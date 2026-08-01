from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import prawcore
from django.test import TestCase, override_settings

from ingest.models import ItemType, RawItem
from preparation.context import build_context
from preparation.tasks import MAX_RETRY_ATTEMPTS, prepare_item


def make_raw_comment(**overrides):
    defaults = dict(
        item_type=ItemType.COMMENT,
        reddit_id="c",
        subreddit="LouboutinLife",
        author="someuser",
        body="a comment",
        permalink="/r/LouboutinLife/comments/abc/xyz/",
        link_id="t3_root",
        parent_id="t3_root",
        created_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RawItem.objects.create(**defaults)


def make_raw_post(**overrides):
    defaults = dict(
        item_type=ItemType.POST,
        fullname="t3_root",
        reddit_id="root",
        subreddit="LouboutinLife",
        author="someuser",
        title="a post",
        selftext="post body",
        permalink="/r/LouboutinLife/comments/root/",
        created_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RawItem.objects.create(**defaults)


@dataclass
class FakeComment:
    id: str
    subreddit: str = "LouboutinLife"
    author: str = "someuser"
    body: str = "fetched comment"
    permalink: str = "/r/LouboutinLife/comments/abc/xyz/"
    link_id: str = "t3_root"
    parent_id: str = "t3_root"
    created_utc: float = 1_700_000_000.0

    @property
    def fullname(self):
        return f"t1_{self.id}"


class BuildContextTests(TestCase):
    def test_post_returns_empty_context_without_praw_call(self):
        post = make_raw_post()
        self.assertEqual(build_context(post), "")

    def test_walks_already_retained_ancestors(self):
        make_raw_post()
        c1 = make_raw_comment(fullname="t1_c1", body="first reply", parent_id="t3_root")
        c2 = make_raw_comment(fullname="t1_c2", body="second reply", parent_id="t1_c1")

        context = build_context(c2)

        self.assertEqual(context, "a post\n\npost body\n---\nfirst reply")

    @patch("preparation.context.get_reddit_client")
    def test_fetches_and_persists_missing_ancestor(self, mock_get_client):
        make_raw_post()
        c2 = make_raw_comment(fullname="t1_c2", parent_id="t1_missing")
        mock_get_client.return_value.comment.return_value = FakeComment(
            id="missing", body="fetched parent", parent_id="t3_root"
        )

        context = build_context(c2)

        self.assertIn("fetched parent", context)
        self.assertTrue(RawItem.objects.filter(fullname="t1_missing").exists())
        mock_get_client.return_value.comment.assert_called_once_with("missing")

    @patch("preparation.context.get_reddit_client")
    def test_does_not_refetch_once_cached(self, mock_get_client):
        make_raw_post()
        c2 = make_raw_comment(fullname="t1_c2", parent_id="t1_missing")
        mock_get_client.return_value.comment.return_value = FakeComment(
            id="missing", body="fetched parent", parent_id="t3_root"
        )
        build_context(c2)

        sibling = make_raw_comment(fullname="t1_c3", parent_id="t1_missing")
        build_context(sibling)

        mock_get_client.return_value.comment.assert_called_once_with("missing")

    def test_depth_cap_stops_the_walk(self):
        make_raw_post()
        make_raw_comment(fullname="t1_c1", body="level 1", parent_id="t3_root")
        make_raw_comment(fullname="t1_c2", body="level 2", parent_id="t1_c1")
        c3 = make_raw_comment(fullname="t1_c3", body="level 3", parent_id="t1_c2")

        with override_settings(PREPARATION_MAX_ANCESTOR_DEPTH=1):
            context = build_context(c3)

        self.assertEqual(context, "level 2")

    @patch("preparation.context.get_reddit_client")
    def test_deleted_ancestor_stops_walk_without_error(self, mock_get_client):
        c2 = make_raw_comment(fullname="t1_c2", parent_id="t1_missing")
        response = Mock(status_code=404)
        mock_get_client.return_value.comment.side_effect = prawcore.exceptions.NotFound(response)

        context = build_context(c2)

        self.assertEqual(context, "")

    @patch("preparation.context.get_reddit_client")
    def test_transient_error_raises_when_not_best_effort(self, mock_get_client):
        c2 = make_raw_comment(fullname="t1_c2", parent_id="t1_missing")
        response = Mock(status_code=503, text="")
        response.headers.get.return_value = None
        mock_get_client.return_value.comment.side_effect = prawcore.exceptions.ServerError(response)

        with self.assertRaises(prawcore.exceptions.ServerError):
            build_context(c2, best_effort=False)

    @patch("preparation.context.get_reddit_client")
    def test_transient_error_degrades_gracefully_in_best_effort_mode(self, mock_get_client):
        c2 = make_raw_comment(fullname="t1_c2", parent_id="t1_missing")
        response = Mock(status_code=503, text="")
        response.headers.get.return_value = None
        mock_get_client.return_value.comment.side_effect = prawcore.exceptions.ServerError(response)

        context = build_context(c2, best_effort=True)

        self.assertEqual(context, "")


class PrepareItemTaskTests(TestCase):
    @patch("evaluate.tasks.evaluate_item")
    @patch("preparation.tasks.build_context")
    def test_enqueues_evaluate_item_with_context(self, mock_build_context, mock_evaluate_item):
        raw = make_raw_comment()
        mock_build_context.return_value = "some context"

        prepare_item.call(raw.id)

        mock_evaluate_item.enqueue.assert_called_once_with(raw.id, context="some context")

    @patch("preparation.tasks.build_context")
    def test_transient_error_requeues(self, mock_build_context):
        raw = make_raw_comment()
        response = Mock(status_code=503, text="")
        response.headers.get.return_value = None
        mock_build_context.side_effect = prawcore.exceptions.ServerError(response)

        with patch("django_tasks.base.Task.using") as mock_using:
            prepare_item.call(raw.id, attempt=0)

        mock_using.assert_called_once()
        self.assertIn("run_after", mock_using.call_args.kwargs)
        mock_using.return_value.enqueue.assert_called_once_with(raw.id, attempt=1)

    def test_missing_raw_item_is_a_noop(self):
        prepare_item.call(999999)

    @patch("preparation.tasks.build_context")
    def test_last_attempt_uses_best_effort(self, mock_build_context):
        raw = make_raw_comment()
        mock_build_context.return_value = ""

        prepare_item.call(raw.id, attempt=MAX_RETRY_ATTEMPTS - 1)

        mock_build_context.assert_called_once_with(raw, best_effort=True)
