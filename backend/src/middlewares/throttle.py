from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from starlette.responses import JSONResponse

_attempts = defaultdict(deque)
_lock = Lock()


async def login_limit(request, call_next):
    if request.url.path == "/api/auth/login" and request.method == "POST":
        key = request.client.host if request.client else "local"
        now = monotonic()
        with _lock:
            for identity in list(_attempts):
                attempts = _attempts[identity]
                while attempts and attempts[0] <= now - 60:
                    attempts.popleft()
                if not attempts:
                    del _attempts[identity]
            attempts = _attempts[key]
            if len(attempts) >= 30:
                return JSONResponse({"detail": "登录请求过多，请稍后重试。"}, 429, headers={"Retry-After": "60"})
            attempts.append(now)
    return await call_next(request)
