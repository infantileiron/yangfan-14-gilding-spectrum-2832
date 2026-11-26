from fastapi import Response

from src.business.profile import PROFILE
from src.config.settings import Session
from src.schemas.resources import dataset_view, review_view, run_view
from src.services import datasets, reviews, runs
from src.utils.csv_data import render_csv


def dataset_details(dataset_id):
    with Session() as db:
        return dataset_view(datasets.require(db, dataset_id), include_rows=True)


def dataset_csv(dataset_id):
    with Session() as db:
        dataset = datasets.require(db, dataset_id)
        contents = render_csv(dataset.rows, [field["key"] for field in PROFILE["columns"]])
        return Response(contents, media_type="text/csv", headers={
            "Content-Disposition": f'attachment; filename="{dataset_id}-input.csv"',
        })


def run_details(run_id):
    with Session() as db:
        result = run_view(runs.require(db, run_id), include_result=True)
        review = reviews.lookup(db, run_id)
        result["review"] = review_view(review) if review else None
        return result
