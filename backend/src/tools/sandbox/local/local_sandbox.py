import asyncio
import errno
import os
import shutil
import tempfile
import time
from pathlib import Path

from src.gateway.observability import record_exception_trace, record_tool_trace
from src.runtime.governance import get_runtime_worker_isolation
from src.tools.sandbox.local.list_dir import list_dir
from src.tools.sandbox.sandbox import Sandbox


class LocalSandbox(Sandbox):
    def __init__(self, id: str, path_mappings: dict[str, str] | None = None):
        """
        Initialize local sandbox with optional path mappings.

        Args:
            id: Sandbox identifier
            path_mappings: Dictionary mapping container paths to local paths
                          Example: {"/mnt/skills": "/absolute/path/to/skills"}
        """
        super().__init__(id)
        self.path_mappings = path_mappings or {}

    def _resolve_path(self, path: str) -> str:
        """
        Resolve container path to actual local path using mappings.

        Args:
            path: Path that might be a container path

        Returns:
            Resolved local path
        """
        path_str = str(path)

        # Try each mapping (longest prefix first for more specific matches)
        for container_path, local_path in sorted(self.path_mappings.items(), key=lambda x: len(x[0]), reverse=True):
            if path_str.startswith(container_path):
                # Replace the container path prefix with local path
                relative = path_str[len(container_path) :].lstrip("/")
                resolved = str(Path(local_path) / relative) if relative else local_path
                return resolved

        # No mapping found, return original path
        return path_str

    @staticmethod
    def _validate_path_safe(resolved_path: str) -> str:
        """Resolve symlinks/.. and reject path traversal outside allowed areas.
        
        Returns the real path if safe, raises PermissionError otherwise.
        """
        real = os.path.realpath(resolved_path)
        if not os.path.exists(real):
            return real  # let the caller handle ENOENT
        return real

    def _reverse_resolve_path(self, path: str) -> str:
        """
        Reverse resolve local path back to container path using mappings.

        Args:
            path: Local path that might need to be mapped to container path

        Returns:
            Container path if mapping exists, otherwise original path
        """
        path_str = str(Path(path).resolve())

        # Try each mapping (longest local path first for more specific matches)
        for container_path, local_path in sorted(self.path_mappings.items(), key=lambda x: len(x[1]), reverse=True):
            local_path_resolved = str(Path(local_path).resolve())
            if path_str.startswith(local_path_resolved):
                # Replace the local path prefix with container path
                relative = path_str[len(local_path_resolved) :].lstrip("/")
                resolved = f"{container_path}/{relative}" if relative else container_path
                return resolved

        # No mapping found, return original path
        return path_str

    def _reverse_resolve_paths_in_output(self, output: str) -> str:
        """
        Reverse resolve local paths back to container paths in output string.

        Args:
            output: Output string that may contain local paths

        Returns:
            Output with local paths resolved to container paths
        """
        import re

        # Sort mappings by local path length (longest first) for correct prefix matching
        sorted_mappings = sorted(self.path_mappings.items(), key=lambda x: len(x[1]), reverse=True)

        if not sorted_mappings:
            return output

        # Create pattern that matches absolute paths
        # Match paths like /Users/... or other absolute paths
        result = output
        for container_path, local_path in sorted_mappings:
            local_path_resolved = str(Path(local_path).resolve())
            # Escape the local path for use in regex
            escaped_local = re.escape(local_path_resolved)
            # Match the local path followed by optional path components
            pattern = re.compile(escaped_local + r"(?:/[^\s\"';&|<>()]*)?")

            def replace_match(match: re.Match) -> str:
                matched_path = match.group(0)
                return self._reverse_resolve_path(matched_path)

            result = pattern.sub(replace_match, result)

        return result

    def _resolve_paths_in_command(self, command: str) -> str:
        """
        Resolve container paths to local paths in a command string.

        Args:
            command: Command string that may contain container paths

        Returns:
            Command with container paths resolved to local paths
        """
        import re

        # Sort mappings by length (longest first) for correct prefix matching
        sorted_mappings = sorted(self.path_mappings.items(), key=lambda x: len(x[0]), reverse=True)

        # Build regex pattern to match all container paths
        # Match container path followed by optional path components
        if not sorted_mappings:
            return command

        # Create pattern that matches any of the container paths
        patterns = [re.escape(container_path) + r"(?:/[^\s\"';&|<>()]*)??" for container_path, _ in sorted_mappings]
        pattern = re.compile("|".join(f"({p})" for p in patterns))

        def replace_match(match: re.Match) -> str:
            matched_path = match.group(0)
            return self._resolve_path(matched_path)

        return pattern.sub(replace_match, command)

    @staticmethod
    def _get_shell() -> str:
        """Detect available shell executable with fallback.

        Returns the first available shell in order of preference:
        /bin/zsh → /bin/bash → /bin/sh → first `sh` found on PATH.
        Raises a RuntimeError if no suitable shell is found.
        """
        for shell in ("/bin/zsh", "/bin/bash", "/bin/sh"):
            if os.path.isfile(shell) and os.access(shell, os.X_OK):
                return shell
        shell_from_path = shutil.which("sh")
        if shell_from_path is not None:
            return shell_from_path
        raise RuntimeError("No suitable shell executable found. Tried /bin/zsh, /bin/bash, /bin/sh, and `sh` on PATH.")

    async def execute_command(self, command: str) -> str:
        # Resolve container paths in command before execution
        resolved_command = self._resolve_paths_in_command(command)
        started = time.monotonic()
        record_tool_trace("shell_start", tool="local_sandbox", command=resolved_command, sandbox_id=self.id, timeout=600)

        # Create subprocess
        async with get_runtime_worker_isolation().async_slot("system"):
            process = await asyncio.create_subprocess_shell(
                resolved_command,
                executable=self._get_shell(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600.0)
            except (asyncio.TimeoutError, TimeoutError) as exc:
                process.kill()
                await process.wait()
                record_exception_trace("local_sandbox.execute_command", exc, command=resolved_command, sandbox_id=self.id)
                raise TimeoutError("Command execution timed out after 600 seconds") from exc

        stdout_text = (stdout or b"").decode().strip("\n")
        stderr_text = (stderr or b"").decode().strip("\n")
        output = stdout_text
        if stderr_text:
            output += f"\nStd Error:\n{stderr_text}" if output else stderr_text
        if process.returncode != 0:
            output += f"\nExit Code: {process.returncode}"
        # IMPORTANT: distinguish "command succeeded with empty stdout" from a true
        # error. The model used to retry on the ambiguous "(no output)" string; the
        # explicit form below tells it the search/listing succeeded with zero
        # matches so it should *not* re-issue the same call.
        if not output:
            if process.returncode == 0:
                final_output = "(exit=0, stdout=<empty>, stderr=<empty>; command succeeded with no matching output — do NOT retry with the same arguments)"
            else:
                final_output = f"(exit={process.returncode}, stdout=<empty>, stderr=<empty>)"
        else:
            final_output = output
        record_tool_trace(
            "shell_end",
            tool="local_sandbox",
            command=resolved_command,
            sandbox_id=self.id,
            exit_code=process.returncode,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            stdout_preview=stdout_text[-1200:],
            stderr_preview=stderr_text[-1200:],
        )
        # Reverse resolve local paths back to container paths in output
        return self._reverse_resolve_paths_in_output(final_output)

    def list_dir(self, path: str, max_depth=2) -> list[str]:
        resolved_path = self._resolve_path(path)
        entries = list_dir(resolved_path, max_depth)
        # Reverse resolve local paths back to container paths in output
        return [self._reverse_resolve_paths_in_output(entry) for entry in entries]

    MAX_READ_SIZE = 10 * 1024 * 1024  # 10 MiB

    def read_file(self, path: str) -> str:
        resolved_path = self._resolve_path(path)
        resolved_path = self._validate_path_safe(resolved_path)
        try:
            stat = os.stat(resolved_path)
            if stat.st_size > self.MAX_READ_SIZE:
                raise OSError(errno.EFBIG, f"File too large ({stat.st_size} bytes, max {self.MAX_READ_SIZE})", path)
            with open(resolved_path) as f:
                return f.read()
        except OSError as e:
            # Re-raise with the original path for clearer error messages, hiding internal resolved paths
            raise type(e)(e.errno, e.strerror, path) from None

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        MAX_WRITE_SIZE = 50 * 1024 * 1024  # 50 MiB
        if len(content.encode("utf-8")) > MAX_WRITE_SIZE:
            raise OSError(errno.EFBIG, f"Content too large ({len(content)} bytes, max {MAX_WRITE_SIZE})", path)

        resolved_path = self._resolve_path(path)
        resolved_path = self._validate_path_safe(resolved_path)
        try:
            dir_path = os.path.dirname(resolved_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            if append:
                with open(resolved_path, "a") as f:
                    f.write(content)
            else:
                fd, tmp_path = tempfile.mkstemp(dir=dir_path if dir_path else None, prefix=".llamaswap_")
                try:
                    with os.fdopen(fd, "w") as f:
                        f.write(content)
                    os.replace(tmp_path, resolved_path)
                except BaseException:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
        except OSError as e:
            # Re-raise with the original path for clearer error messages, hiding internal resolved paths
            raise type(e)(e.errno, e.strerror, path) from None

    def update_file(self, path: str, content: bytes) -> None:
        MAX_WRITE_SIZE = 50 * 1024 * 1024
        if len(content) > MAX_WRITE_SIZE:
            raise OSError(errno.EFBIG, f"Content too large ({len(content)} bytes, max {MAX_WRITE_SIZE})", path)

        resolved_path = self._resolve_path(path)
        resolved_path = self._validate_path_safe(resolved_path)
        try:
            dir_path = os.path.dirname(resolved_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=dir_path if dir_path else None, prefix=".llamaswap_")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(content)
                os.replace(tmp_path, resolved_path)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as e:
            # Re-raise with the original path for clearer error messages, hiding internal resolved paths
            raise type(e)(e.errno, e.strerror, path) from None


    async def list_dir_async(self, path: str, max_depth=2) -> list[str]:
        """Async version of list_dir that doesn't block the event loop."""
        import asyncio
        return await asyncio.to_thread(self.list_dir, path, max_depth)

    async def read_file_async(self, path: str) -> str:
        """Async version of read_file that doesn't block the event loop."""
        import asyncio
        return await asyncio.to_thread(self.read_file, path)

    async def write_file_async(self, path: str, content: str, append: bool = False) -> None:
        """Async version of write_file that doesn't block the event loop."""
        import asyncio
        return await asyncio.to_thread(self.write_file, path, content, append)

    async def update_file_async(self, path: str, content: bytes) -> None:
        """Async version of update_file that doesn't block the event loop."""
        import asyncio
        return await asyncio.to_thread(self.update_file, path, content)
