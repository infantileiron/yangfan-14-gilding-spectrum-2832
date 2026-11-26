import logging
import time
from pathlib import Path

from redis.exceptions import RedisError

from src.config.settings import redis
from src.services.executor import claim, execute
from src.services.runs import WAKE_KEY

HEARTBEAT = Path("/tmp/worker-heartbeat")


def work():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            job = claim()
            HEARTBEAT.touch()
            if job:
                execute(job)
            else:
                try:
                    redis.brpop(WAKE_KEY, timeout=1)
                except RedisError:
                    time.sleep(1)
        except Exception:
            logging.exception("Worker loop error")
            time.sleep(2)


if __name__ == "__main__":
    work()
