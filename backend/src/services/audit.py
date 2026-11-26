from sqlalchemy import select

from src.config.settings import Session
from src.models.audit import Event
from src.schemas.resources import audit_view


def record(db, actor, action, subject):
    db.add(Event(actor=actor, action=action, subject=subject))


def recent():
    with Session() as db:
        events = db.scalars(select(Event).order_by(Event.created_at.desc(), Event.id.desc()).limit(100))
        return [audit_view(event) for event in events]
