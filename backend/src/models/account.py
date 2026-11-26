from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Account(Base):
    __tablename__ = "accounts"
    email: Mapped[str] = mapped_column(String(160), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
