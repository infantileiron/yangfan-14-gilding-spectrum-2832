import numpy as np

BANDS_NM = (440, 500, 560, 620, 680, 740)
BAND_FIELDS = tuple(f"r{band}" for band in BANDS_NM)
SURFACES = ("封闭基底", "仿旧基底", "过渡基底")


def matrix(rows):
    return np.asarray([[row[field] for field in BAND_FIELDS] for row in rows], dtype=float)


def _validated_group(rows, split):
    group = [row for row in rows if row["split"] == split]
    if not group:
        raise ValueError(f"{split}至少需要 1 片。")
    values = matrix(group)
    if np.any(values.sum(axis=1) == 0):
        raise ValueError(f"{split}内有样片的六波段均为零，请检查暗电流扣除。")
    return group


def split_samples(rows):
    """Extract pending patches when a managed reference spectrum is pinned."""
    return _validated_group(rows, "待验")


def split_spectra(rows):
    groups = tuple([row for row in rows if row["split"] == split] for split in ("参照", "复核", "待验"))
    for group, minimum, split in zip(groups, (18, 8, 1), ("参照", "复核", "待验")):
        if len(group) < minimum:
            raise ValueError(f"{split}至少需要 {minimum} 片。")
        values = matrix(group)
        if np.any(values.sum(axis=1) == 0):
            raise ValueError(f"{split}内有样片的六波段均为零，请检查暗电流扣除。")
    if np.linalg.matrix_rank(matrix(groups[0])) < 3:
        raise ValueError("参照谱有效秩小于 3，无法提取三种参考谱。")
    return groups


_LAZY_SPECTRUM_EXPORTS = {
    "compare_maxima",
    "compare_spectra",
    "evaluate_update",
    "first_set_gate",
    "surface_residual_maxima",
    "max_abs_residual_by_surface",
    "maximum_absolute_residual_by_surface",
    "residual_maxima_by_surface",
}


def __getattr__(name):
    if name in _LAZY_SPECTRUM_EXPORTS:
        from . import spectrum_versions
        return getattr(spectrum_versions, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
