from ingest.reddit_client import get_reddit_client


def submit_report(item_type, reddit_id, reason):
    """Submit a native Reddit report so a flagged item shows up in the
    subreddit's own mod queue, in addition to our review UI."""
    reddit = get_reddit_client()
    if item_type == "comment":
        target = reddit.comment(reddit_id)
    else:
        target = reddit.submission(reddit_id)
    target.report(reason)
