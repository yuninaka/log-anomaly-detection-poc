from collections.abc import Sequence
from dataclasses import dataclass

STL_ANOMALY_THRESHOLD = 3.0
ISOLATION_FOREST_ANOMALY_THRESHOLD = 1.0
# noiseは「ただのノイズ」であり、正解ラベルとしては陽性(anomaly)に含めない。
# ノイズを誤って検知しないことこそがこのPoCの価値であるため、noiseを陽性扱い
# すると評価がこの価値を測れなくなる。
POSITIVE_LABEL = "anomaly"


@dataclass(frozen=True)
class PrecisionRecall:
    precision: float
    recall: float
    true_positive: int
    false_positive: int
    false_negative: int


def classify_by_threshold(scores: Sequence[float], threshold: float) -> list[bool]:
    return [score >= threshold for score in scores]


def precision_recall(
    predicted: Sequence[bool], actual: Sequence[bool]
) -> PrecisionRecall:
    if len(predicted) != len(actual):
        raise ValueError("predicted and actual must have the same length")

    true_positive = sum(p and a for p, a in zip(predicted, actual, strict=True))
    false_positive = sum(p and not a for p, a in zip(predicted, actual, strict=True))
    false_negative = sum(not p and a for p, a in zip(predicted, actual, strict=True))

    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)

    return PrecisionRecall(
        precision=precision,
        recall=recall,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    # 分母が0の場合は「0%」ではなく「評価不能」なのでNaNを返す(例: 実異常が
    # 1件もないためrecallの分母(TP+FN)が0になるケース)。0.0で埋めると
    # 「検知に完全失敗した」と誤読されるため区別する。
    return numerator / denominator if denominator > 0 else float("nan")


def labels_to_positive_flags(labels: Sequence[str]) -> list[bool]:
    return [label == POSITIVE_LABEL for label in labels]
