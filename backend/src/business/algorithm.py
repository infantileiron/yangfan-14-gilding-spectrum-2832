import numpy as np

from .factorization import ReferenceSpectra
from .review import RECHECK, classify_candidate
from .spectra import matrix, split_spectra


def analyze(rows, parameter):
    reference, holdout, samples = split_spectra(rows)
    model = ReferenceSpectra(matrix(reference))
    _, holdout_residuals = model.decompose(matrix(holdout))
    mixes, residuals = model.decompose(matrix(samples))
    results = [classify_candidate(row, shares, residual, parameter)
               for row, shares, residual in zip(samples, mixes, residuals)]
    results.sort(key=lambda row: (row["decision"] != RECHECK, -row["residual_pp"], row["sample_id"]))
    holdout_peaks = np.max(np.abs(holdout_residuals), axis=1)
    flagged = sum(row["decision"] == RECHECK for row in results)
    return {
        "summary": f"{len(results)} 片待验补样，其中 {flagged} 片须全波段复测。",
        "metrics": [
            {"label": "独立复核片数", "value": len(holdout)},
            {"label": "独立复核全波段 RMSE（百分点）",
             "value": round(float(np.sqrt(np.mean(holdout_residuals ** 2))), 3)},
            {"label": "独立复核单片最大残差 P95（百分点）",
             "value": round(float(np.quantile(holdout_peaks, 0.95)), 3)},
        ],
        "reference_profiles": model.as_records(),
        "rows": results,
        "notes": ["光谱比例是分解出的反射贡献，不能用于推定金箔含量。各比例单独四舍五入。"],
    }
