def trim_to_cap(queryset, cap):
    """Keep only the `cap` most-recent rows (by created_utc) in `queryset`,
    deleting the rest. Bounds RawItem to a rolling retention window; if
    inference falls behind, unevaluated items can be evicted before ever
    being scored (IngestLogEntry still records that they were ingested,
    just not evaluated)."""
    ids_to_keep = list(
        queryset.order_by("-created_utc").values_list("id", flat=True)[:cap]
    )
    deleted, _ = queryset.exclude(id__in=ids_to_keep).delete()
    return deleted
