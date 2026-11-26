import json
import logging
import math
from datetime import timedelta

from sqlalchemy import and_, or_, select, update

from src.business.algorithm import analyze
from src.business.profile import PROFILE
from src.config.settings import ARTIFACTS, Session
from src.constants.workflow import Stage
from src.models.base import new_id, utcnow
from src.models.dataset import Dataset
from src.models.run import Run
from src.services.audit import record
from src.services.exports import result_keys
from src.utils.csv_data import render_csv

log = logging.getLogger(__name__)
LEASE = timedelta(minutes=10)
MAX_ATTEMPTS = 3


def claim():
    expired = utcnow() - LEASE
    stale = and_(Run.status == Stage.RUNNING.value, Run.started_at < expired)
    available = or_(Run.status == Stage.QUEUED.value, stale)
    with Session.begin() as db:
        exhausted = db.scalars(select(Run).where(stale, Run.attempts >= MAX_ATTEMPTS).with_for_update(skip_locked=True))
        for run in exhausted:
            run.status = Stage.FAILED.value
            run.error = "后台任务多次中断。请提交新的计算单。"
            run.finished_at = utcnow()
            record(db, "worker", "run_failed", run.id)
        run = db.scalar(
            select(Run).where(available, Run.attempts < MAX_ATTEMPTS)
            .order_by(Run.created_at, Run.id).limit(1).with_for_update(skip_locked=True)
        )
        if run is None:
            return None
        run.status = Stage.RUNNING.value
        run.lease = new_id()
        run.started_at = utcnow()
        run.attempts += 1
        dataset = db.get(Dataset, run.dataset_id)
        return run.id, run.lease, run.parameter, dataset.rows


def verify_result(result):
    if not result["rows"]:
        raise ValueError("当前参数没有得到可交接的结果。请检查数据并调整参数。")
    samples = set()
    chart = PROFILE["chart"]["key"]
    for row in result["rows"]:
        if not set(result_keys()).issubset(row) or row["sample_id"] in samples:
            raise ValueError("算法结果包含重复样本或缺少导出列。")
        if not isinstance(row[chart], (float, int)) or not math.isfinite(row[chart]):
            raise ValueError("算法结果包含无效的图表数值。")
        samples.add(row["sample_id"])
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    return result


def execute(job):
    run_id, lease, parameter, rows = job
    artifact = None
    result = None
    error = None
    try:
        result = verify_result(analyze(rows, parameter))
        artifact = f"{run_id}-{lease}.csv"
        path = ARTIFACTS / artifact
        temporary = path.with_suffix(".tmp")
        temporary.write_text("\ufeff" + render_csv(result["rows"], result_keys(), protect=True), encoding="utf-8")
        temporary.replace(path)
    except ValueError as exc:
        error = str(exc)
    except Exception:
        log.exception("Run %s failed", run_id)
        error = "计算或导出失败。请检查输入并重新提交。"
    if error:
        result = None
    stage = Stage.FAILED.value if error else Stage.SUCCEEDED.value
    with Session.begin() as db:
        change = db.execute(update(Run).where(Run.id == run_id, Run.lease == lease, Run.status == Stage.RUNNING.value).values(
            status=stage, result=result, artifact=artifact if not error else None, error=error, finished_at=utcnow(),
        ))
        if change.rowcount:
            record(db, "worker", f"run_{stage}", run_id)
    if artifact and (error or not change.rowcount):
        (ARTIFACTS / artifact).unlink(missing_ok=True)
