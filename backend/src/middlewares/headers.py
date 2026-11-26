from time import perf_counter
from uuid import uuid4


async def add_headers(request, call_next):
    start = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(uuid4())
    response.headers["Server-Timing"] = f"app;dur={(perf_counter() - start) * 1000:.1f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response
