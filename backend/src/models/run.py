from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.workflow import Stage
from src.models.base import Base, new_id, utcnow


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    parameter: Mapped[float]
    actor: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default=Stage.QUEUED.value, index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    lease: Mapped[str | None] = mapped_column(String(36))
    attempts: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
