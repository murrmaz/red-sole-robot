import praw
from django.conf import settings


def get_reddit_client():
    return praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        username=settings.REDDIT_USERNAME,
        password=settings.REDDIT_PASSWORD,
        user_agent=settings.REDDIT_USER_AGENT,
    )


def get_subreddit(reddit=None):
    reddit = reddit or get_reddit_client()
    return reddit.subreddit(settings.REDDIT_SUBREDDIT)
