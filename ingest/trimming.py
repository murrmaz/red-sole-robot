def trim_to_cap(model, cap):
    """Keep only the `cap` most-recent rows (by created_utc), deleting the
    rest. Used by `reconcile` to bound the pending queue when inference
    can't keep up; per design, overflowing unprocessed items are simply
    dropped — there is no audit trail for them."""
    ids_to_keep = list(
        model.objects.order_by("-created_utc").values_list("id", flat=True)[:cap]
    )
    deleted, _ = model.objects.exclude(id__in=ids_to_keep).delete()
    return deleted
