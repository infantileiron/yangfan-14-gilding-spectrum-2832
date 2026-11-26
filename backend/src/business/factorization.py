import warnings

import numpy as np
from sklearn.decomposition import NMF
from sklearn.exceptions import ConvergenceWarning

from .spectra import BANDS_NM


class ReferenceSpectra:
    def __init__(self, training):
        self.model = self._new_model()
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            try:
                self.model.fit(training)
            except ConvergenceWarning as exc:
                raise ValueError("参考谱分解未收敛。请检查参照片的测量质量与覆盖范围。") from exc
        self._update_state(self.model.components_)

    @staticmethod
    def _new_model():
        return NMF(n_components=3, init="nndsvda", random_state=414, tol=1e-5, max_iter=2500)

    def _update_state(self, components):
        self.mass = components.sum(axis=1)
        if np.any(self.mass <= 0):
            raise ValueError("有参考谱的全部波段为零，请补充有效参照片。")
        normalized = components / self.mass[:, None]
        self.centroids = normalized @ np.asarray(BANDS_NM)
        self.order = np.argsort(self.centroids, kind="stable")
        self.profiles = normalized[self.order]

    @classmethod
    def restore(cls, state):
        """Rebuild a fixed spectrum set from a JSON-safe :meth:`snapshot`."""
        if isinstance(state, ReferenceSpectra):
            return state
        if not isinstance(state, dict) or "components" not in state:
            raise ValueError("参考谱版本缺少可恢复的谱分量。")
        components = np.asarray(state["components"], dtype=float)
        if components.shape != (3, len(BANDS_NM)) or not np.all(np.isfinite(components)):
            raise ValueError("参考谱版本的谱分量格式不正确。")

        obj = cls.__new__(cls)
        obj.model = cls._new_model()
        # Fit a tiny valid matrix only to initialize all private sklearn state;
        # the persisted components immediately replace the dummy solution.
        dummy = np.asarray([
            [1, 2, 3, 4, 5, 6],
            [6, 5, 4, 3, 2, 1],
            [1, 3, 5, 7, 9, 11],
            [2, 4, 6, 8, 10, 12],
            [6, 4, 2, 1, 3, 5],
            [1, 1, 2, 3, 5, 8],
        ], dtype=float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            obj.model.fit(dummy)
        obj.model.components_ = components.copy()

        if "mass" in state and "order" in state and "centroids" in state and "profiles" in state:
            obj.mass = np.asarray(state["mass"], dtype=float)
            obj.order = np.asarray(state["order"], dtype=int)
            obj.centroids = np.asarray(state["centroids"], dtype=float)
            obj.profiles = np.asarray(state["profiles"], dtype=float)
        else:
            obj._update_state(components)
        if obj.order.shape != (3,) or obj.profiles.shape != (3, len(BANDS_NM)):
            raise ValueError("参考谱版本的排序状态不正确。")
        return obj

    def snapshot(self):
        return {
            "components": self.model.components_.tolist(),
            "mass": [float(x) for x in self.mass],
            "order": [int(x) for x in self.order],
            "centroids": [float(x) for x in self.centroids],
            "profiles": self.profiles.tolist(),
            "records": self.as_records(),
        }

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
