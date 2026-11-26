import warnings

import numpy as np
from sklearn.decomposition import NMF
from sklearn.exceptions import ConvergenceWarning

from .spectra import BANDS_NM


class ReferenceSpectra:
    def __init__(self, training):
        self.model = NMF(n_components=3, init="nndsvda", random_state=414, tol=1e-5, max_iter=2500)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            try:
                self.model.fit(training)
            except ConvergenceWarning as exc:
                raise ValueError("参考谱分解未收敛。请检查参照片的测量质量与覆盖范围。") from exc
        components = self.model.components_
        self.mass = components.sum(axis=1)
        if np.any(self.mass <= 0):
            raise ValueError("有参考谱的全部波段为零，请补充有效参照片。")
        normalized = components / self.mass[:, None]
        self.centroids = normalized @ np.asarray(BANDS_NM)
        self.order = np.argsort(self.centroids, kind="stable")
        self.profiles = normalized[self.order]

    def decompose(self, values):
        coefficients = self.model.transform(values)
        residual = values - coefficients @ self.model.components_
        contribution = (coefficients * self.mass)[..., self.order]
        totals = contribution.sum(axis=1)
        if np.any(totals <= 0):
            raise ValueError("存在无法投影到参考谱的样片，请检查比色仪读数。")
        return contribution / totals[:, None], residual

    def as_records(self):
        return [
            {
                "basis": f"参考谱 {index}",
                "center_nm": round(float(self.centroids[column]), 2),
                "normalized_profile": [
                    {"nm": band, "percent": round(float(weight) * 100, 2)}
                    for band, weight in zip(BANDS_NM, profile)
                ],
            }
            for index, (column, profile) in enumerate(zip(self.order, self.profiles), start=1)
        ]
