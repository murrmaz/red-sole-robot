from datetime import datetime, timezone
from unittest.mock import patch

from django.test import TestCase

from evaluate.backends.base import InferenceResult
from evaluate.models import EvaluationRecord, Verdict
from evaluate.tasks import evaluate_item
from ingest.models import RawComment


def make_raw_comment(**overrides):
    defaults = dict(
        reddit_id="abc123",
        subreddit="LouboutinLife",
        author="someuser",
        body="hello world",
        permalink="/r/LouboutinLife/comments/abc/xyz/",
        link_id="t3_abc",
        parent_id="t3_abc",
        created_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RawComment.objects.create(**defaults)


class EvaluateItemTests(TestCase):
    @patch("actions.tasks.handle_flagged")
    @patch("evaluate.tasks.get_inference_backend")
    def test_flagged_creates_record_enqueues_handle_flagged_and_deletes_raw(
        self, mock_get_backend, mock_handle_flagged
    ):
        raw = make_raw_comment()
        mock_get_backend.return_value.model_name = "test-model"
        mock_get_backend.return_value.classify.return_value = InferenceResult(
            flagged=True, category="spam", confidence=0.9, rationale="looks like spam"
        )

        evaluate_item.call("comment", raw.id)

        record = EvaluationRecord.objects.get(reddit_fullname="t1_abc123")
        self.assertEqual(record.verdict, Verdict.FLAGGED)
        self.assertEqual(record.category, "spam")
        mock_handle_flagged.enqueue.assert_called_once_with(record.id)
        self.assertFalse(RawComment.objects.filter(id=raw.id).exists())

    @patch("actions.tasks.handle_flagged")
    @patch("evaluate.tasks.get_inference_backend")
    def test_clear_does_not_enqueue_but_still_deletes_raw(
        self, mock_get_backend, mock_handle_flagged
    ):
        raw = make_raw_comment()
        mock_get_backend.return_value.model_name = "test-model"
        mock_get_backend.return_value.classify.return_value = InferenceResult(
            flagged=False, category="", confidence=0.1, rationale="fine"
        )

        evaluate_item.call("comment", raw.id)

        record = EvaluationRecord.objects.get(reddit_fullname="t1_abc123")
        self.assertEqual(record.verdict, Verdict.CLEAR)
        mock_handle_flagged.enqueue.assert_not_called()
        self.assertFalse(RawComment.objects.filter(id=raw.id).exists())

    @patch("evaluate.tasks.get_inference_backend")
    def test_malformed_response_leaves_raw_row_for_retry(self, mock_get_backend):
        raw = make_raw_comment()
        mock_get_backend.return_value.classify.side_effect = ValueError("bad json")

        evaluate_item.call("comment", raw.id)

        self.assertFalse(EvaluationRecord.objects.exists())
        self.assertTrue(RawComment.objects.filter(id=raw.id).exists())
