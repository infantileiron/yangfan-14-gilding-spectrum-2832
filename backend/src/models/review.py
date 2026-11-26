from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, new_id, utcnow


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("run_id", name="one_review_per_run"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    decision: Mapped[str] = mapped_column(String(20))
    samples: Mapped[list] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
