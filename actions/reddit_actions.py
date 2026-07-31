import prawcore

from ingest.reddit_client import get_reddit_client

TRANSIENT_EXCEPTIONS = (
    prawcore.exceptions.TooManyRequests,
    prawcore.exceptions.RequestException,
    prawcore.exceptions.ServerError,
)


def submit_report(item_type, reddit_id, reason):
    """Submit a native Reddit report so a flagged item shows up in the
    subreddit's own mod queue, in addition to our review UI."""
    reddit = get_reddit_client()
    if item_type == "comment":
        target = reddit.comment(reddit_id)
    else:
        target = reddit.submission(reddit_id)
    target.report(reason)


def retry_delay_seconds(exc: Exception, attempt: int) -> float:
    """How long to wait before retrying a transient error. Honors
    prawcore's own Retry-After header when present, else exponential
    backoff capped at 15 minutes."""
    retry_after = getattr(exc, "retry_after", None)
    if retry_after:
        return float(retry_after)
    return min(60 * (2**attempt), 900)
