from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.config.settings import Session
from src.constants.workflow import Decision, Stage
from src.models.review import Review
from src.schemas.resources import review_view
from src.services import runs
from src.services.audit import record


def lookup(db, run_id):
    return db.scalar(select(Review).where(Review.run_id == run_id))


def list_reviews():
    with Session() as db:
        return [review_view(review) for review in db.scalars(select(Review).order_by(Review.created_at.desc()))]


def sign(run_id, body, reviewer):
    with Session.begin() as db:
        run = runs.require(db, run_id)
        if run.status != Stage.SUCCEEDED.value:
            raise HTTPException(409, "计算成功后才能签审。")
        if lookup(db, run_id) is not None:
            raise HTTPException(409, "此计算单已有交接决定。")
        valid = {row["sample_id"] for row in run.result["rows"]}
        samples = list(dict.fromkeys(body.samples))
        if set(samples) - valid:
            raise HTTPException(422, "签审样本不属于这次计算。")
        if body.decision == Decision.APPROVE and not samples:
            raise HTTPException(422, "签发至少需要勾选一条结果。")
        review = Review(run_id=run_id, decision=body.decision.value, samples=samples, note=body.note, reviewer=reviewer)
        db.add(review)
        record(db, reviewer, f"review_{body.decision.value}", run_id)
        try:
            db.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "此计算单已有交接决定。") from exc
        return review_view(review)
