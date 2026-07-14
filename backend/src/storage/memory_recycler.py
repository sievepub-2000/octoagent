"""Memory and cache recycler for OctoAgent.

Handles automatic cleanup and recycling of memory and cache resources
when context compacts to a new conversation.
"""

from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RecycleResult:
    """Result of a memory/cache recycling operation."""

    freed_memory_mb: float
    freed_disk_mb: float
    cleaned_files: int
    cleaned_dirs: int
    duration_ms: float
    status: str


class MemoryRecycler:
    """Manages memory and cache recycling for context compaction."""

    def __init__(
        self,
        runtime_root: Path,
        cache_dir: Path | None = None,
        max_cache_age_days: int = 7,
        max_cache_size_gb: float = 10.0,
        gc_threshold: int = 1000,
    ) -> None:
        self._runtime_root = runtime_root
        self._cache_dir = cache_dir or runtime_root / "cache"
        self._max_cache_age_days = max_cache_age_days
        self._max_cache_size_gb = max_cache_size_gb
        self._gc_threshold = gc_threshold
        self._last_recycle_time = 0.0
        self._recycle_interval_seconds = 300  # 5 minutes minimum between recycles
        self._operation_count = 0
        self._stats: dict[str, Any] = {
            "total_recycles": 0,
            "total_freed_memory_mb": 0.0,
            "total_freed_disk_mb": 0.0,
            "last_recycle_at": None,
        }

    def should_recycle(self) -> bool:
        """Check if recycling should be triggered."""
        if self._operation_count < self._gc_threshold:
            return False
        if time.time() - self._last_recycle_time < self._recycle_interval_seconds:
            return False
        return True

    def trigger_recycle(self, *, context_compacted: bool = False) -> RecycleResult:
        """Trigger memory and cache recycling.

        Args:
            context_compacted: Whether triggered by context compaction.

        Returns:
            RecycleResult with statistics.
        """
        start_time = time.time()
        freed_memory_mb = 0.0
        freed_disk_mb = 0.0
        cleaned_files = 0
        cleaned_dirs = 0

        try:
            # 1. Python garbage collection
            freed_memory_mb = self._run_gc()

            # 2. Clean old cache files
            disk_freed, files_cleaned, dirs_cleaned = self._clean_old_cache()
            freed_disk_mb += disk_freed
            cleaned_files += files_cleaned
            cleaned_dirs += dirs_cleaned

            # 3. Clean temporary files
            temp_freed, temp_files = self._clean_temp_files()
            freed_disk_mb += temp_freed
            cleaned_files += temp_files

            # 4. Update stats
            duration_ms = (time.time() - start_time) * 1000
            self._last_recycle_time = time.time()
            self._operation_count = 0
            self._stats["total_recycles"] += 1
            self._stats["total_freed_memory_mb"] += freed_memory_mb
            self._stats["total_freed_disk_mb"] += freed_disk_mb
            self._stats["last_recycle_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            logger.info(
                "Memory recycler completed: freed %.2f MB memory, %.2f MB disk, %d files, %d dirs, %.2f ms",
                freed_memory_mb,
                freed_disk_mb,
                cleaned_files,
                cleaned_dirs,
                duration_ms,
            )

            return RecycleResult(
                freed_memory_mb=freed_memory_mb,
                freed_disk_mb=freed_disk_mb,
                cleaned_files=cleaned_files,
                cleaned_dirs=cleaned_dirs,
                duration_ms=duration_ms,
                status="success",
            )

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("Memory recycler failed: %s", exc, exc_info=True)
            return RecycleResult(
                freed_memory_mb=freed_memory_mb,
                freed_disk_mb=freed_disk_mb,
                cleaned_files=cleaned_files,
                cleaned_dirs=cleaned_dirs,
                duration_ms=duration_ms,
                status=f"error: {exc}",
            )

    def _run_gc(self) -> float:
        """Run Python garbage collection and estimate memory freed."""
        before = self._get_process_memory_mb()
        gc.collect()
        after = self._get_process_memory_mb()
        freed = max(0, before - after)
        logger.debug("GC freed %.2f MB", freed)
        return freed

    def _get_process_memory_mb(self) -> float:
        """Get current process memory usage in MB."""
        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            return usage.ru_maxrss / 1024  # Convert KB to MB
        except Exception:
            return 0.0

    def _clean_old_cache(self) -> tuple[float, int, int]:
        """Clean cache files older than max_cache_age_days."""
        if not self._cache_dir.exists():
            return 0.0, 0, 0

        total_freed = 0.0
        files_cleaned = 0
        dirs_cleaned = 0
        cutoff_time = time.time() - (self._max_cache_age_days * 86400)

        for item in self._cache_dir.rglob("*"):
            try:
                if item.is_file():
                    mtime = item.stat().st_mtime
                    if mtime < cutoff_time:
                        size_mb = item.stat().st_size / (1024 * 1024)
                        item.unlink()
                        total_freed += size_mb
                        files_cleaned += 1
                elif item.is_dir():
                    if not any(item.iterdir()):
                        item.rmdir()
                        dirs_cleaned += 1
            except Exception as exc:
                logger.debug("Failed to clean %s: %s", item, exc)

        # Check if cache directory exceeds max size
        total_size = self._calculate_dir_size(self._cache_dir)
        max_size_bytes = self._max_cache_size_gb * 1024 * 1024 * 1024
        if total_size > max_size_bytes:
            logger.info(
                "Cache size %.2f GB exceeds limit %.2f GB, triggering aggressive cleanup",
                total_size / (1024 * 1024 * 1024),
                self._max_cache_size_gb,
            )
            # Remove oldest files until under limit
            self._aggressive_cache_cleanup(max_size_bytes)

        return total_freed, files_cleaned, dirs_cleaned

    def _calculate_dir_size(self, directory: Path) -> float:
        """Calculate total size of directory in bytes."""
        total = 0
        for item in directory.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except Exception:
                    pass
        return total

    def _aggressive_cache_cleanup(self, target_size_bytes: float) -> None:
        """Remove oldest files until cache is under target size."""
        files = []
        for item in self._cache_dir.rglob("*"):
            if item.is_file():
                try:
                    files.append((item.stat().st_mtime, item.stat().st_size, item))
                except Exception:
                    pass

        files.sort(key=lambda x: x[0])  # Sort by mtime (oldest first)

        current_size = self._calculate_dir_size(self._cache_dir)
        for _, size, file_path in files:
            if current_size <= target_size_bytes:
                break
            try:
                file_path.unlink()
                current_size -= size
            except Exception as exc:
                logger.debug("Failed to remove %s: %s", file_path, exc)

    def _clean_temp_files(self) -> tuple[float, int]:
        """Clean temporary files in runtime/tmp directory."""
        tmp_dir = self._runtime_root / "tmp"
        if not tmp_dir.exists():
            return 0.0, 0

        total_freed = 0.0
        files_cleaned = 0
        cutoff_time = time.time() - (24 * 3600)  # 24 hours

        for item in tmp_dir.rglob("*"):
            try:
                if item.is_file() and item.stat().st_mtime < cutoff_time:
                    size_mb = item.stat().st_size / (1024 * 1024)
                    item.unlink()
                    total_freed += size_mb
                    files_cleaned += 1
            except Exception as exc:
                logger.debug("Failed to clean temp file %s: %s", item, exc)

        return total_freed, files_cleaned

    def get_stats(self) -> dict[str, Any]:
        """Get recycling statistics."""
        return {
            **self._stats,
            "gc_threshold": self._gc_threshold,
            "max_cache_age_days": self._max_cache_age_days,
            "max_cache_size_gb": self._max_cache_size_gb,
            "current_operation_count": self._operation_count,
            "last_recycle_time": self._last_recycle_time,
        }

    def increment_operation_count(self) -> None:
        """Increment operation counter for recycle threshold."""
        self._operation_count += 1


# Singleton instance
_recycler: MemoryRecycler | None = None


def get_memory_recycler(runtime_root: Path) -> MemoryRecycler:
    """Get or create the singleton MemoryRecycler instance."""
    global _recycler
    if _recycler is None:
        _recycler = MemoryRecycler(
            runtime_root=runtime_root,
            max_cache_age_days=7,
            max_cache_size_gb=10.0,
            gc_threshold=1000,
        )
    return _recycler
