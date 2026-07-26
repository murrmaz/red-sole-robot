import logging
import threading

from django.core.management.base import BaseCommand

from ingest.ingestion import save_comment, save_post
from ingest.reddit_client import get_subreddit

logger = logging.getLogger(__name__)


def _stream_comments():
    subreddit = get_subreddit()
    for comment in subreddit.stream.comments(skip_existing=True):
        save_comment(comment)


def _stream_submissions():
    subreddit = get_subreddit()
    for submission in subreddit.stream.submissions(skip_existing=True):
        save_post(submission)


class Command(BaseCommand):
    help = (
        "Long-running process that streams new comments and posts from the "
        "configured subreddit via PRAW and queues them for AI inference."
    )

    def handle(self, *args, **options):
        threads = [
            threading.Thread(target=_stream_comments, daemon=True),
            threading.Thread(target=_stream_submissions, daemon=True),
        ]
        for t in threads:
            t.start()
        self.stdout.write(self.style.SUCCESS("Streaming comments and posts..."))
        for t in threads:
            t.join()
