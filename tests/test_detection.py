from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from log_anomaly_detection_poc.data_layers import MetadataRecord
from log_anomaly_detection_poc.detection import (
    DAILY_PERIOD_AT_FIVE_MIN,
    MIN_SAMPLES_FOR_ISOLATION_FOREST,
    _interpolate_latency,
    _stl_residual_zscore,
    _zscore,
    compute_isolation_forest_anomaly_score,
    compute_stl_anomaly_score,
)

START = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)


def _records(
    module_name: str, latencies: list[float], error_rates: list[float] | None = None
) -> list[MetadataRecord]:
    error_rates = error_rates or [0.0] * len(latencies)
    return [
        MetadataRecord(
            scenario_id=f"{module_name}-{i}",
            module_name=module_name,
            window_start=START + timedelta(minutes=5 * i),
            avg_latency_ms=latency,
            error_rate=error_rate,
            request_count=5,
        )
        for i, (latency, error_rate) in enumerate(
            zip(latencies, error_rates, strict=True)
        )
    ]


def test_zscore_of_constant_series_is_zero_not_nan() -> None:
    constant = pd.Series([5.0, 5.0, 5.0])

    result = _zscore(constant)

    assert (result == 0.0).all()


def test_zscore_flags_the_outlier() -> None:
    series = pd.Series([10.0, 10.0, 10.0, 100.0])

    result = _zscore(series)

    assert result.iloc[3] > result.iloc[0]


def test_interpolate_latency_fills_nan_between_known_points() -> None:
    values = pd.Series([100.0, np.nan, 200.0])

    result = _interpolate_latency(values)

    assert result.iloc[1] == pytest.approx(150.0)


def test_interpolate_latency_all_nan_falls_back_to_zero() -> None:
    values = pd.Series([np.nan, np.nan])

    result = _interpolate_latency(values)

    assert (result == 0.0).all()


def test_stl_residual_zscore_returns_zeros_when_too_short() -> None:
    series = pd.Series([1.0, 2.0, 3.0])

    result = _stl_residual_zscore(series, period=DAILY_PERIOD_AT_FIVE_MIN)

    assert (result == 0.0).all()


def test_compute_stl_anomaly_score_empty_input() -> None:
    assert compute_stl_anomaly_score([]) == []


def test_compute_stl_anomaly_score_returns_one_score_per_record() -> None:
    records = _records("mod", [100.0] * 10)

    scores = compute_stl_anomaly_score(records)

    assert len(scores) == len(records)


def test_compute_stl_anomaly_score_short_series_is_all_zero() -> None:
    records = _records("mod", [100.0, 500.0, 100.0])

    scores = compute_stl_anomaly_score(records)

    assert scores == [0.0, 0.0, 0.0]


def test_compute_stl_anomaly_score_preserves_input_order_across_modules() -> None:
    records = _records("a", [100.0, 100.0]) + _records("b", [200.0, 200.0])

    scores = compute_stl_anomaly_score(records)

    assert len(scores) == len(records)


def test_compute_stl_anomaly_score_detects_a_sustained_latency_spike() -> None:
    n = 3 * DAILY_PERIOD_AT_FIVE_MIN
    rng = np.random.default_rng(0)
    latencies = (100 + rng.normal(0, 2, n)).tolist()
    spike_start, spike_end = 400, 415
    for i in range(spike_start, spike_end):
        latencies[i] += 300
    records = _records("mod", latencies)

    scores = compute_stl_anomaly_score(records)

    baseline_max = max(
        score for i, score in enumerate(scores) if not (spike_start <= i < spike_end)
    )
    spike_min = min(scores[spike_start:spike_end])
    assert spike_min > baseline_max


def test_compute_isolation_forest_anomaly_score_empty_input() -> None:
    assert compute_isolation_forest_anomaly_score([]) == []


def test_compute_isolation_forest_anomaly_score_too_few_samples_is_all_zero() -> None:
    records = _records("mod", [100.0] * (MIN_SAMPLES_FOR_ISOLATION_FOREST - 1))

    scores = compute_isolation_forest_anomaly_score(records)

    assert scores == [0.0] * len(records)


def test_compute_isolation_forest_anomaly_score_flags_multivariate_outliers() -> None:
    rng = np.random.default_rng(0)
    n = 100
    latencies = (100 + rng.normal(0, 2, n)).tolist()
    error_rates = [0.0] * n
    outlier_indices = [10, 50, 90]
    for i in outlier_indices:
        latencies[i] = 800.0
        error_rates[i] = 0.9
    records = _records("mod", latencies, error_rates)

    scores = compute_isolation_forest_anomaly_score(records, seed=0)

    for i in outlier_indices:
        assert scores[i] == 1.0
