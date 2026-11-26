import os
from pathlib import Path

from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True, pool_recycle=240)
Session = sessionmaker(engine, expire_on_commit=False)
redis = Redis.from_url(os.environ["REDIS_URL"], socket_timeout=3, socket_connect_timeout=3)
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ISSUER = os.environ["JWT_ISSUER"]
ARTIFACTS = Path(os.getenv("ARTIFACTS_DIR", "/artifacts"))
SEED_DEMO = os.getenv("SEED_DEMO", "false").lower() == "true"
