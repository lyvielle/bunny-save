import logging
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from . import redact
from .backup import Cancelled, run_backup
from .restore import run_restore
from .util import iso

logger = logging.getLogger("bunnysave.jobs")


class Job:
    def __init__(self, kind, setup_id, label, trigger="manual"):
        self.id = uuid.uuid4().hex[:10]
        self.kind, self.setup_id, self.label, self.trigger = kind, setup_id, label, trigger
        self.state, self.phase, self.current = "queued", "queued", ""
        self.total_bytes = self.done_bytes = self.files_total = self.files_done = 0
        self.lines = deque(maxlen=300)
        self.hooks, self.result, self.error = [], {}, None
        self.started = self.finished = None
        self.cancel_event = threading.Event()
        self._secrets = []

    # -- helpers used by backup/restore code
    def check_cancel(self):
        if self.cancel_event.is_set():
            raise Cancelled()

    def log(self, msg, level=logging.INFO):
        msg = redact.redact(msg)
        self.lines.append(f"{time.strftime('%H:%M:%S')} {msg}")
        logger.log(level, msg, extra={"job_id": self.id, "setup_id": self.setup_id})

    def warn(self, msg):
        self.log("WARN " + msg, logging.WARNING)

    def register_secret(self, s):
        if s:
            redact.register(s)
            self._secrets.append(s)

    def release_secrets(self):
        for s in self._secrets:
            redact.unregister(s)
        self._secrets.clear()

    def to_dict(self):
        pct = int(100 * self.done_bytes / self.total_bytes) if self.total_bytes else (100 if self.state == "done" else 0)
        return {"id": self.id, "kind": self.kind, "setup_id": self.setup_id, "label": self.label,
                "trigger": self.trigger, "state": self.state, "phase": self.phase,
                "current": redact.redact(self.current), "total_bytes": self.total_bytes,
                "done_bytes": self.done_bytes, "files_total": self.files_total, "files_done": self.files_done,
                "percent": min(pct, 100), "log": list(self.lines), "hooks": self.hooks,
                "result": self.result, "error": redact.redact(self.error) if self.error else None,
                "started": self.started, "finished": self.finished}


class JobManager:
    def __init__(self, settings, db, workers=2):
        self.settings, self.db = settings, db
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self.jobs, self.order = {}, deque(maxlen=60)
        self.lock = threading.Lock()
        self.busy_setups = set()

    def _register(self, job):
        with self.lock:
            self.jobs[job.id] = job
            self.order.append(job.id)
            for jid in list(self.jobs):
                if jid not in self.order:
                    del self.jobs[jid]

    def get(self, jid):
        return self.jobs.get(jid)

    def list(self):
        return [self.jobs[j].to_dict() for j in reversed(self.order) if j in self.jobs]

    def cancel(self, jid):
        j = self.jobs.get(jid)
        if not j or j.state not in ("queued", "running"):
            return False
        j.cancel_event.set()
        return True

    def submit_backup(self, setup, supplied, trigger="manual"):
        with self.lock:
            if setup["id"] in self.busy_setups:
                raise RuntimeError("a job for this setup is already running")
            self.busy_setups.add(setup["id"])
        job = Job("backup", setup["id"], setup["name"], trigger)
        self._register(job)
        self.pool.submit(self._run, job, lambda: run_backup(self.settings, self.db, job, setup, supplied), setup["id"])
        return job

    def submit_restore(self, backup, params, supplied):
        job = Job("restore", backup["setup_id"], backup["filename"])
        self._register(job)
        self.pool.submit(self._run, job, lambda: run_restore(self.settings, self.db, job, backup, params, supplied), None)
        return job

    def run_sync(self, kind, backup, params, supplied):
        """Synchronous (plan) execution returning the result or raising."""
        job = Job(kind, backup["setup_id"], backup["filename"])
        try:
            return run_restore(self.settings, self.db, job, backup, params, supplied)
        finally:
            job.release_secrets()

    def _run(self, job, fn, busy_key):
        job.state, job.started = "running", iso()
        job.log(f"{job.kind} started ({job.trigger})")
        try:
            fn()
            job.state, job.phase = "done", "done"
            job.done_bytes = job.total_bytes
        except Cancelled:
            job.state, job.phase = "cancelled", "cancelled"
            job.log("cancelled; partial output removed")
        except Exception as e:
            job.state, job.phase = "failed", "failed"
            job.error = redact.redact(f"{type(e).__name__}: {e}")
            job.log("FAILED: " + job.error, logging.ERROR)
        finally:
            job.finished = iso()
            job.release_secrets()
            if busy_key:
                with self.lock:
                    self.busy_setups.discard(busy_key)
