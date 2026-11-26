from datetime import datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, new_id, utcnow


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    rows: Mapped[list] = mapped_column(JSON)
    author: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
