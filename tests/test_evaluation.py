import math

import pytest

from log_anomaly_detection_poc.evaluation import (
    classify_by_threshold,
    labels_to_positive_flags,
    precision_recall,
)

TWO_TRUE_POSITIVES = 2


def test_classify_by_threshold_marks_scores_at_or_above_threshold() -> None:
    result = classify_by_threshold([0.0, 2.9, 3.0, 5.0], threshold=3.0)

    assert result == [False, False, True, True]


def test_classify_by_threshold_empty_input() -> None:
    assert classify_by_threshold([], threshold=3.0) == []


def test_precision_recall_perfect_match() -> None:
    result = precision_recall(predicted=[True, False, True], actual=[True, False, True])

    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.true_positive == TWO_TRUE_POSITIVES
    assert result.false_positive == 0
    assert result.false_negative == 0


def test_precision_recall_with_false_positive_and_false_negative() -> None:
    # actual:    anomaly, normal,  anomaly, normal
    # predicted: anomaly, anomaly, normal,  normal
    result = precision_recall(
        predicted=[True, True, False, False], actual=[True, False, True, False]
    )

    assert result.true_positive == 1
    assert result.false_positive == 1
    assert result.false_negative == 1
    assert result.precision == pytest.approx(0.5)
    assert result.recall == pytest.approx(0.5)


def test_precision_recall_no_predicted_positives_precision_is_nan_not_error() -> None:
    # 1件も陽性判定しなかった場合、precisionの分母(TP+FP)が0になり評価不能。
    # 「0%」と誤読されないよう0.0ではなくNaNを返す(0除算エラーにもしない)。
    result = precision_recall(predicted=[False, False], actual=[True, False])

    assert math.isnan(result.precision)
    assert result.recall == 0.0  # 実異常1件を見逃したという実際の0%


def test_precision_recall_no_actual_positives_recall_is_nan_not_error() -> None:
    # 実異常が1件も存在しない場合、recallの分母(TP+FN)が0になり評価不能。
    result = precision_recall(predicted=[True, False], actual=[False, False])

    assert math.isnan(result.recall)
    assert result.precision == 0.0  # 唯一の陽性判定が誤りだったという実際の0%


def test_precision_recall_mismatched_length_raises() -> None:
    with pytest.raises(ValueError, match="length"):
        precision_recall(predicted=[True], actual=[True, False])


def test_labels_to_positive_flags_treats_only_anomaly_as_positive() -> None:
    flags = labels_to_positive_flags(["normal", "noise", "anomaly"])

    assert flags == [False, False, True]
