from datetime import datetime, timezone
from unittest.mock import patch

from django.test import TestCase

from ingest.models import RawComment
from moderation.inference.base import InferenceResult
from moderation.models import ModerationRecord, ReviewStatus, Verdict
from moderation.tasks import classify_item


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


class ClassifyItemTests(TestCase):
    @patch("moderation.tasks.submit_report")
    @patch("moderation.tasks.get_inference_backend")
    def test_flagged_creates_record_and_reports_and_deletes_raw(
        self, mock_get_backend, mock_submit_report
    ):
        raw = make_raw_comment()
        mock_get_backend.return_value.model_name = "test-model"
        mock_get_backend.return_value.classify.return_value = InferenceResult(
            flagged=True, category="spam", confidence=0.9, rationale="looks like spam"
        )

        classify_item.call("comment", raw.id)

        record = ModerationRecord.objects.get(reddit_fullname="t1_abc123")
        self.assertEqual(record.verdict, Verdict.FLAGGED)
        self.assertEqual(record.category, "spam")
        self.assertTrue(record.reddit_report_submitted)
        self.assertEqual(record.review_status, ReviewStatus.UNREVIEWED)
        mock_submit_report.assert_called_once_with("comment", "abc123", "spam")
        self.assertFalse(RawComment.objects.filter(id=raw.id).exists())

    @patch("moderation.tasks.submit_report")
    @patch("moderation.tasks.get_inference_backend")
    def test_clear_does_not_report_but_still_deletes_raw(
        self, mock_get_backend, mock_submit_report
    ):
        raw = make_raw_comment()
        mock_get_backend.return_value.model_name = "test-model"
        mock_get_backend.return_value.classify.return_value = InferenceResult(
            flagged=False, category="", confidence=0.1, rationale="fine"
        )

        classify_item.call("comment", raw.id)

        record = ModerationRecord.objects.get(reddit_fullname="t1_abc123")
        self.assertEqual(record.verdict, Verdict.CLEAR)
        self.assertFalse(record.reddit_report_submitted)
        mock_submit_report.assert_not_called()
        self.assertFalse(RawComment.objects.filter(id=raw.id).exists())

    @patch("moderation.tasks.get_inference_backend")
    def test_malformed_response_leaves_raw_row_for_retry(self, mock_get_backend):
        raw = make_raw_comment()
        mock_get_backend.return_value.classify.side_effect = ValueError("bad json")

        classify_item.call("comment", raw.id)

        self.assertFalse(ModerationRecord.objects.exists())
        self.assertTrue(RawComment.objects.filter(id=raw.id).exists())

    @patch("moderation.tasks.submit_report")
    @patch("moderation.tasks.get_inference_backend")
    def test_report_failure_is_recorded_but_raw_still_deleted(
        self, mock_get_backend, mock_submit_report
    ):
        raw = make_raw_comment()
        mock_get_backend.return_value.model_name = "test-model"
        mock_get_backend.return_value.classify.return_value = InferenceResult(
            flagged=True, category="spam", confidence=0.9, rationale="spammy"
        )
        mock_submit_report.side_effect = Exception("reddit API down")

        classify_item.call("comment", raw.id)

        record = ModerationRecord.objects.get(reddit_fullname="t1_abc123")
        self.assertFalse(record.reddit_report_submitted)
        self.assertIn("reddit API down", record.reddit_report_error)
        self.assertFalse(RawComment.objects.filter(id=raw.id).exists())
