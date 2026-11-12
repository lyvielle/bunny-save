"""APScheduler glue. Unattended runs can only use env-derived or keyring secrets."""
import logging

log = logging.getLogger("bunnysave.scheduler")


class Scheduler:
    def __init__(self, db, jobs):
        self.db, self.jobs = db, jobs
        self.sched = None
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            self.sched = BackgroundScheduler()
        except ImportError:
            log.warning("APScheduler not installed: schedules disabled")

    @property
    def available(self):
        return self.sched is not None

    def start(self):
        if self.sched:
            self.sched.start()
            for s in self.db.list_setups():
                self.sync(s)

    def sync(self, setup):
        if not self.sched:
            return
        jid = f"setup-{setup['id']}"
        if self.sched.get_job(jid):
            self.sched.remove_job(jid)
        sc = setup["config"]["schedule"]
        if sc["type"] == "interval":
            from apscheduler.triggers.interval import IntervalTrigger
            trig = IntervalTrigger(hours=sc["hours"])
        elif sc["type"] == "daily":
            from apscheduler.triggers.cron import CronTrigger
            hh, mm = sc["time"].split(":")
            trig = CronTrigger(hour=int(hh), minute=int(mm))
        else:
            return
        self.sched.add_job(self._fire, trig, id=jid, args=[setup["id"]], max_instances=1, coalesce=True,
                           misfire_grace_time=3600)

    def remove(self, setup_id):
        if self.sched and self.sched.get_job(f"setup-{setup_id}"):
            self.sched.remove_job(f"setup-{setup_id}")

    def _fire(self, setup_id):
        setup = self.db.get_setup(setup_id)
        if not setup:
            return
        try:
            self.jobs.submit_backup(setup, {}, trigger="schedule")
        except Exception as e:
            log.warning("scheduled run not started: %s", e, extra={"setup_id": setup_id})

    def next_run(self, setup_id):
        if not self.sched:
            return None
        j = self.sched.get_job(f"setup-{setup_id}")
        return j.next_run_time.isoformat() if j and j.next_run_time else None
