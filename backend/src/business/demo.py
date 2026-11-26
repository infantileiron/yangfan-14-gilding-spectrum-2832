from random import Random

from .spectra import BAND_FIELDS

REFERENCE = (
    (67, 69, 55, 42, 26, 19),
    (16, 44, 63, 59, 38, 22),
    (9, 17, 29, 54, 75, 88),
)
SURFACES = ("封闭基底", "仿旧基底", "过渡基底")


def patch(sample_id, split, surface, shares, rng, spike=0):
    spectrum = [
        round(sum(share * value for share, value in zip(shares, values)) + rng.gauss(0, 0.25), 3)
        for values in zip(*REFERENCE)
    ]
    spectrum[2] += spike
    return {"sample_id": sample_id, "split": split, "surface": surface, **dict(zip(BAND_FIELDS, spectrum))}


def demo_rows():
    rng = Random(1416)
    rows = []
    for index in range(96):
        dominant = index % 3
        if index < 9:
            shares = [float(component == dominant) for component in range(3)]
        else:
            weights = [rng.uniform(0.08, 0.8) * (3 if component == dominant else 1) for component in range(3)]
            shares = [weight / sum(weights) for weight in weights]
        rows.append(patch(f"YG-R{index + 1:03}", "参照" if index < 72 else "复核",
                          SURFACES[dominant], shares, rng))
    candidates = [
        ((.78, .12, .10), 0), ((.25, .45, .30), 36), ((.18, .13, .69), 0),
        ((.17, .67, .16), -19), ((.52, .38, .10), 0), ((.19, .37, .44), 0),
        ((.44, .13, .43), 16), ((.24, .56, .20), 0),
    ]
    rows.extend(patch(f"YG-P{index:02}", "待验", SURFACES[(index - 1) % 3], shares, rng, spike)
                for index, (shares, spike) in enumerate(candidates, start=1))
    return rows
