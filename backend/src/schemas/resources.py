from datetime import datetime, timezone


def utc(value: datetime | None):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def dataset_view(dataset, include_rows=False):
    item = {
        "id": dataset.id, "name": dataset.name, "count": len(dataset.rows),
        "checksum": dataset.checksum, "author": dataset.author, "created_at": utc(dataset.created_at),
    }
    if include_rows:
        item["rows"] = dataset.rows
    return item


def run_view(run, include_result=False):
    spectrum_label = getattr(run, "spectrum_version", None)
    spectrum_id = getattr(run, "spectrum_version_id", None)
    item = {
        "id": run.id, "dataset_id": run.dataset_id, "label": run.label, "parameter": run.parameter,
        "spectrum_version": spectrum_label,
        "spectrum_version_id": spectrum_id,
        "reference_spectrum_version": spectrum_label,
        "reference_spectrum_version_id": spectrum_id,
        "status": run.status, "error": run.error, "actor": run.actor,
        "created_at": utc(run.created_at), "started_at": utc(run.started_at),
        "finished_at": utc(run.finished_at),
    }
    if include_result:
        item["result"] = run.result
    if include_result and isinstance(run.result, dict):
        # Persisted results remain self-describing even if a pre-upgrade row has
        # null pinning columns.
        for key in (
            "spectrum_version",
            "spectrum_version_id",
            "reference_spectrum_version",
            "reference_spectrum_version_id",
        ):
            if item.get(key) is None and run.result.get(key) is not None:
                item[key] = run.result[key]
    return item


def spectrum_view(version, include_detail=True):
    status_labels = {
        "active": "在用",
        "superseded": "已替换",
        "rejected": "未启用",
        "pending": "待生效",
    }
    item = {
        "id": version.id,
        "seq": version.seq,
        "candidate_number": version.seq,
        "active_number": version.active_number,
        "version_number": version.active_number if version.active_number is not None else version.seq,
        "version": version.version,
        "version_label": version.version or f"candidate-{version.seq}",
        "candidate_version": f"c{version.seq}",
        "spectrum_version": version.version or f"c{version.seq}",
        "label": version.label,
        "name": version.label,
        "status": version.status,
        "status_label": status_labels.get(version.status, version.status),
        "active": version.status == "active" and bool(version.accepted),
        "is_active": version.status == "active" and bool(version.accepted),
        "enabled": version.status == "active" and bool(version.accepted),
        "accepted": bool(version.accepted),
        "passed": bool(version.accepted),
        "allowed": bool(version.accepted),
        "source_dataset_id": version.source_dataset_id,
        "dataset_id": version.source_dataset_id,
        "holdout_dataset_id": version.holdout_dataset_id,
        "holdout_checksum": version.holdout_checksum,
        "base_version_id": version.base_version_id,
        "threshold": version.threshold,
        "parameter": version.threshold,
        "gate": version.gate,
        "reason": version.reason,
        "actor": version.actor,
        "created_at": utc(version.created_at),
        "activated_at": utc(version.activated_at),
        "surface_metrics": version.surface_metrics,
        "residual_maxima": version.surface_metrics,
        "max_residual_by_surface": version.surface_metrics,
        "baseline_metrics": version.baseline_metrics,
        "active_metrics": version.baseline_metrics,
    }
    if include_detail:
        item.update({
            "state": version.state,
            "reference_profiles": (version.state or {}).get("records") if version.state else None,
            "comparison": version.comparison,
            "gate_detail": version.gate_detail,
            "holdout_rows": version.holdout_rows,
        })
    return item


def review_view(review):
    return {
        "id": review.id, "run_id": review.run_id, "decision": review.decision,
        "samples": review.samples, "note": review.note, "reviewer": review.reviewer,
        "created_at": utc(review.created_at),
    }


def audit_view(event):
    return {"actor": event.actor, "action": event.action, "subject": event.subject, "created_at": utc(event.created_at)}
