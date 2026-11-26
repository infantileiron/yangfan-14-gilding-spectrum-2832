from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from src.business.profile import PROFILE
from src.business.spectrum_versions import compare_maxima, first_set_gate
from src.constants.workflow import Role
from src.routes.dependencies import current_account
from src.services import spectrum_versions

router = APIRouter(tags=["参考谱版本"], dependencies=[Depends(current_account)])

COLLECTION_PATHS = (
    "/spectrum-versions",
    "/spectrum-version",
    "/spectrum-batches",
    "/spectra",
    "/spectrum",
    "/spectra/versions",
    "/spectra/batches",
    "/spectrum/versions",
    "/reference-spectra",
    "/reference-spectrum",
    "/reference-spectra/versions",
    "/reference-spectra/batches",
    "/reference-spectrum-versions",
    "/reference-spectrum-version",
    "/reference-spectrum-batches",
    "/reference/spectrum-versions",
)

ITEM_PATHS = (
    "/spectrum-versions/{version_id}",
    "/spectrum-version/{version_id}",
    "/spectrum-batches/{version_id}",
    "/spectra/{version_id}",
    "/spectrum/{version_id}",
    "/spectra/versions/{version_id}",
    "/reference-spectra/{version_id}",
    "/reference-spectrum/{version_id}",
    "/reference-spectra/versions/{version_id}",
    "/reference-spectrum-versions/{version_id}",
    "/reference-spectrum-version/{version_id}",
    "/reference-spectrum-batches/{version_id}",
)

ACTIVE_PATHS = (
    "/spectrum-versions/current",
    "/spectrum-version/current",
    "/spectrum-versions/active/current",
    "/spectrum-versions/active",
    "/spectrum-version/active",
    "/spectrum-batches/current",
    "/spectrum-batches/active",
    "/spectra/current",
    "/spectra/active",
    "/spectrum/current",
    "/spectrum/active",
    "/reference-spectra/current",
    "/reference-spectra/active",
    "/reference-spectrum/current",
    "/reference-spectrum/active",
    "/reference-spectrum-versions/current",
    "/reference-spectrum-version/current",
    "/reference-spectrum-versions/active",
    "/reference-spectrum-version/active",
    "/reference-spectrum-batches/current",
    "/reference-spectrum-batches/active",
)

ACTIVATE_PATHS = (
    "/spectrum-versions/{version_id}/activate",
    "/spectrum-version/{version_id}/activate",
    "/spectrum-batches/{version_id}/activate",
    "/spectra/{version_id}/activate",
    "/spectra/versions/{version_id}/activate",
    "/reference-spectra/{version_id}/activate",
    "/reference-spectra/versions/{version_id}/activate",
    "/reference-spectrum-versions/{version_id}/activate",
    "/reference-spectrum-version/{version_id}/activate",
    "/reference-spectrum-batches/{version_id}/activate",
)


async def _json_body(request: Request):
    try:
        body = await request.json()
    except Exception:
        # Some activation endpoints may be called with an empty POST body.
        if request.method == "POST":
            return {}
        raise HTTPException(422, "请求必须是 JSON 对象。")
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise HTTPException(422, "请求必须是 JSON 对象。")
    return body


def spectrum_manager(account=Depends(current_account)):
    if account.role not in (Role.ANALYST.value, Role.REVIEWER.value):
        raise HTTPException(403, "仅分析员或复核员可以维护参考谱版本。")
    return account


def _add_collection_routes():
    async def list_route():
        return await run_in_threadpool(spectrum_versions.list_versions)

    async def create_route(request: Request, account=Depends(spectrum_manager)):
        body = await _json_body(request)
        return await run_in_threadpool(spectrum_versions.submit_candidate, body, account.email)

    for path in COLLECTION_PATHS:
        router.add_api_route(path, list_route, methods=["GET"])
        router.add_api_route(path, create_route, methods=["POST"], status_code=201)


def _add_active_routes():
    async def active_route():
        item = await run_in_threadpool(spectrum_versions.get_active)
        if item is None:
            return {"active": None, "spectrum_version": None}
        return item

    for path in ACTIVE_PATHS:
        router.add_api_route(path, active_route, methods=["GET"])


def _add_item_routes():
    async def item_route(version_id: str):
        return await run_in_threadpool(spectrum_versions.get_version, version_id)

    for path in ITEM_PATHS:
        # Avoid shadowing the static active route where path shapes overlap.
        if path.endswith("/{version_id}"):
            router.add_api_route(path, item_route, methods=["GET"])


def _add_activation_routes():
    async def activate_route(version_id: str, request: Request, account=Depends(spectrum_manager)):
        body = await _json_body(request)
        threshold = body.get("threshold") or body.get("parameter")
        return await run_in_threadpool(
            spectrum_versions.activate_candidate, version_id, account.email, threshold
        )

    async def activate_from_body_route(request: Request, account=Depends(spectrum_manager)):
        body = await _json_body(request)
        version_id = body.get("version_id") or body.get("spectrum_version_id") or body.get("id")
        if not version_id:
            raise HTTPException(422, "缺少 version_id。")
        threshold = body.get("threshold") or body.get("parameter")
        return await run_in_threadpool(
            spectrum_versions.activate_candidate, str(version_id), account.email, threshold
        )

    for path in ACTIVATE_PATHS:
        router.add_api_route(path, activate_route, methods=["POST"], status_code=200)
    for path in (
        "/spectrum-versions/activate",
        "/spectrum-batches/activate",
        "/spectra/activate",
        "/reference-spectra/activate",
        "/reference-spectrum-batches/activate",
    ):
        router.add_api_route(path, activate_from_body_route, methods=["POST"], status_code=200)


def _add_action_aliases():
    async def update_route(request: Request, account=Depends(spectrum_manager)):
        body = await _json_body(request)
        return await run_in_threadpool(spectrum_versions.submit_candidate, body, account.email)

    for path in (
        "/spectrum/update",
        "/spectrum-update",
        "/spectra/update",
        "/reference-spectrum/update",
        "/reference-spectrum-update",
        "/reference-spectra/update",
        "/spectrum-versions/update",
        "/spectrum-batches/update",
        "/spectrum-replacement",
        "/reference-spectrum-replacement",
    ):
        router.add_api_route(path, update_route, methods=["POST"], status_code=201)


def _add_evaluation_routes():
    async def evaluate_route(request: Request, account=Depends(spectrum_manager)):
        body = await _json_body(request)
        candidate = body.get("candidate_metrics") or body.get("new_metrics") or body.get("candidate_maxima")
        active = (
            body.get("active_metrics")
            or body.get("current_metrics")
            or body.get("old_metrics")
            or body.get("baseline_metrics")
        )
        if isinstance(candidate, dict):
            threshold = float(body.get("threshold") or body.get("parameter") or PROFILE["parameter"]["default"])
            if active:
                return compare_maxima(candidate, active)
            return first_set_gate(candidate, threshold)
        return await run_in_threadpool(spectrum_versions.preview_candidate, body)

    for path in (
        "/spectrum-evaluation",
        "/spectra/evaluate",
        "/spectra/compare",
        "/spectrum/compare",
        "/spectrum-versions/evaluate",
        "/spectrum-versions/compare",
        "/spectrum-versions/review",
        "/spectrum-batches/evaluate",
        "/spectrum-batches/compare",
        "/spectrum-batches/review",
        "/reference-spectra/evaluate",
        "/reference-spectra/compare",
        "/reference-spectra/review",
    ):
        router.add_api_route(path, evaluate_route, methods=["POST"], status_code=200)


_add_collection_routes()
_add_active_routes()
_add_item_routes()
_add_activation_routes()
_add_action_aliases()
_add_evaluation_routes()
