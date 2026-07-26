from django.conf import settings
from django.core.management.base import BaseCommand

from ingest.ingestion import save_comment, save_post
from ingest.models import RawComment, RawPost
from ingest.reddit_client import get_subreddit
from ingest.trimming import trim_to_cap
from moderation.models import ModerationRecord


class Command(BaseCommand):
    help = (
        "Fetches a fixed number of recent comments/posts, inserts any "
        "missing from the raw queue (catching anything the stream missed), "
        "and trims the raw queue down to its configured cap. Intended to "
        "run hourly."
    )

    def handle(self, *args, **options):
        subreddit = get_subreddit()
        already_scored = set(
            ModerationRecord.objects.values_list("reddit_fullname", flat=True)
        )

        comments_added = 0
        for comment in subreddit.comments(limit=settings.RECONCILE_COMMENT_FETCH_LIMIT):
            if f"t1_{comment.id}" in already_scored:
                continue
            _, created = save_comment(comment)
            comments_added += created

        posts_added = 0
        for submission in subreddit.new(limit=settings.RECONCILE_POST_FETCH_LIMIT):
            if f"t3_{submission.id}" in already_scored:
                continue
            _, created = save_post(submission)
            posts_added += created

        comments_trimmed = trim_to_cap(RawComment, settings.QUEUE_COMMENT_CAP)
        posts_trimmed = trim_to_cap(RawPost, settings.QUEUE_POST_CAP)

        self.stdout.write(
            self.style.SUCCESS(
                f"Added {comments_added} comments, {posts_added} posts. "
                f"Trimmed {comments_trimmed} comments, {posts_trimmed} posts."
            )
        )
