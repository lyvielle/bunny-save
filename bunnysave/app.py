import logging
import os
import shutil
import uuid

import hashlib

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

from . import VERSION, redact
from .archive_io import PipelineError
from .backup import delete_backup_files
from .browse import list_archive, preview
from .conflict import POLICIES
from .db import DB
from .jobs import JobManager
from .model import normalize_setup
from .scheduler import Scheduler
from .secretstore import SecretError, keyring_set, resolve_archive_secret, sftp_secret_name
from .settings import Settings
from .testing import test_source
from .util import hostname, iso

log = logging.getLogger("bunnysave.app")


def _has_module(n):
    try:
        __import__(n)
        return True
    except ImportError:
        return False


def create_app(settings=None, start_scheduler=None):
    settings = settings or Settings.from_env()
    redact.setup_logging(settings.logs_dir)
    db = DB(settings.db_path)
    jobs = JobManager(settings, db)
    sched = Scheduler(db, jobs)
    if start_scheduler is None:
        start_scheduler = os.environ.get("BUNNYSAVE_SCHEDULER", "1") == "1"
    if start_scheduler:
        sched.start()

    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(SETTINGS=settings, DB=db, JOBS=jobs, SCHED=sched, MAX_CONTENT_LENGTH=4 * 1024 * 1024)

    @app.errorhandler(Exception)
    def on_error(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify(error=e.description), e.code
        code = 400 if isinstance(e, (ValueError, SecretError, PipelineError, KeyError)) else 500
        if code == 500:
            log.exception("unhandled error")
        return jsonify(error=redact.redact(f"{type(e).__name__}: {e}")), code

    icon_v = hashlib.sha256(open(os.path.join(app.static_folder, "icon-512.png"), "rb").read()).hexdigest()[:8]

    def _versioned(name, mimetype):
        txt = open(os.path.join(app.static_folder, name), encoding="utf-8").read().replace("__V__", icon_v)
        r = Response(txt, mimetype=mimetype)
        r.headers["Cache-Control"] = "no-cache"
        return r

    @app.after_request
    def no_cache_static(r):
        if request.path.startswith("/static/"):
            r.headers["Cache-Control"] = "no-cache"
        return r

    @app.get("/")
    def index():
        return _versioned("index.html", "text/html")

    @app.get("/sw.js")
    def service_worker():  # served from "/" so its scope covers the whole app
        r = _versioned("sw.js", "text/javascript")
        r.headers["Service-Worker-Allowed"] = "/"
        return r

    @app.get("/manifest.webmanifest")
    def web_manifest():
        return _versioned("manifest.webmanifest", "application/manifest+json")

    @app.get("/api/info")
    def info():
        return jsonify(version=VERSION, hostname=hostname(), conflict_policies=POLICIES,
                       capabilities={"gpg": bool(shutil.which("gpg")), "age": bool(shutil.which("age")),
                                     "zstd": bool(shutil.which("zstd")), "bzip2": bool(shutil.which("bzip2")),
                                     "zip_aes": _has_module("pyzipper"), "sftp": _has_module("paramiko"),
                                     "keyring": _has_module("keyring"), "scheduler": sched.available, "host_root": settings.host_available(),
                                     "master_key": bool(settings.master_key)},
                       backups_dir=str(settings.backups_dir), keys_dir=str(settings.keys_dir))

    # ---------------- setups
    def setup_view(s):
        d = dict(s)
        d["next_run"] = sched.next_run(s["id"])
        return d

    @app.get("/api/setups")
    def setups_list():
        return jsonify([setup_view(s) for s in db.list_setups()])

    @app.post("/api/setups")
    def setups_create():
        cfg = normalize_setup(request.get_json(force=True))
        sid = uuid.uuid4().hex[:8]
        db.save_setup(sid, cfg, iso())
        s = db.get_setup(sid)
        sched.sync(s)
        return jsonify(setup_view(s)), 201

    @app.put("/api/setups/<sid>")
    def setups_update(sid):
        old = db.get_setup(sid) or _404()
        cfg = normalize_setup(request.get_json(force=True), old["config"])
        db.save_setup(sid, cfg, iso())
        s = db.get_setup(sid)
        sched.sync(s)
        return jsonify(setup_view(s))

    @app.delete("/api/setups/<sid>")
    def setups_delete(sid):
        db.delete_setup(sid)
        sched.remove(sid)
        return jsonify(ok=True)

    def _404():
        from werkzeug.exceptions import NotFound
        raise NotFound("not found")

    @app.post("/api/test-source")
    def test_source_route():
        body = request.get_json(force=True)
        src = normalize_setup({"name": "test", "sources": [body["source"]]})["sources"][0]
        return jsonify(test_source(src, settings, body.get("secrets") or {}))

    # ---------------- jobs
    @app.post("/api/setups/<sid>/run")
    def run_setup(sid):
        s = db.get_setup(sid) or _404()
        body = request.get_json(silent=True) or {}
        try:
            job = jobs.submit_backup(s, {"archive_password": body.get("archive_password"),
                                         "sftp": body.get("sftp") or {}})
        except RuntimeError as e:
            return jsonify(error=str(e)), 409
        return jsonify(job.to_dict()), 202

    @app.get("/api/jobs")
    def jobs_list():
        return jsonify(jobs.list())

    @app.get("/api/jobs/<jid>")
    def jobs_get(jid):
        j = jobs.get(jid) or _404()
        return jsonify(j.to_dict())

    @app.post("/api/jobs/<jid>/cancel")
    def jobs_cancel(jid):
        return jsonify(ok=jobs.cancel(jid))

    @app.post("/api/setups/<sid>/keyring")
    def keyring_save(sid):
        s = db.get_setup(sid) or _404()
        b = request.get_json(force=True)
        cfg = s["config"]
        if b.get("kind") == "archive":
            keyring_set(f"archive:{cfg['secret_ref']}", b["value"])
        else:
            src = next(x for x in cfg["sources"] if x["id"] == b["source_id"])
            keyring_set(f"sftp-key:{src['key_path']}" if src.get("auth") == "key" else sftp_secret_name(src), b["value"])
        return jsonify(ok=True)

    # ---------------- backups
    def backup_view(b):
        return {k: b[k] for k in ("id", "setup_id", "setup_name", "filename", "created", "size", "fmt", "encrypted",
                                  "sha256", "verify_status", "status", "error")} | {"enc_tool": b["enc"].get("tool")}

    @app.get("/api/backups")
    def backups_list():
        return jsonify([backup_view(b) for b in db.list_backups(request.args.get("setup_id"))])

    @app.get("/api/backups/<bid>/download")
    def backup_download(bid):
        b = db.get_backup(bid) or _404()
        if not os.path.isfile(b["path"]):
            return jsonify(error="archive file is missing on disk"), 404
        return send_file(b["path"], as_attachment=True, download_name=b["filename"], conditional=True)

    @app.delete("/api/backups/<bid>")
    def backups_delete(bid):
        b = db.get_backup(bid) or _404()
        delete_backup_files(b)
        db.delete_backup(bid)
        return jsonify(ok=True)

    def _backup_secret(b, body):
        return resolve_archive_secret(settings, b["fmt"], b["enc"], b["secret_ref"], body.get("archive_password")) \
            if b["encrypted"] else None

    def _with_secret(b, body, fn):
        secret = _backup_secret(b, body)
        redact.register(secret)
        try:
            return fn(secret)
        finally:
            redact.unregister(secret)

    @app.post("/api/backups/<bid>/entries")
    def backup_entries(bid):
        b = db.get_backup(bid) or _404()
        body = request.get_json(silent=True) or {}
        return jsonify(_with_secret(b, body, lambda s: list_archive(b, s, settings)))

    @app.post("/api/backups/<bid>/preview")
    def backup_preview(bid):
        b = db.get_backup(bid) or _404()
        body = request.get_json(force=True)
        try:
            return jsonify(_with_secret(b, body, lambda s: preview(b, s, settings, body["path"])))
        except FileNotFoundError:
            return jsonify(error="entry not found"), 404

    def _restore_params(body, apply):
        return {"mode": body.get("mode"), "target": body.get("target") or "/", "start": body.get("start") or "",
                "dest": body.get("dest") or {}, "conflict": body.get("conflict", "skip"),
                "selection": body.get("selection") or [], "apply": apply,
                "post_restore": body.get("post_restore") or {}}

    @app.post("/api/backups/<bid>/restore/plan")
    def restore_plan(bid):
        b = db.get_backup(bid) or _404()
        body = request.get_json(force=True)
        supplied = {"archive_password": body.get("archive_password"), "sftp": body.get("sftp") or {},
                    "dest": body.get("dest_secret") or {}}
        return jsonify(jobs.run_sync("plan", b, _restore_params(body, False), supplied))

    @app.post("/api/backups/<bid>/restore/run")
    def restore_run(bid):
        b = db.get_backup(bid) or _404()
        body = request.get_json(force=True)
        pr = body.get("post_restore") or {}
        if pr.get("enabled") and pr.get("confirm") != "RUN":
            return jsonify(error="post-restore commands need explicit confirmation"), 400
        supplied = {"archive_password": body.get("archive_password"), "sftp": body.get("sftp") or {},
                    "dest": body.get("dest_secret") or {}}
        job = jobs.submit_restore(b, _restore_params(body, True), supplied)
        return jsonify(job.to_dict()), 202

    return app


def main():  # `python -m bunnysave.app` for local dev; Docker uses gunicorn
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("BUNNYSAVE_PORT", "8484")), threaded=True)


if __name__ == "__main__":
    main()
