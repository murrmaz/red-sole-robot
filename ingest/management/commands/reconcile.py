from django.conf import settings
from django.core.management.base import BaseCommand

from ingest.ingestion import save_comment, save_post
from ingest.models import ItemType, RawItem
from ingest.reddit_client import get_subreddit
from ingest.trimming import trim_to_cap
from evaluate.models import EvaluationRecord


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
            EvaluationRecord.objects.values_list("reddit_fullname", flat=True)
        )

        comments_added = 0
        for comment in subreddit.comments(limit=settings.RECONCILE_COMMENT_FETCH_LIMIT):
            if comment.fullname in already_scored:
                continue
            _, created = save_comment(comment)
            comments_added += created

        posts_added = 0
        for submission in subreddit.new(limit=settings.RECONCILE_POST_FETCH_LIMIT):
            if submission.fullname in already_scored:
                continue
            _, created = save_post(submission)
            posts_added += created

        comments_trimmed = trim_to_cap(
            RawItem.objects.filter(item_type=ItemType.COMMENT), settings.RETAINED_COMMENT_CAP
        )
        posts_trimmed = trim_to_cap(
            RawItem.objects.filter(item_type=ItemType.POST), settings.RETAINED_POST_CAP
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Added {comments_added} comments, {posts_added} posts. "
                f"Trimmed {comments_trimmed} comments, {posts_trimmed} posts."
            )
        )
