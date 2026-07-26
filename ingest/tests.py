from dataclasses import dataclass
from datetime import datetime, timezone

from django.test import TestCase

from ingest.ingestion import save_comment, save_post
from ingest.models import RawComment, RawPost
from ingest.trimming import trim_to_cap


@dataclass
class FakeComment:
    id: str
    subreddit: str = "LouboutinLife"
    author: str = "someuser"
    body: str = "hello world"
    permalink: str = "/r/LouboutinLife/comments/abc/xyz/"
    link_id: str = "t3_abc"
    parent_id: str = "t3_abc"
    created_utc: float = 1_700_000_000.0


@dataclass
class FakeSubmission:
    id: str
    subreddit: str = "LouboutinLife"
    author: str = "someuser"
    title: str = "a post"
    selftext: str = "body text"
    url: str = "https://example.com"
    permalink: str = "/r/LouboutinLife/comments/abc/"
    created_utc: float = 1_700_000_000.0


class SaveCommentTests(TestCase):
    def test_dedups_by_reddit_id(self):
        comment = FakeComment(id="abc123")
        save_comment(comment)
        save_comment(comment)
        self.assertEqual(RawComment.objects.filter(reddit_id="abc123").count(), 1)

    def test_stores_expected_fields(self):
        comment = FakeComment(id="abc123")
        save_comment(comment)
        raw = RawComment.objects.get(reddit_id="abc123")
        self.assertEqual(raw.body, "hello world")
        self.assertEqual(raw.subreddit, "LouboutinLife")
        self.assertEqual(
            raw.created_utc, datetime.fromtimestamp(1_700_000_000.0, tz=timezone.utc)
        )


class SavePostTests(TestCase):
    def test_dedups_by_reddit_id(self):
        submission = FakeSubmission(id="post1")
        save_post(submission)
        save_post(submission)
        self.assertEqual(RawPost.objects.filter(reddit_id="post1").count(), 1)


class TrimToCapTests(TestCase):
    def test_keeps_only_most_recent(self):
        base = 1_700_000_000.0
        for i in range(10):
            save_comment(FakeComment(id=f"c{i}", created_utc=base + i))

        deleted = trim_to_cap(RawComment, 3)

        self.assertEqual(deleted, 7)
        remaining_ids = set(RawComment.objects.values_list("reddit_id", flat=True))
        self.assertEqual(remaining_ids, {"c7", "c8", "c9"})
