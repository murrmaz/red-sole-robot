from django.conf import settings
from django_tasks import task

from evaluate.models import EvaluationRecord
from ingest.ingestion import save_comment, save_post
from ingest.models import ItemType, RawItem
from ingest.reddit_client import get_subreddit
from ingest.trimming import trim_to_cap


@task(queue_name=settings.TASK_QUEUE_REDDIT)
def ingest_batch() -> None:
    """Fetch a fixed number of recent comments/posts, insert any missing
    from the raw queue, and trim the raw queue down to its configured cap.
    Runs on the shared `reddit` queue so its PRAW calls share the process-
    wide client with preparation and actions. Triggered periodically by the
    `ingest` management command via external cron."""
    subreddit = get_subreddit()
    comments = list(subreddit.comments(limit=settings.INGEST_COMMENT_FETCH_LIMIT))
    submissions = list(subreddit.new(limit=settings.INGEST_POST_FETCH_LIMIT))

    # Only check evaluation status for the handful of items just fetched,
    # not the whole (permanent, ever-growing) EvaluationRecord table.
    fetched_fullnames = [c.fullname for c in comments] + [s.fullname for s in submissions]
    already_scored = set(
        EvaluationRecord.objects.filter(reddit_fullname__in=fetched_fullnames)
        .values_list("reddit_fullname", flat=True)
    )

    for comment in comments:
        if comment.fullname in already_scored:
            continue
        save_comment(comment)

    for submission in submissions:
        if submission.fullname in already_scored:
            continue
        save_post(submission)

    trim_to_cap(RawItem.objects.filter(item_type=ItemType.COMMENT), settings.RETAINED_COMMENT_CAP)
    trim_to_cap(RawItem.objects.filter(item_type=ItemType.POST), settings.RETAINED_POST_CAP)
