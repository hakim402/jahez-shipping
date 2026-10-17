"""Bounded explicit batch, sharing the admin refresh service; never invoked by views."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError
from django.db.models import F

from apps.containers.refresh import refresh_container, short_database_wait
from apps.containers.tracking import active_journeys

# No automatic retry. Reserve a complete service budget plus DB/summary margin.
REFRESH_RESERVE_SECONDS = 30


@contextmanager
def batch_lock():
    """One batch per shared Shipping data directory; OS releases lock after exit/crash."""
    fd = None
    try:
        path = Path(settings.DATA_DIR) / ".container-refresh.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("invalid_lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if fd is not None:
            os.close(fd)
        raise CommandError("refresh_busy", returncode=75) from None
    except OSError:
        if fd is not None:
            os.close(fd)
        raise CommandError("refresh_lock_unavailable", returncode=75) from None
    try:
        yield
    finally:
        # Keep the inode: unlinking an advisory lock file permits split locks.
        os.close(fd)


class Command(BaseCommand):
    help = "Refresh active journeys once with bounded work; summaries never include identities."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        selection = parser.add_mutually_exclusive_group(required=True)
        selection.add_argument("--active", action="store_true", help="Include private and published active journeys.")
        selection.add_argument("--container", type=int, help="One internal admin record ID; still skips archived/completed journeys.")
        parser.add_argument("--dry-run", "--status", dest="dry_run", action="store_true", help="Read selection counts only; no lock file, writes or provider calls.")
        parser.add_argument("--limit", type=int, default=50, help="Maximum selected records, 1–100 (default 50).")
        parser.add_argument("--max-seconds", type=int, default=900, help="Run budget, 60–900 seconds (default 900).")
        parser.add_argument("--quiet", action="store_true", help="Suppress successful unchanged/no-work summaries; failures remain visible.")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100 or not 60 <= options["max_seconds"] <= 900:
            raise CommandError("invalid_refresh_bounds", returncode=2)
        if options["container"] is not None and options["container"] < 1:
            raise CommandError("invalid_container_selection", returncode=2)
        deadline = time.monotonic() + options["max_seconds"]
        try:
            if options["dry_run"]:
                self.run_selection(options, deadline, dry_run=True)
            else:
                with batch_lock(), short_database_wait():
                    self.run_selection(options, deadline, dry_run=False)
        except OperationalError:
            raise CommandError("refresh_database_unavailable", returncode=75) from None

    def run_selection(self, options, deadline, *, dry_run):
        eligible = active_journeys()
        if options["container"] is not None:
            eligible = eligible.filter(pk=options["container"])
        # Attempt age provides fairness across bounded runs, even for persistent failures.
        ids = list(eligible.order_by(F("last_refresh_attempt_at").asc(nulls_first=True), "pk")
                   .values_list("pk", flat=True)[:options["limit"] + 1])
        more = len(ids) > options["limit"]
        ids = ids[:options["limit"]]
        summary = dict(selected=len(ids), attempted=0, changed=0, unchanged=0, skipped=0,
                       failed=0, attention=0, deferred=0, more_eligible=more, dry_run=dry_run)
        if not dry_run:
            for pk in ids:
                if deadline - time.monotonic() < REFRESH_RESERVE_SECONDS:
                    break
                summary["attempted"] += 1
                try:
                    result = refresh_container(pk, active_only=True)
                    if not result.ok:
                        summary["failed"] += 1
                    elif result.code == "skipped":
                        summary["skipped"] += 1
                    else:
                        summary["changed" if result.changed else "unchanged"] += 1
                        if result.code == "unknown_status":
                            summary["attention"] += 1
                except Exception:
                    # One unexpected record failure cannot leak data or abort the remaining batch.
                    summary["failed"] += 1
            summary["deferred"] = len(ids) - summary["attempted"]
        actionable = summary["failed"] or summary["attention"] or summary["deferred"] or more
        if dry_run or not options["quiet"] or summary["changed"] or actionable:
            self.stdout.write(json.dumps(summary, sort_keys=True))
        if not dry_run:
            if summary["failed"] or summary["attention"]:
                raise CommandError("refresh_needs_attention", returncode=1)
            if summary["deferred"] or more:
                raise CommandError("refresh_incomplete", returncode=2)
