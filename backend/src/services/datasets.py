from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.business.profile import PROFILE
from src.config.settings import Session
from src.models.dataset import Dataset
from src.schemas.resources import dataset_view
from src.services.audit import record
from src.utils.csv_data import digest, parse_csv


def require(db, dataset_id):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "数据版本不存在。")
    return dataset


def list_datasets():
    with Session() as db:
        return [dataset_view(row) for row in db.scalars(select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id.desc()))]


def save_in(db, name, rows, author, audit=True):
    checksum = digest(rows)
    existing = db.scalar(select(Dataset).where(Dataset.checksum == checksum))
    if existing is not None:
        return existing, False
    item = Dataset(name=name, checksum=checksum, rows=rows, author=author)
    try:
        with db.begin_nested():
            db.add(item)
            db.flush()
    except IntegrityError:
        existing = db.scalar(select(Dataset).where(Dataset.checksum == checksum).with_for_update())
        if existing is None:
            raise
        return existing, False
    if audit:
        record(db, author, "dataset_imported", item.id)
    return item, True


def ingest(name, contents, author):
    try:
        rows = parse_csv(contents, PROFILE["columns"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with Session.begin() as db:
        item, created = save_in(db, name, rows, author)
        return {**dataset_view(item), "created": created}
