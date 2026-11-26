"""Initial schema for a fresh Compose volume and lightweight additive upgrades."""
from sqlalchemy import inspect, text

from src.models.account import Account
from src.models.audit import Event
from src.models.dataset import Dataset
from src.models.review import Review
from src.models.run import Run
from src.models.spectrum import SpectrumVersion

SCHEMA = (Account, Dataset, SpectrumVersion, Run, Review, Event)


def migrate(engine):
    tables = [model.__table__ for model in SCHEMA]
    Account.metadata.create_all(engine, tables=tables)
    _ensure_run_columns(engine)


def _ensure_run_columns(engine):
    """Add pinning columns to volumes created before spectrum versioning."""
    inspector = inspect(engine)
    if "runs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("runs")}
    statements = []
    if "spectrum_version_id" not in columns:
        statements.append("ALTER TABLE runs ADD COLUMN spectrum_version_id VARCHAR(36) NULL")
    if "spectrum_version" not in columns:
        statements.append("ALTER TABLE runs ADD COLUMN spectrum_version VARCHAR(40) NULL")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
