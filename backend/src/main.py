import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select

from migrations.bootstrap import migrate
from scripts.seed_demo import seed
from src.business.profile import PROFILE
from src.business.routes import router as domain_router
from src.config.settings import SEED_DEMO, Session, engine, redis
from src.middlewares.headers import add_headers
from src.middlewares.throttle import login_limit
from src.models.dataset import Dataset
from src.routes import auth, spectra, workspace
from src.routes.dependencies import current_account

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    migrate(engine)
    if SEED_DEMO:
        try:
            seed()
        except Exception:
            logger.exception("演示数据初始化失败")
    yield


app = FastAPI(title=PROFILE["title"], description=PROFILE["subtitle"], lifespan=lifespan, redoc_url=None)
app.middleware("http")(login_limit)
app.middleware("http")(add_headers)
app.include_router(auth.router, prefix="/api")
app.include_router(spectra.router, prefix="/api")
app.include_router(workspace.router, prefix="/api")
app.include_router(domain_router, prefix="/api", dependencies=[Depends(current_account)])


@app.get("/healthz")
def health():
    try:
        with Session() as db:
            db.execute(select(Dataset.id).limit(1))
        redis.ping()
    except Exception as exc:
        raise HTTPException(503, "存储服务未就绪。") from exc
    return {"status": "ok"}
