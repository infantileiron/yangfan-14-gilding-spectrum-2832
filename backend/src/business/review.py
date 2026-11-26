import numpy as np

from .spectra import BANDS_NM

RECHECK = "全波段复测"
TRIAL = "二次试贴"


def classify_candidate(row, shares, residual, threshold):
    peak = int(np.argmax(np.abs(residual)))
    error = abs(float(residual[peak]))
    return {
        "sample_id": row["sample_id"],
        "surface": row["surface"],
        **{f"spectrum_{index}_pct": round(float(share) * 100, 2)
           for index, share in enumerate(shares, start=1)},
        "worst_band_nm": BANDS_NM[peak],
        "residual_pp": round(error, 3),
        "decision": RECHECK if error >= threshold else TRIAL,
    }


def review_sheet(result):
    rows = result["rows"]
    return {
        "reference_profiles": result["reference_profiles"],
        "bins": {
            decision: [
                {"sample_id": row["sample_id"], "worst_band_nm": row["worst_band_nm"],
                 "residual_pp": row["residual_pp"]}
                for row in rows if row["decision"] == decision
            ]
            for decision in (RECHECK, TRIAL)
        },
    }
