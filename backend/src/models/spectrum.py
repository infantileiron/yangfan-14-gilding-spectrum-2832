from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, new_id, utcnow


class SpectrumVersion(Base):
    """An immutable fitted reference-spectrum set and its activation gate."""

    __tablename__ = "spectrum_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    seq: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    active_number: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    version: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True, index=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    source_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    holdout_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    holdout_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    holdout_rows: Mapped[list | None] = mapped_column(JSON, nullable=True)

    state: Mapped[dict] = mapped_column(JSON)
    surface_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gate_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comparison: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    gate: Mapped[str | None] = mapped_column(String(60), nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(160), default="system")

    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)
