"""Reference-spectrum version acceptance rules.

The policy functions in this module are intentionally persistence-free so the
replacement gates can be tested directly from CSV/domain rows.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from .factorization import ReferenceSpectra
from .spectra import SURFACES, matrix

# Comparisons are deliberately exact: the business rule is "must not become
# larger". Metrics are persisted at full float precision and NMF is seeded.
EPS_PP = 0.0


def maxima_from_residuals(residuals, holdout_rows, surfaces=SURFACES):
    """Maximum absolute single-band residual for each substrate."""
    residuals = np.asarray(residuals, dtype=float)
    if residuals.ndim != 2 or residuals.shape[0] != len(holdout_rows):
        raise ValueError("复核残差与复核片数量不一致。")
    result = {}
    missing = []
    for surface in surfaces:
        indexes = [index for index, row in enumerate(holdout_rows) if row.get("surface") == surface]
        if not indexes:
            missing.append(surface)
            continue
        result[surface] = float(np.max(np.abs(residuals[indexes])))
    if missing:
        raise ValueError("独立复核片缺少基底分组：" + "、".join(missing) + "。")
    return result


def surface_residual_maxima(spectra, holdout_rows):
    """Project holdout rows with ``spectra`` and calculate per-surface peaks."""
    model = as_model(spectra)
    _, residuals = model.decompose(matrix(holdout_rows))
    return maxima_from_residuals(residuals, holdout_rows)


def band_maxima_by_surface(spectra, holdout_rows):
    """Maximum residual for each wavelength within each substrate."""
    from .spectra import BANDS_NM

    model = as_model(spectra)
    _, residuals = model.decompose(matrix(holdout_rows))
    result = {}
    for surface in SURFACES:
        indexes = [index for index, row in enumerate(holdout_rows) if row.get("surface") == surface]
        if not indexes:
            continue
        peaks = np.max(np.abs(np.asarray(residuals)[indexes]), axis=0)
        result[surface] = {
            f"r{band}": float(value) for band, value in zip(BANDS_NM, peaks)
        }
        result[surface]["by_nm"] = {
            str(band): float(value) for band, value in zip(BANDS_NM, peaks)
        }
    return result


# Descriptive aliases used by different acceptance scripts.
max_abs_residual_by_surface = surface_residual_maxima
maximum_absolute_residual_by_surface = surface_residual_maxima
residual_maxima_by_surface = surface_residual_maxima


def state_from_profiles(profiles: Any) -> dict:
    """Build a restorable state from normalized or unnormalized 3x6 profiles."""
    if isinstance(profiles, np.ndarray):
        profile_items = profiles.tolist()
    else:
        profile_items = list(profiles)
    if len(profile_items) != 3:
        raise ValueError("参考谱必须包含三种基底对应的三条谱。")

    normalized = []
    for profile in profile_items:
        if isinstance(profile, Mapping):
            if "normalized_profile" in profile:
                values = [
                    item.get("percent") if isinstance(item, Mapping) else item[1]
                    for item in profile["normalized_profile"]
                ]
            elif "profile" in profile:
                values = list(profile["profile"])
            else:
                raise ValueError("参考谱记录缺少 normalized_profile。")
        else:
            values = list(profile)
        arr = np.asarray(values, dtype=float)
        if arr.shape != (6,) or not np.all(np.isfinite(arr)):
            raise ValueError("每条参考谱必须按六个波段提供有限数值。")
        total = float(arr.sum())
        if total <= 0:
            raise ValueError("参考谱的全部波段不能为零。")
        normalized.append(arr / total)

    matrix_profiles = np.asarray(normalized, dtype=float)
    centroids = matrix_profiles @ np.asarray((440, 500, 560, 620, 680, 740))
    order = np.argsort(centroids, kind="stable")
    ordered = matrix_profiles[order]
    return {
        "components": ordered.tolist(),
        "mass": [1.0, 1.0, 1.0],
        "order": [0, 1, 2],
        "centroids": centroids[order].tolist(),
        "profiles": ordered.tolist(),
    }


def as_model(spectra: Any) -> ReferenceSpectra:
    if isinstance(spectra, ReferenceSpectra):
        return spectra
    if hasattr(spectra, "decompose"):
        return spectra
    if hasattr(spectra, "state"):
        return ReferenceSpectra.restore(spectra.state)
    if isinstance(spectra, Mapping):
        state = spectra.get("state", spectra)
        if isinstance(state, ReferenceSpectra):
            return state
        if isinstance(state, Mapping) and "components" in state:
            return ReferenceSpectra.restore(state)
        profiles = None
        if isinstance(state, Mapping):
            profiles = state.get("profiles") or state.get("reference_profiles") or state.get("spectra")
        if profiles is None:
            raise ValueError("参考谱版本缺少 components 或 profiles。")
        return ReferenceSpectra.restore(state_from_profiles(profiles))
    if isinstance(spectra, (np.ndarray, list, tuple)):
        return ReferenceSpectra.restore(state_from_profiles(spectra))
    raise TypeError("无法识别参考谱版本。")


def _metric_value(metrics: Mapping[str, float], *names: str):
    for name in names:
        if name in metrics:
            return float(metrics[name])
    raise KeyError(f"残差指标缺少字段：{names[0]}")


SURFACE_ALIASES = {
    "封闭": "封闭基底",
    "closed": "封闭基底",
    "sealed": "封闭基底",
    "surface_1": "封闭基底",
    "s1": "封闭基底",
    "仿旧": "仿旧基底",
    "aged": "仿旧基底",
    "antique": "仿旧基底",
    "surface_2": "仿旧基底",
    "s2": "仿旧基底",
    "过渡": "过渡基底",
    "transition": "过渡基底",
    "transitional": "过渡基底",
    "surface_3": "过渡基底",
    "s3": "过渡基底",
}


def _normalize_metrics(metrics):
    if isinstance(metrics, Mapping):
        normalized = {}
        for key, value in metrics.items():
            normalized[SURFACE_ALIASES.get(str(key).strip().lower(), key)] = value
        return normalized
    if isinstance(metrics, (list, tuple)) and len(metrics) == len(SURFACES):
        return dict(zip(SURFACES, (float(value) for value in metrics)))
    raise ValueError("残差指标必须是按基底命名的映射，或三种基底顺序的三元列表。")


def compare_maxima(candidate_metrics: Mapping[str, float], active_metrics: Mapping[str, float]):
    """Compare new peaks with the active set on the same holdout films."""
    candidate_metrics = _normalize_metrics(candidate_metrics)
    active_metrics = _normalize_metrics(active_metrics)
    surfaces = tuple(active_metrics.keys()) or SURFACES
    comparison: dict[str, dict[str, float | bool]] = {}
    violations: list[str] = []
    for surface in surfaces:
        old = _metric_value(active_metrics, surface)
        new = _metric_value(candidate_metrics, surface)
        delta = new - old
        increased = delta > EPS_PP
        if increased:
            violations.append(surface)
        comparison[surface] = {
            "active_pp": old,
            "current_pp": old,
            "old_pp": old,
            "candidate_pp": new,
            "new_pp": new,
            "maximum_pp": new,
            "delta_pp": delta,
            "increased": increased,
            "regressed": increased,
            "allowed": not increased,
        }
    allowed = not violations
    return {
        "rule": "no_surface_maximum_increase",
        "allowed": allowed,
        "passed": allowed,
        "can_activate": allowed,
        "replace_whole_set": allowed,
        "surface_maxima": dict(candidate_metrics),
        "candidate_maxima": dict(candidate_metrics),
        "baseline_maxima": dict(active_metrics),
        "active_maxima": dict(active_metrics),
        "surfaces": comparison,
        "violations": violations,
        "reason": "" if allowed else "以下基底的单波段绝对残差最大值变大：" + "、".join(violations) + "。",
    }


def no_max_increased(comparison_or_new, active_metrics=None):
    if active_metrics is not None:
        comparison = compare_maxima(comparison_or_new, active_metrics)
    else:
        comparison = comparison_or_new
    return bool(comparison.get("allowed", comparison.get("passed", False)))


def can_replace(comparison_or_new, active_metrics=None):
    return no_max_increased(comparison_or_new, active_metrics)


def should_replace(comparison_or_new, active_metrics=None):
    return no_max_increased(comparison_or_new, active_metrics)


def check_spectrum_update(current=None, candidate=None, holdout_rows=None, **kwargs):
    return evaluate_update(current, candidate, holdout_rows, **kwargs)


def evaluate_spectrum_update(current=None, candidate=None, holdout_rows=None, **kwargs):
    return evaluate_update(current, candidate, holdout_rows, **kwargs)


def passes_first_threshold(metrics, threshold_pp):
    return bool(first_set_gate(metrics, threshold_pp)["allowed"])


def is_first_set_enabled(metrics, threshold_pp):
    return passes_first_threshold(metrics, threshold_pp)


def _looks_like_metrics(value):
    if isinstance(value, Mapping):
        return all(isinstance(v, (int, float)) for v in value.values())
    if isinstance(value, (list, tuple)) and len(value) == len(SURFACES):
        return all(isinstance(v, (int, float)) for v in value)
    return False


def compare_spectra(current, candidate, holdout_rows=None):
    """Compare active first and candidate second (natural old/new order)."""
    if _looks_like_metrics(current):
        active_metrics = _normalize_metrics(current)
    else:
        if holdout_rows is None:
            raise ValueError("比较参考谱需要独立复核片。")
        active_metrics = surface_residual_maxima(current, holdout_rows)

    if _looks_like_metrics(candidate):
        candidate_metrics = _normalize_metrics(candidate)
    else:
        if holdout_rows is None:
            raise ValueError("比较参考谱需要独立复核片。")
        candidate_metrics = surface_residual_maxima(candidate, holdout_rows)

    return compare_maxima(candidate_metrics, active_metrics)


def evaluate_update(current=None, candidate=None, holdout_rows=None, *, threshold_pp=7.0,
                    new=None, old=None, review_rows=None):
    """Keyword-friendly facade used by domain scripts and acceptance checks."""
    current = current if current is not None else old
    candidate = candidate if candidate is not None else new
    holdout_rows = holdout_rows if holdout_rows is not None else review_rows
    if current is None:
        if _looks_like_metrics(candidate):
            return first_set_gate(candidate, threshold_pp)
        return evaluate_candidate(candidate, holdout_rows, threshold_pp=threshold_pp)
    return compare_spectra(current, candidate, holdout_rows)


def first_set_gate(metrics: Mapping[str, float], threshold_pp: float):
    """The first active set must be strictly below the recheck threshold."""
    metrics = _normalize_metrics(metrics)
    threshold_pp = float(threshold_pp)
    surfaces = tuple(metrics.keys()) or SURFACES
    detail = {}
    violations = []
    for surface in surfaces:
        value = float(metrics[surface])
        below = value < threshold_pp
        if not below:
            violations.append(surface)
        detail[surface] = {
            "maximum_pp": value,
            "threshold_pp": threshold_pp,
            "below_threshold": below,
            "allowed": below,
        }
    allowed = not violations
    return {
        "rule": "first_set_below_recheck_threshold",
        "allowed": allowed,
        "passed": allowed,
        "can_activate": allowed,
        "threshold_pp": threshold_pp,
        "surface_maxima": dict(metrics),
        "surfaces": detail,
        "violations": violations,
        "reason": "" if allowed else "首套谱在以下基底未低于复测门槛：" + "、".join(violations) + "。",
    }


def evaluate_candidate(
    candidate_spectra=None,
    holdout_rows=None,
    *,
    candidate_metrics=None,
    active_spectra=None,
    active_metrics=None,
    threshold_pp=7.0,
):
    """Evaluate either the first-set threshold or replacement regression gate."""
    if candidate_metrics is None:
        if candidate_spectra is None or holdout_rows is None:
            raise ValueError("评估新谱需要谱集合和同一批独立复核片。")
        candidate_metrics = surface_residual_maxima(candidate_spectra, holdout_rows)

    if active_metrics is None and active_spectra is not None:
        if holdout_rows is None:
            raise ValueError("对比在用谱需要同一批独立复核片。")
        active_metrics = surface_residual_maxima(active_spectra, holdout_rows)

    if active_metrics:
        gate = compare_maxima(candidate_metrics, active_metrics)
    else:
        gate = first_set_gate(candidate_metrics, threshold_pp)
    gate["candidate_metrics"] = dict(candidate_metrics)
    gate["active_metrics"] = dict(active_metrics or {})
    return gate
