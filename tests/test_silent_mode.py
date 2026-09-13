import math
from datetime import datetime, timezone

from log_anomaly_detection_poc.data_layers import MetadataRecord
from log_anomaly_detection_poc.evaluation import PrecisionRecall
from log_anomaly_detection_poc.silent_mode import (
    SilentModeRecord,
    accumulate_silent_mode_records,
    decide_production_readiness,
)

START = datetime(2026, 1, 5, tzinfo=timezone.utc)
THRESHOLD = 3.0


def _record(scenario_id: str) -> MetadataRecord:
    return MetadataRecord(
        scenario_id=scenario_id,
        module_name="/api/login",
        window_start=START,
        avg_latency_ms=100.0,
        error_rate=0.0,
        request_count=5,
    )


def test_accumulate_marks_scores_at_or_above_threshold_as_flagged() -> None:
    metadata = [_record("a"), _record("b"), _record("c")]
    scores = [0.0, 2.9, 3.0]

    records = accumulate_silent_mode_records(metadata, scores, THRESHOLD, "STL")

    assert [r.flagged for r in records] == [False, False, True]


def test_accumulate_preserves_order_and_identity() -> None:
    metadata = [_record("a"), _record("b")]
    scores = [10.0, 0.0]

    records = accumulate_silent_mode_records(metadata, scores, THRESHOLD, "STL")

    assert records == [
        SilentModeRecord(scenario_id="a", algorithm="STL", score=10.0, flagged=True),
        SilentModeRecord(scenario_id="b", algorithm="STL", score=0.0, flagged=False),
    ]


def test_accumulate_empty_input() -> None:
    assert accumulate_silent_mode_records([], [], THRESHOLD, "STL") == []


def _pr(precision: float) -> PrecisionRecall:
    return PrecisionRecall(
        precision=precision,
        recall=0.0,
        true_positive=0,
        false_positive=0,
        false_negative=0,
    )


def test_decide_production_readiness_above_threshold_is_ready() -> None:
    decision = decide_production_readiness("STL", _pr(0.6), threshold=0.5)

    assert decision.ready_for_production is True
    assert decision.reason == "ready"


def test_decide_production_readiness_exactly_at_threshold_is_ready() -> None:
    decision = decide_production_readiness("STL", _pr(0.5), threshold=0.5)

    assert decision.ready_for_production is True
    assert decision.reason == "ready"


def test_decide_production_readiness_below_threshold_is_insufficient_precision() -> (
    None
):
    decision = decide_production_readiness("STL", _pr(0.13), threshold=0.5)

    assert decision.ready_for_production is False
    assert decision.reason == "insufficient_precision"


def test_decide_production_readiness_nan_precision_is_insufficient_samples() -> None:
    decision = decide_production_readiness("STL", _pr(math.nan), threshold=0.5)

    assert decision.ready_for_production is False
    assert decision.reason == "insufficient_samples"
    assert math.isnan(decision.precision)
