from django.core.management.base import BaseCommand

from ingest.tasks import ingest_batch


class Command(BaseCommand):
    help = (
        "Enqueues an ingest_batch task on the shared reddit queue, which "
        "fetches new comments/posts, catches anything missed, and trims "
        "the raw queue to its configured cap. Intended to run periodically "
        "via external cron."
    )

    def handle(self, *args, **options):
        ingest_batch.enqueue()
        self.stdout.write(self.style.SUCCESS("Enqueued ingest_batch."))
