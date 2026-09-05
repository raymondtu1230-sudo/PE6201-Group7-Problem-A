#!/usr/bin/env python3
"""Run the offline suite with keys removed, Python network blocked and a time limit."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GUARD = '''import os, sys
os.environ.pop("OPENROUTER_API_KEY", None)
def prohibit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto"}:
        with open(os.environ["D5_NETWORK_AUDIT_LOG"], "a") as out:
            out.write(event + "\\n")
        raise RuntimeError("D5 readiness audit forbids network access")
sys.addaudithook(prohibit)
'''


def main():
    with tempfile.TemporaryDirectory(prefix="d5-offline-gate-") as tmp:
        directory = Path(tmp)
        (directory / 'sitecustomize.py').write_text(GUARD)
        log = directory / 'network.log'
        env = dict(os.environ)
        env.pop('OPENROUTER_API_KEY', None)
        env['D5_NETWORK_AUDIT_LOG'] = str(log)
        env['PYTHONPATH'] = str(directory) + os.pathsep + str(ROOT)
        try:
            result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                                    cwd=ROOT, env=env, timeout=300)
            code = result.returncode
        except subprocess.TimeoutExpired:
            print('Offline acceptance exceeded 300 seconds; stopped. No paid test is authorized.')
            code = 1
        attempts = len(log.read_text().splitlines()) if log.exists() else 0
        print(json.dumps({'mode': 'offline-readiness', 'valid': code == 0 and attempts == 0,
                          'network_attempts': attempts, 'paid_model_calls': 0}))
        raise SystemExit(code or (1 if attempts else 0))


if __name__ == '__main__': main()
