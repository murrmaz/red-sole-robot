from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

import ingest.reddit_client as reddit_client
from evaluate.models import EvaluationRecord, ItemType as EvalItemType, Verdict
from ingest.ingestion import save_comment, save_post
from ingest.models import IngestLogEntry, ItemType, RawItem
from ingest.reddit_client import get_reddit_client
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


class FakeSubreddit:
    def __init__(self, comments=(), submissions=()):
        self._comments = list(comments)
        self._submissions = list(submissions)

    def comments(self, limit=None):
        return self._comments

    def new(self, limit=None):
        return self._submissions


def make_evaluation_record(fullname):
    return EvaluationRecord.objects.create(
        item_type=EvalItemType.COMMENT,
        reddit_fullname=fullname,
        subreddit="LouboutinLife",
        author="someuser",
        permalink="/r/LouboutinLife/comments/abc/xyz/",
        content_created_utc=datetime.fromtimestamp(1_700_000_000.0, tz=timezone.utc),
        verdict=Verdict.CLEAR,
    )


class ReconcileCommandTests(TestCase):
    @patch("ingest.management.commands.reconcile.get_subreddit")
    def test_skips_items_already_evaluated(self, mock_get_subreddit):
        make_evaluation_record("t1_c1")
        mock_get_subreddit.return_value = FakeSubreddit(
            comments=[FakeComment(id="c1"), FakeComment(id="c2")],
        )

        call_command("reconcile")

        self.assertFalse(RawItem.objects.filter(fullname="t1_c1").exists())
        self.assertTrue(RawItem.objects.filter(fullname="t1_c2").exists())

    @patch("ingest.management.commands.reconcile.get_subreddit")
    def test_evaluation_lookup_is_bounded_by_fetch_size_not_table_size(
        self, mock_get_subreddit
    ):
        for i in range(500):
            make_evaluation_record(f"t1_old{i}")
        mock_get_subreddit.return_value = FakeSubreddit(
            comments=[FakeComment(id="c1")],
        )

        with CaptureQueriesContext(connection) as queries:
            call_command("reconcile")

        evaluation_lookup_queries = [
            q for q in queries.captured_queries
            if "evaluate_evaluationrecord" in q["sql"].lower() and "select" in q["sql"].lower()
        ]
        self.assertEqual(len(evaluation_lookup_queries), 1)
        self.assertIn("t1_c1", evaluation_lookup_queries[0]["sql"])
        self.assertNotIn("t1_old0", evaluation_lookup_queries[0]["sql"])


class TrimToCapTests(TestCase):
    def test_keeps_only_most_recent(self):
        base = 1_700_000_000.0
        for i in range(10):
            save_comment(FakeComment(id=f"c{i}", created_utc=base + i))

        deleted = trim_to_cap(RawItem.objects.filter(item_type=ItemType.COMMENT), 3)

        self.assertEqual(deleted, 7)
        remaining_fullnames = set(RawItem.objects.values_list("fullname", flat=True))
        self.assertEqual(remaining_fullnames, {"t1_c7", "t1_c8", "t1_c9"})


class RedditClientSingletonTests(TestCase):
    def setUp(self):
        reddit_client._client = None
        self.addCleanup(setattr, reddit_client, "_client", None)

    @patch("ingest.reddit_client.praw.Reddit")
    def test_returns_same_instance(self, mock_reddit_cls):
        first = get_reddit_client()
        second = get_reddit_client()

        mock_reddit_cls.assert_called_once()
        self.assertIs(first, second)

    @patch("ingest.reddit_client.praw.Reddit")
    def test_thread_safe_construction(self, mock_reddit_cls):
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(lambda _: get_reddit_client(), range(20)))

        mock_reddit_cls.assert_called_once()
        self.assertTrue(all(r is results[0] for r in results))
