from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from dashboard.tasks import rollup_metrics_task, run_rollup


class Command(BaseCommand):
    help = (
        "Recomputes precomputed hourly/daily MetricBucket rows. Intended to "
        "run hourly via external cron/systemd timer, same as `ingest "
        "reconcile`. Use --full --sync once after migrating to backfill "
        "existing history."
    )

    def add_arguments(self, parser):
        parser.add_argument("--full", action="store_true", help="Recompute all history.")
        parser.add_argument("--since-hours", type=int, default=48)
        parser.add_argument(
            "--sync", action="store_true",
            help="Run in-process instead of enqueuing (no db_worker required).",
        )

    def handle(self, *args, **options):
        since = None if options["full"] else timezone.now() - timedelta(hours=options["since_hours"])
        if options["sync"]:
            run_rollup(since)
            self.stdout.write(self.style.SUCCESS("Rollup complete."))
        else:
            rollup_metrics_task.enqueue(since.isoformat() if since else None)
            self.stdout.write(self.style.SUCCESS("Enqueued rollup task."))
