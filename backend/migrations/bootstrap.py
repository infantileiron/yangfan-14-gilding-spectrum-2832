"""Initial schema for a fresh Compose volume."""
from src.models.account import Account
from src.models.audit import Event
from src.models.dataset import Dataset
from src.models.review import Review
from src.models.run import Run

SCHEMA = (Account, Dataset, Run, Review, Event)


def migrate(engine):
    tables = [model.__table__ for model in SCHEMA]
    Account.metadata.create_all(engine, tables=tables)
