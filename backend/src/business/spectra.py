import numpy as np

BANDS_NM = (440, 500, 560, 620, 680, 740)
BAND_FIELDS = tuple(f"r{band}" for band in BANDS_NM)


def matrix(rows):
    return np.asarray([[row[field] for field in BAND_FIELDS] for row in rows], dtype=float)


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
