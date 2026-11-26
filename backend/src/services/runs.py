import logging

from fastapi import HTTPException
from redis.exceptions import RedisError
from sqlalchemy import or_, select

from src.business.profile import PROFILE
from src.config.settings import Session, redis
from src.models.run import Run
from src.schemas.resources import run_view
from src.services import datasets, spectrum_versions
from src.services.audit import record

WAKE_KEY = "workbench:wake"
logger = logging.getLogger(__name__)


def require(db, run_id):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "计算单不存在。")
    return run


def list_runs():
    with Session() as db:
        return [run_view(run) for run in db.scalars(select(Run).order_by(Run.created_at.desc(), Run.id.desc()))]


def submit(body, actor):
    control = PROFILE["parameter"]
    if not control["min"] <= body.parameter <= control["max"]:
        raise HTTPException(422, f"「{control['label']}」超出允许范围。")
    with Session.begin() as db:
        dataset = datasets.require(db, body.dataset_id)
        active_spectrum = spectrum_versions.active_reference(db)
        selected_spectrum = active_spectrum
        requested_id = getattr(body, "spectrum_version_id", None) or getattr(body, "reference_spectrum_version_id", None)
        requested_label = getattr(body, "spectrum_version", None) or getattr(body, "reference_spectrum_version", None)
        if requested_label is not None:
            requested_label = str(requested_label)
        if requested_id is not None:
            requested_id = str(requested_id)
        if requested_label in {"active", "current", "latest", "在用", "当前在用"}:
            requested_label = None
        if requested_id in {"active", "current", "latest"}:
            requested_id = None
        if requested_id or requested_label:
            stmt = select(spectrum_versions.SpectrumVersion)
            if requested_id:
                stmt = stmt.where(spectrum_versions.SpectrumVersion.id == requested_id)
            else:
                label_filters = [spectrum_versions.SpectrumVersion.version == requested_label]
                if requested_label.isdigit():
                    number = int(requested_label)
                    label_filters.extend([
                        spectrum_versions.SpectrumVersion.active_number == number,
                        spectrum_versions.SpectrumVersion.seq == number,
                    ])
                stmt = stmt.where(or_(*label_filters))
            requested = db.scalar(stmt.limit(1))
            if requested is None:
                raise HTTPException(404, "指定的参考谱版本不存在。")
            if requested.status != "active" or not requested.accepted:
                raise HTTPException(409, "指定的参考谱版本尚未生效。")
            selected_spectrum = requested

        if selected_spectrum is not None:
            spectrum_version_id = selected_spectrum.id
            spectrum_version = selected_spectrum.version
        else:
            # Datasets are content-addressed and immutable, so their checksum is
            # also a stable label for the dataset-derived NMF state.
            spectrum_version_id = None
            spectrum_version = f"dataset-{dataset.checksum[:12]}"
        run = Run(
            dataset_id=body.dataset_id,
            label=body.label,
            parameter=body.parameter,
            actor=actor,
            spectrum_version_id=spectrum_version_id,
            spectrum_version=spectrum_version,
        )
        db.add(run)
        db.flush()
        record(db, actor, "run_queued", run.id)
        response = run_view(run)
    try:
        with redis.pipeline() as commands:
            commands.lpush(WAKE_KEY, run.id)
            commands.ltrim(WAKE_KEY, 0, 99)
            commands.execute()
    except RedisError:
        logger.warning("Redis wake signal failed for %s. Worker will poll the database.", run.id)
    return response
