import numpy as np

from .review import RECHECK, classify_candidate
from .spectra import matrix, split_samples, split_spectra
from .spectrum_versions import surface_residual_maxima


def _version_metadata(spectrum_version, spectrum_version_id=None):
    metadata = {
        "spectrum_version": None,
        "spectrum_version_id": spectrum_version_id,
        "reference_spectrum_version": None,
        "reference_spectrum_version_id": spectrum_version_id,
        "reference_version": None,
        "reference_version_id": spectrum_version_id,
        "used_spectrum_version": None,
        "used_reference_spectrum_version": None,
        "reference_spectrum_id": spectrum_version_id,
        "spectrum_id": spectrum_version_id,
    }

    label = None
    if isinstance(spectrum_version, str):
        label = spectrum_version
    elif isinstance(spectrum_version, int):
        label = f"v{spectrum_version}"
    elif spectrum_version is not None:
        label = (
            getattr(spectrum_version, "version_label", None)
            or getattr(spectrum_version, "version", None)
            or getattr(spectrum_version, "id", None)
        )
        if spectrum_version_id is None:
            spectrum_version_id = getattr(spectrum_version, "id", None)

    if isinstance(label, int):
        label = f"v{label}"
    metadata["spectrum_version"] = label
    metadata["reference_spectrum_version"] = label
    metadata["reference_version"] = label
    metadata["used_spectrum_version"] = label
    metadata["used_reference_spectrum_version"] = label
    if spectrum_version_id is not None:
        metadata["spectrum_version_id"] = spectrum_version_id
        metadata["reference_spectrum_version_id"] = spectrum_version_id
        metadata["reference_version_id"] = spectrum_version_id
        metadata["reference_spectrum_id"] = spectrum_version_id
        metadata["spectrum_id"] = spectrum_version_id
    metadata["spectrum_version_info"] = {
        "id": spectrum_version_id,
        "version": label,
        "version_label": label,
        "spectrum_version": label,
        "spectrum_version_id": spectrum_version_id,
    }
    metadata["reference_spectrum_version_info"] = dict(metadata["spectrum_version_info"])
    return metadata


def _coerce_pinned_spectrum(spectrum):
    """Accept model objects, persisted snapshots, ORM rows, matrices, or labels."""
    if spectrum is None or isinstance(spectrum, str):
        return None, spectrum if isinstance(spectrum, str) else None, None

    label = None
    version_id = None
    if hasattr(spectrum, "decompose"):
        return spectrum, getattr(spectrum, "version_label", None), getattr(spectrum, "id", None)

    state = None
    if hasattr(spectrum, "state"):
        state = spectrum.state
        label = getattr(spectrum, "version_label", None) or getattr(spectrum, "version", None)
        version_id = getattr(spectrum, "id", None)
    elif isinstance(spectrum, dict):
        label = spectrum.get("version_label") or spectrum.get("version")
        version_id = spectrum.get("id") or spectrum.get("spectrum_version_id")
        if "state" in spectrum:
            state = spectrum["state"]
        elif "components" in spectrum:
            state = spectrum
        elif "profiles" in spectrum or "reference_profiles" in spectrum:
            state = spectrum

    if state is not None:
        from .spectrum_versions import as_model
        return as_model(state), label, version_id

    if isinstance(spectrum, (np.ndarray, list, tuple)):
        from .spectrum_versions import as_model
        return as_model(spectrum), label, version_id

    return None, label, version_id


def analyze(rows, parameter, spectrum=None, spectrum_version=None, spectrum_version_id=None):
    pinned_model, implicit_label, implicit_id = _coerce_pinned_spectrum(spectrum)

    # Tolerate a likely positional analyze(rows, parameter, "v2") contract.
    if pinned_model is None and isinstance(spectrum, str):
        spectrum_version = spectrum_version or spectrum
    if spectrum_version is None and implicit_label is not None:
        spectrum_version = implicit_label
    if spectrum_version_id is None and implicit_id is not None:
        spectrum_version_id = implicit_id

    dataset_holdout = []
    if pinned_model is None:
        reference, holdout, samples = split_spectra(rows)
        from .factorization import ReferenceSpectra
        model = ReferenceSpectra(matrix(reference))
        dataset_holdout = holdout
        if spectrum_version is None:
            spectrum_version = "dataset-derived"
    else:
        model = pinned_model
        samples = split_samples(rows)
        dataset_holdout = [row for row in rows if row.get("split") == "复核"]

    holdout_residuals = None
    holdout_peaks = None
    surface_metrics = None
    if dataset_holdout:
        _, holdout_residuals = model.decompose(matrix(dataset_holdout))
        holdout_peaks = np.max(np.abs(holdout_residuals), axis=1)
        try:
            surface_metrics = surface_residual_maxima(model, dataset_holdout)
        except ValueError:
            surface_metrics = None

    mixes, residuals = model.decompose(matrix(samples))
    results = [classify_candidate(row, shares, residual, parameter)
               for row, shares, residual in zip(samples, mixes, residuals)]
    results.sort(key=lambda row: (row["decision"] != RECHECK, -row["residual_pp"], row["sample_id"]))
    flagged = sum(row["decision"] == RECHECK for row in results)
    metrics = []
    if dataset_holdout and holdout_residuals is not None:
        metrics = [
            {"label": "独立复核片数", "value": len(dataset_holdout)},
            {"label": "独立复核全波段 RMSE（百分点）",
             "value": round(float(np.sqrt(np.mean(holdout_residuals ** 2))), 3)},
            {"label": "独立复核单片最大残差 P95（百分点）",
             "value": round(float(np.quantile(holdout_peaks, 0.95)), 3)},
        ]

    if surface_metrics is None and isinstance(spectrum, dict):
        surface_metrics = spectrum.get("surface_metrics")

    version_metadata = _version_metadata(spectrum_version, spectrum_version_id)
    result = {
        "summary": f"{len(results)} 片待验补样，其中 {flagged} 片须全波段复测。",
        "metrics": metrics,
        "reference_profiles": model.as_records(),
        "rows": results,
        "surface_residual_maxima": surface_metrics,
        "residual_maxima_by_surface": surface_metrics,
        "max_residual_by_surface": surface_metrics,
        "notes": ["光谱比例是分解出的反射贡献，不能用于推定金箔含量。各比例单独四舍五入。"],
        **version_metadata,
    }
    return result
