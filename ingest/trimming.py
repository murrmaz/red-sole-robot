from django.db.models import Q
from django.utils import timezone


def trim_to_cap(queryset, cap):
    """Keep only the `cap` most-recent rows (by created_utc) in `queryset`,
    deleting the rest -- except rows still protected (protect_until in the
    future) because they're serving as ancestor context for a
    pending/in-progress evaluation. Bounds RawItem to a rolling retention
    window; if inference falls behind, unevaluated items can be evicted
    before ever being scored (IngestLogEntry still records that they were
    ingested, just not evaluated)."""
    ids_to_keep = list(
        queryset.order_by("-created_utc").values_list("id", flat=True)[:cap]
    )
    protected = Q(protect_until__gt=timezone.now())
    deleted, _ = queryset.exclude(Q(id__in=ids_to_keep) | protected).delete()
    return deleted
