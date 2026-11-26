from fastapi import APIRouter, HTTPException

from src.config.settings import Session
from src.constants.workflow import Stage
from src.routes.spectra import router as spectrum_router
from src.services.runs import require

from .review import review_sheet

router = APIRouter(prefix="/domain", tags=["光谱复测"])
router.include_router(spectrum_router)


@router.get("/spectrum-review/{run_id}")
def spectrum_review(run_id: str):
    with Session() as db:
        run = require(db, run_id)
        if run.status != Stage.SUCCEEDED.value:
            raise HTTPException(409, "分解完成后才能生成光谱复测单。")
        return {"run_id": run_id, **review_sheet(run.result)}
