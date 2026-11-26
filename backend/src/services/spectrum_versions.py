from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Mapping

import numpy as np
from fastapi import HTTPException
from sqlalchemy import func, select

from src.business.factorization import ReferenceSpectra
from src.business.profile import PROFILE
from src.business.spectra import matrix
from src.business.spectrum_versions import (
    compare_maxima,
    first_set_gate,
    state_from_profiles,
    surface_residual_maxima,
)
from src.config.settings import Session
from src.models.dataset import Dataset
from src.models.spectrum import SpectrumVersion
from src.schemas.resources import spectrum_view
from src.services.audit import record
from src.services.datasets import save_in
from src.utils.csv_data import digest, parse_csv

_lock = threading.RLock()


def require(db, version_id: str) -> SpectrumVersion:
    item = db.get(SpectrumVersion, version_id)
    if item is None:
        raise HTTPException(404, "参考谱版本不存在。")
    return item


def active_record(db, for_update: bool = False) -> SpectrumVersion | None:
    stmt = (
        select(SpectrumVersion)
        .where(SpectrumVersion.status == "active", SpectrumVersion.accepted.is_(True))
        .order_by(SpectrumVersion.seq.desc(), SpectrumVersion.id.desc())
        .limit(1)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def active_reference(db):
    """Return the ORM-pinned active version for a new run, if one exists."""
    return active_record(db, for_update=False)


def list_versions():
    with Session() as db:
        rows = db.scalars(select(SpectrumVersion).order_by(SpectrumVersion.seq.desc(), SpectrumVersion.id.desc()))
        return [spectrum_view(row, include_detail=False) for row in rows]


def get_version(version_id: str):
    with Session() as db:
        return spectrum_view(require(db, version_id))


def get_active():
    with Session() as db:
        item = active_record(db)
        return spectrum_view(item) if item else None


def _as_mapping(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, Mapping):
        return dict(payload)
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True)
    return dict(payload)


def _first_key(payload: Mapping[str, Any], *keys: str):
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _threshold(payload: Mapping[str, Any]):
    control = PROFILE["parameter"]
    raw = _first_key(payload, "threshold", "retest_threshold", "recheck_pp", "parameter", "max_residual_threshold")
    if raw is None:
        return float(control["default"])
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "复测门槛必须是数字。") from exc
    if not control["min"] <= value <= control["max"]:
        raise HTTPException(422, f"「{control['label']}」超出允许范围。")
    return value


def _dataset(db, dataset_id: str | None) -> Dataset | None:
    if not dataset_id:
        return None
    item = db.get(Dataset, str(dataset_id))
    if item is None:
        raise HTTPException(404, "数据版本不存在。")
    return item


def _parse_csv_text(contents: str | None) -> list[dict] | None:
    if not contents:
        return None
    try:
        return parse_csv(contents, PROFILE["columns"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _select_split(rows: list[dict], split: str) -> list[dict]:
    return [row for row in rows if row.get("split") == split]


def _state_from_profiles(profiles: Any) -> dict:
    try:
        return state_from_profiles(profiles)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _reference_model(db, payload: Mapping[str, Any]):
    explicit_state = _first_key(payload, "state", "spectrum_state")
    if explicit_state is not None:
        state = explicit_state.get("state", explicit_state) if isinstance(explicit_state, Mapping) else explicit_state
        try:
            model = ReferenceSpectra.restore(state)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return model, None

    components = _first_key(payload, "components")
    if components is not None:
        try:
            model = ReferenceSpectra.restore({"components": components})
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return model, None

    profiles = _first_key(
        payload,
        "reference_profiles",
        "new_reference_profiles",
        "candidate_profiles",
        "profiles",
        "spectra",
        "spectrum_profiles",
        "new_spectrum",
        "candidate_spectrum",
        "spectrum",
    )
    if profiles is not None:
        state = _state_from_profiles(profiles)
        return ReferenceSpectra.restore(state), None

    dataset_id = _first_key(
        payload, "reference_dataset_id", "reference_id", "ref_dataset_id", "dataset_id", "source_dataset_id"
    )
    dataset = _dataset(db, dataset_id)

    rows = None
    csv_text = _first_key(payload, "reference_csv", "csv", "dataset_csv", "csv_content", "contents")
    if csv_text:
        rows = _parse_csv_text(csv_text)
        # A full CSV may also be persisted for auditability.
        if dataset is None and _first_key(payload, "persist_csv", "save_dataset"):
            name = _first_key(payload, "name", "label") or "参考谱批次"
            dataset, _ = save_in(db, str(name)[:100], rows, payload.get("actor", "analyst"))
    if rows is None and dataset is not None:
        rows = dataset.rows
    explicit_rows = _first_key(payload, "reference_rows", "references")
    if explicit_rows is not None:
        rows = explicit_rows

    reference_rows = _select_split(rows or [], "参照")
    if len(reference_rows) < 18:
        raise HTTPException(422, "参照至少需要 18 片，才能拟合三种参考谱。")
    values = matrix(reference_rows)
    if np.any(values.sum(axis=1) == 0):
        raise HTTPException(422, "参照内有样片的六波段均为零，请检查暗电流扣除。")
    if np.linalg.matrix_rank(values) < 3:
        raise HTTPException(422, "参照谱有效秩小于 3，无法提取三种参考谱。")
    try:
        model = ReferenceSpectra(values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return model, getattr(dataset, "id", None)


def _requested_holdout_rows(db, payload: Mapping[str, Any]):
    rows = _first_key(payload, "holdout_rows", "review_rows", "validation_rows", "check_rows")
    if rows is not None:
        return list(rows)

    csv_text = _first_key(
        payload, "holdout_csv", "review_csv", "validation_csv", "csv", "dataset_csv", "csv_content", "contents"
    )
    if csv_text:
        parsed = _parse_csv_text(csv_text)
        return _select_split(parsed or [], "复核") or parsed or []

    dataset_id = _first_key(
        payload,
        "holdout_dataset_id",
        "review_dataset_id",
        "validation_dataset_id",
        "holdout_id",
        "review_id",
    )
    dataset = _dataset(db, dataset_id)
    if dataset is not None:
        return _select_split(dataset.rows, "复核") or list(dataset.rows)

    # The common one-dataset workflow: dataset_id contains references and the
    # independent review films together.
    source_id = _first_key(payload, "dataset_id", "source_dataset_id", "reference_dataset_id")
    source = _dataset(db, source_id)
    if source is not None:
        return _select_split(source.rows, "复核")
    return None


def _same_holdout(stored, requested):
    if not requested:
        return True
    if digest(requested) == digest(stored):
        return True
    if len(requested) != len(stored):
        return False
    try:
        stored_by_id = {row["sample_id"]: row for row in stored}
        requested_by_id = {row["sample_id"]: row for row in requested}
        if set(stored_by_id) != set(requested_by_id):
            return False
        ids = sorted(stored_by_id)
        left = matrix([stored_by_id[sample_id] for sample_id in ids])
        right = matrix([requested_by_id[sample_id] for sample_id in ids])
        return left.shape == right.shape and bool(np.allclose(left, right, atol=1e-9, rtol=0.0))
    except (KeyError, TypeError, ValueError):
        return False


def _holdout_for_gate(db, payload, active: SpectrumVersion | None):
    requested = _requested_holdout_rows(db, payload)
    if active is not None:
        stored = active.holdout_rows
        if not stored and active.holdout_dataset_id:
            stored = _select_split(_dataset(db, active.holdout_dataset_id).rows, "复核")
        if not stored:
            raise HTTPException(409, "在用参考谱没有保存独立复核片，无法按同一批复核片比较。")
        if requested and not _same_holdout(stored, requested):
            raise HTTPException(422, "新旧谱必须使用同一批独立复核片。")
        return stored
    if not requested:
        raise HTTPException(422, "首套谱必须提供独立复核片或包含复核分组的数据版本。")
    return requested


def _metrics(model, holdout):
    try:
        return surface_residual_maxima(model, holdout)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _next_seq(db):
    return int(db.scalar(select(func.coalesce(func.max(SpectrumVersion.seq), 0))) or 0) + 1


def _next_active_number(db):
    return int(db.scalar(select(func.coalesce(func.max(SpectrumVersion.active_number), 0))) or 0) + 1


def _create_version_row(db, payload, actor, model, source_dataset_id, threshold, holdout, metrics,
                        active, gate):
    accepted = bool(gate["allowed"])
    seq = _next_seq(db)
    active_number = _next_active_number(db) if accepted else None
    version = f"v{active_number}" if accepted else None
    now = datetime.utcnow()
    item = SpectrumVersion(
        seq=seq,
        active_number=active_number,
        version=version,
        label=_first_key(payload, "label", "name", "version_label") or f"参考谱 {seq}",
        status="active" if accepted else "rejected",
        source_dataset_id=source_dataset_id,
        holdout_dataset_id=_first_key(payload, "holdout_dataset_id", "review_dataset_id"),
        holdout_checksum=digest(holdout) if holdout else None,
        holdout_rows=holdout,
        state=model.snapshot(),
        surface_metrics=metrics,
        baseline_metrics=gate.get("active_metrics") or (active.surface_metrics if active else None),
        gate_detail=gate,
        comparison=gate if active is not None else None,
        gate=gate.get("rule"),
        threshold=threshold,
        accepted=accepted,
        reason=gate.get("reason") or None,
        base_version_id=getattr(active, "id", None),
        actor=actor,
        activated_at=now if accepted else None,
    )
    db.add(item)
    db.flush()
    return item


def preview_candidate(payload: Any):
    """Run the same gate without persisting a candidate version."""
    body = _as_mapping(payload)
    container = body.get("candidate")
    if isinstance(container, Mapping):
        body = {**dict(container), **body}
    threshold = _threshold(body)
    with Session.begin() as db:
        active = active_record(db, for_update=False)
        model, _ = _reference_model(db, body)
        holdout = _holdout_for_gate(db, body, active)
        metrics = _metrics(model, holdout)
        if active is None:
            return first_set_gate(metrics, threshold)
        baseline = active.surface_metrics or _metrics(ReferenceSpectra.restore(active.state), holdout)
        gate = compare_maxima(metrics, baseline)
        gate["active_metrics"] = dict(baseline)
        return gate


def submit_candidate(payload: Any, actor: str = "analyst"):
    body = _as_mapping(payload)
    for container_key in ("candidate", "candidate_version", "spectrum_set", "data"):
        container = body.get(container_key)
        if isinstance(container, Mapping):
            # Top-level authentication/holdout fields win over nested values.
            body = {**dict(container), **body}
    body.setdefault("actor", actor)
    threshold = _threshold(body)
    with _lock:
        with Session.begin() as db:
            active = active_record(db, for_update=True)
            model, source_dataset_id = _reference_model(db, body)
            holdout = _holdout_for_gate(db, body, active)
            metrics = _metrics(model, holdout)
            if active is None:
                gate = first_set_gate(metrics, threshold)
            else:
                baseline = active.surface_metrics or _metrics(ReferenceSpectra.restore(active.state), holdout)
                gate = compare_maxima(metrics, baseline)
                gate["active_metrics"] = dict(baseline)
            item = _create_version_row(db, body, actor, model, source_dataset_id, threshold,
                                       holdout, metrics, active, gate)
            if gate["allowed"] and active is not None:
                active.status = "superseded"
                active.activated_at = active.activated_at or datetime.utcnow()
            record(db, actor, "spectrum_submitted", item.id)
            record(db, actor, "spectrum_activated" if gate["allowed"] else "spectrum_rejected", item.id)
            return spectrum_view(item)


def activate_candidate(version_id: str, actor: str = "analyst", threshold: float | None = None):
    rejection = None
    result_view = None
    with _lock:
        with Session.begin() as db:
            item = require(db, version_id)
            if item.status == "active" and item.accepted:
                result_view = spectrum_view(item)
            else:
                active = active_record(db, for_update=True)
                if active is not None and active.id == item.id:
                    item.status = "active"
                    item.accepted = True
                    result_view = spectrum_view(item)
                else:
                    holdout = item.holdout_rows
                    if active is not None:
                        holdout = active.holdout_rows or holdout
                    if not holdout:
                        raise HTTPException(422, "该参考谱版本没有保存可用于生效校验的独立复核片。")
                    model = ReferenceSpectra.restore(item.state)
                    metrics = _metrics(model, holdout)
                    gate_threshold = float(threshold if threshold is not None else item.threshold or PROFILE["parameter"]["default"])
                    if active is None:
                        gate = first_set_gate(metrics, gate_threshold)
                    else:
                        baseline = active.surface_metrics or _metrics(ReferenceSpectra.restore(active.state), holdout)
                        gate = compare_maxima(metrics, baseline)
                        gate["active_metrics"] = dict(baseline)

                    item.surface_metrics = metrics
                    item.baseline_metrics = gate.get("active_metrics")
                    item.gate_detail = gate
                    item.comparison = gate if active is not None else None
                    item.gate = gate.get("rule")
                    item.threshold = gate_threshold
                    item.reason = gate.get("reason") or None
                    item.accepted = bool(gate["allowed"])
                    if not gate["allowed"]:
                        item.status = "rejected"
                        db.flush()
                        record(db, actor, "spectrum_rejected", item.id)
                        rejection = spectrum_view(item)
                    else:
                        if active is not None:
                            active.status = "superseded"
                        if item.active_number is None:
                            item.active_number = _next_active_number(db)
                            item.version = f"v{item.active_number}"
                        item.status = "active"
                        item.activated_at = datetime.utcnow()
                        db.flush()
                        record(db, actor, "spectrum_activated", item.id)
                        result_view = spectrum_view(item)
    # A failed gate is a persisted domain outcome, not a transport exception.
    return rejection or result_view


def ensure_from_dataset(db, dataset: Dataset, actor: str = "seed", threshold: float | None = None):
    """Create and activate v1 from a seeded dataset when no active set exists."""
    existing = active_record(db, for_update=True)
    if existing is not None:
        return existing, False

    value = float(threshold if threshold is not None else PROFILE["parameter"]["default"])
    holdout = _select_split(dataset.rows, "复核")
    reference_rows = _select_split(dataset.rows, "参照")
    if len(reference_rows) < 18 or not holdout:
        return None, False
    model = ReferenceSpectra(matrix(reference_rows))
    metrics = _metrics(model, holdout)
    gate = first_set_gate(metrics, value)
    payload = {"label": "初始在用参考谱", "holdout_dataset_id": dataset.id}
    item = _create_version_row(db, payload, actor, model, dataset.id, value, holdout, metrics, None, gate)
    if not gate["allowed"]:
        item.status = "rejected"
        return item, False
    record(db, actor, "spectrum_activated", item.id)
    return item, True


# Descriptive service aliases for scripts/tests written around the batch or
# version vocabulary.
create_spectrum_version = submit_candidate
create_version = submit_candidate
submit_spectrum_batch = submit_candidate
register_spectrum = submit_candidate
