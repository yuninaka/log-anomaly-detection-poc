from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from log_anomaly_detection_poc.preprocessing import (
    AGGREGATED_COLUMNS,
    GROUND_TRUTH_AGGREGATED_COLUMNS,
    aggregate_ground_truth,
    aggregate_observed_logs,
)

START = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
FREQ = "5min"
TWO_REQUESTS = 2
THREE_BUCKETS = 3


def _observed_row(
    offset_seconds: float, endpoint: str, status_code: int, latency_ms: float
) -> dict[str, object]:
    return {
        "timestamp": START + timedelta(seconds=offset_seconds),
        "endpoint": endpoint,
        "status_code": status_code,
        "latency_ms": latency_ms,
    }


def _empty_observed() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
            "endpoint": pd.Series(dtype="object"),
            "status_code": pd.Series(dtype="int64"),
            "latency_ms": pd.Series(dtype="float64"),
        }
    )


def test_aggregates_average_latency_within_a_bucket() -> None:
    observed = pd.DataFrame(
        [
            _observed_row(0, "/api/login", 200, 100.0),
            _observed_row(60, "/api/login", 200, 200.0),
        ]
    )
    end = START + timedelta(minutes=5)

    result = aggregate_observed_logs(observed, start=START, end=end, freq=FREQ)

    row = result[result["endpoint"] == "/api/login"].iloc[0]
    assert row["avg_latency_ms"] == pytest.approx(150.0)
    assert row["request_count"] == TWO_REQUESTS


def test_empty_observed_input_produces_empty_result() -> None:
    result = aggregate_observed_logs(
        _empty_observed(), start=START, end=START, freq=FREQ
    )

    assert result.empty
    assert list(result.columns) == AGGREGATED_COLUMNS


def test_rows_at_bucket_boundary_go_to_the_correct_bucket() -> None:
    observed = pd.DataFrame(
        [
            _observed_row(299, "/api/login", 200, 100.0),  # 4:59 -> bucket 0
            _observed_row(300, "/api/login", 200, 200.0),  # 5:00 -> bucket 1
        ]
    )
    end = START + timedelta(minutes=10)

    result = aggregate_observed_logs(observed, start=START, end=end, freq=FREQ)
    login = result[result["endpoint"] == "/api/login"].sort_values("window_start")

    assert login.iloc[0]["request_count"] == 1
    assert login.iloc[0]["avg_latency_ms"] == pytest.approx(100.0)
    assert login.iloc[1]["request_count"] == 1
    assert login.iloc[1]["avg_latency_ms"] == pytest.approx(200.0)


def test_error_rate_counts_only_server_errors() -> None:
    observed = pd.DataFrame(
        [
            _observed_row(0, "/api/login", 200, 100.0),
            _observed_row(1, "/api/login", 404, 100.0),
            _observed_row(2, "/api/login", 400, 100.0),
            _observed_row(3, "/api/login", 500, 100.0),
        ]
    )
    end = START + timedelta(minutes=5)

    result = aggregate_observed_logs(observed, start=START, end=end, freq=FREQ)

    row = result[result["endpoint"] == "/api/login"].iloc[0]
    assert row["error_rate"] == pytest.approx(0.25)


def test_bucket_with_only_client_errors_has_zero_error_rate() -> None:
    observed = pd.DataFrame(
        [
            _observed_row(0, "/api/login", 400, 100.0),
            _observed_row(1, "/api/login", 404, 100.0),
        ]
    )
    end = START + timedelta(minutes=5)

    result = aggregate_observed_logs(observed, start=START, end=end, freq=FREQ)

    row = result[result["endpoint"] == "/api/login"].iloc[0]
    assert row["error_rate"] == 0.0


def test_buckets_without_traffic_are_zero_filled() -> None:
    observed = pd.DataFrame([_observed_row(0, "/api/login", 200, 100.0)])
    end = START + timedelta(minutes=15)

    result = aggregate_observed_logs(observed, start=START, end=end, freq=FREQ)
    login = result[result["endpoint"] == "/api/login"].sort_values("window_start")

    assert len(login) == THREE_BUCKETS
    empty_buckets = login.iloc[1:]
    assert (empty_buckets["request_count"] == 0).all()
    assert (empty_buckets["error_rate"] == 0.0).all()
    assert empty_buckets["avg_latency_ms"].isna().all()


def test_endpoints_are_aggregated_independently() -> None:
    observed = pd.DataFrame(
        [
            _observed_row(0, "/api/login", 200, 100.0),
            _observed_row(0, "/api/search", 200, 300.0),
        ]
    )
    end = START + timedelta(minutes=5)

    result = aggregate_observed_logs(observed, start=START, end=end, freq=FREQ)

    login_latency = result[result["endpoint"] == "/api/login"].iloc[0]["avg_latency_ms"]
    search_latency = result[result["endpoint"] == "/api/search"].iloc[0][
        "avg_latency_ms"
    ]
    assert login_latency == pytest.approx(100.0)
    assert search_latency == pytest.approx(300.0)


def test_grid_covers_the_full_requested_period() -> None:
    observed = pd.DataFrame([_observed_row(0, "/api/login", 200, 100.0)])
    days = 1
    end = START + timedelta(days=days)

    result = aggregate_observed_logs(observed, start=START, end=end, freq=FREQ)

    expected_buckets_per_endpoint = int(timedelta(days=days) / timedelta(minutes=5))
    assert len(result) == expected_buckets_per_endpoint
    assert result["window_start"].min() == START
    assert result["window_start"].max() == end - timedelta(minutes=5)


def _ground_truth_row(
    offset_seconds: float, endpoint: str, label: str
) -> dict[str, object]:
    return {
        "timestamp": START + timedelta(seconds=offset_seconds),
        "endpoint": endpoint,
        "label": label,
        "anomaly_type": None,
    }


def _empty_ground_truth() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
            "endpoint": pd.Series(dtype="object"),
            "label": pd.Series(dtype="object"),
            "anomaly_type": pd.Series(dtype="object"),
        }
    )


def test_aggregate_ground_truth_empty_input_produces_empty_result() -> None:
    result = aggregate_ground_truth(
        _empty_ground_truth(), start=START, end=START, freq=FREQ
    )

    assert result.empty
    assert list(result.columns) == GROUND_TRUTH_AGGREGATED_COLUMNS


def test_aggregate_ground_truth_bucket_without_traffic_is_normal() -> None:
    ground_truth = pd.DataFrame([_ground_truth_row(0, "/api/login", "normal")])
    end = START + timedelta(minutes=15)

    result = aggregate_ground_truth(ground_truth, start=START, end=end, freq=FREQ)
    login = result[result["endpoint"] == "/api/login"].sort_values("window_start")

    assert len(login) == THREE_BUCKETS
    assert (login["label"] == "normal").all()


def test_aggregate_ground_truth_anomaly_takes_priority_over_noise() -> None:
    ground_truth = pd.DataFrame(
        [
            _ground_truth_row(0, "/api/login", "noise"),
            _ground_truth_row(1, "/api/login", "anomaly"),
            _ground_truth_row(2, "/api/login", "normal"),
        ]
    )
    end = START + timedelta(minutes=5)

    result = aggregate_ground_truth(ground_truth, start=START, end=end, freq=FREQ)

    row = result[result["endpoint"] == "/api/login"].iloc[0]
    assert row["label"] == "anomaly"


def test_aggregate_ground_truth_noise_takes_priority_over_normal() -> None:
    ground_truth = pd.DataFrame(
        [
            _ground_truth_row(0, "/api/login", "normal"),
            _ground_truth_row(1, "/api/login", "noise"),
        ]
    )
    end = START + timedelta(minutes=5)

    result = aggregate_ground_truth(ground_truth, start=START, end=end, freq=FREQ)

    row = result[result["endpoint"] == "/api/login"].iloc[0]
    assert row["label"] == "noise"


def test_aggregate_ground_truth_grid_matches_observed_grid() -> None:
    observed = pd.DataFrame([_observed_row(0, "/api/login", 200, 100.0)])
    ground_truth = pd.DataFrame([_ground_truth_row(0, "/api/login", "normal")])
    end = START + timedelta(days=1)

    observed_result = aggregate_observed_logs(observed, start=START, end=end, freq=FREQ)
    ground_truth_result = aggregate_ground_truth(
        ground_truth, start=START, end=end, freq=FREQ
    )

    merged = observed_result.merge(
        ground_truth_result, on=["window_start", "endpoint"], how="inner"
    )
    assert len(merged) == len(observed_result) == len(ground_truth_result)
