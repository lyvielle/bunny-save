"""Run hook / post-restore commands with timeout, captured + redacted output."""
import os
import signal
import subprocess
import time

from .redact import redact

MAX_OUT = 64 * 1024


def run_command(command, timeout, env_extra, cwd=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("BUNNYSAVE_MASTER")}
    env.update({k: str(v) for k, v in env_extra.items()})
    t0 = time.time()
    res = {"command": command, "exit_code": None, "timed_out": False, "stdout": "", "stderr": ""}
    p = subprocess.Popen(["/bin/sh", "-c", command], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, cwd=cwd, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout or 300)
    except subprocess.TimeoutExpired:
        res["timed_out"] = True
        try:
            os.killpg(p.pid, signal.SIGTERM)
            time.sleep(2)
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = p.communicate()
    res["exit_code"] = p.returncode
    res["stdout"] = redact(out[-MAX_OUT:].decode("utf-8", "replace"))
    res["stderr"] = redact(err[-MAX_OUT:].decode("utf-8", "replace"))
    res["duration"] = round(time.time() - t0, 2)
    return res
