"""Local D5 storage guards. No provider calls or credential persistence."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import stat
import tempfile

from src.live_backend import PaidMalformedResponse

ACTIVE = "active_trial.json"
FILES = ("job_manifest.json", "trials.jsonl", "judgement_queue.json",
         "human_review_annotations.json", "summary.json", ACTIVE, ".d5-run.lock")


def check_output(output: Path) -> None:
    """Read-only checks; live execution additionally probes real write/fsync access."""
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("output must be a real directory")
    for name in FILES:
        for path in (output / name, output / (name + ".tmp")):
            if path.is_symlink() or (path.exists() and not stat.S_ISREG(path.stat().st_mode)):
                raise ValueError(f"invalid output file target: {path.name}")


def durable_json(path: Path, value: object) -> None:
    """Flush a replacement before exposing it; keep the previous checkpoint on error."""
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with (path.with_suffix(path.suffix + ".tmp")).open("w") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    path.with_suffix(path.suffix + ".tmp").replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def exclusive_output(output: Path):
    """One writer per result directory, including across separate CLI processes."""
    try:
        import fcntl
    except ImportError as exc:
        raise ValueError("live runs require file locking; use Linux/Codespaces") from exc
    check_output(output)
    output.mkdir(parents=True, exist_ok=True)
    # Never unlink this file: replacing its inode would invalidate mutual exclusion.
    with (output / ".d5-run.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another runner is already using this output directory") from exc
        try:
            check_output(output)
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def probe_writes(output: Path) -> None:
    """Detect existing permission/device/full-disk errors before a paid request."""
    check_output(output)
    with tempfile.TemporaryFile(dir=output) as handle:
        handle.write(b"D5 storage preflight\n")
        handle.flush()
        os.fsync(handle.fileno())
    for name in FILES:
        path = output / name
        if path.exists():
            with path.open("a") as handle:
                handle.flush()
                os.fsync(handle.fileno())


def known_cost(usages: list[dict]) -> float:
    return sum(u["cost"] for u in usages
               if isinstance(u.get("cost"), (int, float)) and not isinstance(u["cost"], bool)
               and math.isfinite(u["cost"]) and u["cost"] >= 0)


class TrialJournal:
    """Checkpoint every request/response before the agent can request another call.

    An interrupted request has an unknown charge, never an assumed zero. A pending
    journal prevents restarting the trial. Completed scored rows can be recovered
    without a model; ambiguous/incomplete requests require an offline billing audit.
    """
    def __init__(self, output: Path, identity: dict):
        self.path = output / ACTIVE
        if self.path.exists():
            raise ValueError("unresolved active_trial.json; do not restart or delete it")
        self.data = {"identity": identity, "phase": "prepared", "calls": [],
                     "known_cost_usd": 0.0, "billing_complete": True}
        self.save()

    def save(self):
        # Only selected model data is stored, never Request headers or credentials.
        text = json.dumps(self.data, allow_nan=False)
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if key and key in text:
            text = text.replace(key, "[REDACTED_API_KEY]")
        durable_json(self.path, json.loads(text))

    def wrap(self, caller):
        def call(**kwargs):
            self.data["phase"] = "request_in_flight"
            entry = {"requested_model": kwargs["model"],
                     "model_input": kwargs["model_input"], "status": "in_flight"}
            # Copy the mutable history before the agent appends subsequent events.
            entry = json.loads(json.dumps(entry))
            self.data["calls"].append(entry)
            self.data["billing_complete"] = False
            self.save()  # A failed checkpoint prevents this request from being sent.
            try:
                response = caller(**kwargs)
            except PaidMalformedResponse as exc:
                entry.update(status="provider_failure", text=exc.text, usage=exc.usage,
                             model=exc.model, response_id=exc.response_id,
                             finish_reason=exc.finish_reason,
                             native_finish_reason=exc.native_finish_reason, error=exc.error)
                self.data["phase"] = "response_received"
                self._update_cost()
                self.save()
                raise
            except BaseException as exc:
                entry.update(status="request_failed", exception_type=type(exc).__name__)
                self.data["phase"] = "request_failed"
                self.save()
                raise
            entry.update(status="response_received", **asdict(response))
            self.data["phase"] = "response_received"
            self._update_cost()
            self.save()  # Retain raw text/usage before parsing or executing tools.
            return response
        return call

    def _update_cost(self):
        usages = [c.get("usage", {}) for c in self.data["calls"]]
        self.data["known_cost_usd"] = known_cost(usages)
        self.data["billing_complete"] = all(
            isinstance(u.get("cost"), (int, float)) and not isinstance(u["cost"], bool)
            and math.isfinite(u["cost"]) and u["cost"] >= 0 for u in usages)

    def completed(self, row: dict):
        self.data.update(phase="trial_scored", completed_trial=row)
        self.save()

    def clear(self):
        self.path.unlink()
