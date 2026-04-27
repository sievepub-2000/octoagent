from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path('/home/sieve-pub/public-workspace/octoagent')
BACKEND = ROOT / 'backend'
TMPDIR = ROOT / 'tmp'
TMPDIR.mkdir(parents=True, exist_ok=True)

URL = 'http://127.0.0.1:19882/api/fallback-pool/status'


def fetch_status() -> dict:
    with urlopen(URL, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def stop_gateway() -> None:
    subprocess.run(
        "pkill -f 'uvicorn src.gateway.app:app --app-dir /home/sieve-pub/public-workspace/octoagent/backend --host 127.0.0.1 --port 19882'",
        shell=True,
        check=False,
    )
    time.sleep(1.5)


def start_gateway(with_key: bool, log_name: str) -> subprocess.Popen:
    env = os.environ.copy()
    if with_key:
        env['FREE_CLAUDE_CODE_API_KEY'] = 'test-stress-key-xxx'
    else:
        env.pop('FREE_CLAUDE_CODE_API_KEY', None)

    log_path = BACKEND / 'logs' / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open('w', encoding='utf-8')

    proc = subprocess.Popen(
        [
            str(BACKEND / '.venv/bin/python'),
            '-m',
            'uvicorn',
            'src.gateway.app:app',
            '--app-dir',
            str(BACKEND),
            '--host',
            '127.0.0.1',
            '--port',
            '19882',
        ],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )

    deadline = time.time() + 25
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            _ = fetch_status()
            return proc
        except Exception as err:  # noqa: BLE001
            last_err = err
            time.sleep(1)

    proc.send_signal(signal.SIGTERM)
    raise RuntimeError(f'Gateway did not become ready: {last_err}')


def main() -> None:
    before_path = TMPDIR / 'fallback-status-before.json'
    with_key_path = TMPDIR / 'fallback-status-with-key.json'
    after_path = TMPDIR / 'fallback-status-after.json'

    before = fetch_status()
    write_json(before_path, before)

    stop_gateway()
    _proc_key = start_gateway(with_key=True, log_name='gateway-fallback.log')
    with_key = fetch_status()
    write_json(with_key_path, with_key)

    stop_gateway()
    _proc_base = start_gateway(with_key=False, log_name='gateway.log')
    after = fetch_status()
    write_json(after_path, after)

    print('---before---')
    print(json.dumps(before, indent=2, ensure_ascii=False))
    print('---with-key---')
    print(json.dumps(with_key, indent=2, ensure_ascii=False))
    print('---after---')
    print(json.dumps(after, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
