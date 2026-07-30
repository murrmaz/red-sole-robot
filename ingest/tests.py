from dataclasses import dataclass
from datetime import datetime, timezone

from django.test import TestCase

from ingest.ingestion import save_comment, save_post
from ingest.models import IngestLogEntry, ItemType, RawItem
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

    @property
    def fullname(self):
        return f"t1_{self.id}"


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

    @property
    def fullname(self):
        return f"t3_{self.id}"


class SaveCommentTests(TestCase):
    def test_dedups_by_fullname(self):
        comment = FakeComment(id="abc123")
        save_comment(comment)
        save_comment(comment)
        self.assertEqual(RawItem.objects.filter(fullname="t1_abc123").count(), 1)
        self.assertEqual(IngestLogEntry.objects.filter(fullname="t1_abc123").count(), 1)

    def test_stores_expected_fields(self):
        comment = FakeComment(id="abc123")
        save_comment(comment)
        raw = RawItem.objects.get(fullname="t1_abc123")
        self.assertEqual(raw.item_type, ItemType.COMMENT)
        self.assertEqual(raw.body, "hello world")
        self.assertEqual(raw.subreddit, "LouboutinLife")
        self.assertEqual(
            raw.created_utc, datetime.fromtimestamp(1_700_000_000.0, tz=timezone.utc)
        )


class SavePostTests(TestCase):
    def test_dedups_by_fullname(self):
        submission = FakeSubmission(id="post1")
        save_post(submission)
        save_post(submission)
        self.assertEqual(RawItem.objects.filter(fullname="t3_post1").count(), 1)
        self.assertEqual(IngestLogEntry.objects.filter(fullname="t3_post1").count(), 1)


class TrimToCapTests(TestCase):
    def test_keeps_only_most_recent(self):
        base = 1_700_000_000.0
        for i in range(10):
            save_comment(FakeComment(id=f"c{i}", created_utc=base + i))

        deleted = trim_to_cap(RawItem.objects.filter(item_type=ItemType.COMMENT), 3)

        self.assertEqual(deleted, 7)
        remaining_fullnames = set(RawItem.objects.values_list("fullname", flat=True))
        self.assertEqual(remaining_fullnames, {"t1_c7", "t1_c8", "t1_c9"})
