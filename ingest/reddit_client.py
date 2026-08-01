import threading

import praw
from django.conf import settings

_client = None
_client_lock = threading.Lock()


def get_reddit_client():
    """Process-wide singleton praw.Reddit client. ingest_batch, prepare_item,
    and handle_flagged all run on the single `reddit` django_tasks queue (see
    settings.TASK_QUEUE_REDDIT), processed by exactly one db_worker process,
    so this singleton is in practice shared by every Reddit-touching call in
    the app rather than just within one process. Cross-process coordination
    is intentionally not attempted beyond that queue constraint; prawcore
    reacts to live X-Ratelimit-*/Retry-After headers per-process instead."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = praw.Reddit(
                    client_id=settings.REDDIT_CLIENT_ID,
                    client_secret=settings.REDDIT_CLIENT_SECRET,
                    username=settings.REDDIT_USERNAME,
                    password=settings.REDDIT_PASSWORD,
                    user_agent=settings.REDDIT_USER_AGENT,
                )
    return _client


def get_subreddit(reddit=None):
    reddit = reddit or get_reddit_client()
    return reddit.subreddit(settings.REDDIT_SUBREDDIT)
