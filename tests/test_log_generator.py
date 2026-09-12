from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from log_anomaly_detection_poc.log_generator import (
    DAYS_PER_WEEK,
    GROUND_TRUTH_COLUMNS,
    OBSERVED_COLUMNS,
    generate_logs,
)

START = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)  # 月曜日
MAJORITY_NORMAL_RATIO_THRESHOLD = 0.9
EPISODE_GAP = timedelta(hours=2)


def _count_episodes(timestamps: pd.Series) -> int:
    if timestamps.empty:
        return 0
    ordered = timestamps.sort_values()
    is_new_episode = ordered.diff() > EPISODE_GAP
    return int(is_new_episode.sum()) + 1


def test_generates_expected_columns_for_seven_days() -> None:
    dataset = generate_logs(start=START, days=7)

    assert list(dataset.observed.columns) == OBSERVED_COLUMNS
    assert list(dataset.ground_truth.columns) == GROUND_TRUTH_COLUMNS
    assert len(dataset.observed) == len(dataset.ground_truth) > 0


def test_observed_frame_never_contains_ground_truth_columns() -> None:
    dataset = generate_logs(start=START, days=14)

    assert "label" not in dataset.observed.columns
    assert "anomaly_type" not in dataset.observed.columns


def test_generates_more_rows_for_longer_periods() -> None:
    dataset_7d = generate_logs(start=START, days=7)
    dataset_30d = generate_logs(start=START, days=30)

    assert len(dataset_30d.observed) > len(dataset_7d.observed)


def test_zero_days_produces_empty_frame() -> None:
    dataset = generate_logs(start=START, days=0)

    assert dataset.observed.empty
    assert dataset.ground_truth.empty
    assert list(dataset.observed.columns) == OBSERVED_COLUMNS


def test_negative_days_raises_value_error() -> None:
    with pytest.raises(ValueError, match="days"):
        generate_logs(start=START, days=-1)


def test_same_seed_is_reproducible() -> None:
    dataset_a = generate_logs(start=START, days=7, seed=1)
    dataset_b = generate_logs(start=START, days=7, seed=1)

    pd.testing.assert_frame_equal(dataset_a.observed, dataset_b.observed)
    pd.testing.assert_frame_equal(dataset_a.ground_truth, dataset_b.ground_truth)


def test_different_seeds_produce_different_data() -> None:
    dataset_a = generate_logs(start=START, days=7, seed=1)
    dataset_b = generate_logs(start=START, days=7, seed=2)

    assert not dataset_a.observed["latency_ms"].equals(dataset_b.observed["latency_ms"])


def test_arbitrary_day_count_is_accepted() -> None:
    dataset = generate_logs(start=START, days=20)

    end = START + timedelta(days=20)
    assert (dataset.observed["timestamp"] < end).all()


def test_label_distribution_contains_all_three_categories() -> None:
    dataset = generate_logs(start=START, days=30)

    labels = set(dataset.ground_truth["label"].unique())
    assert labels == {"normal", "noise", "anomaly"}


def test_normal_is_the_majority_label() -> None:
    dataset = generate_logs(start=START, days=30)

    normal_ratio = (dataset.ground_truth["label"] == "normal").mean()
    assert normal_ratio > MAJORITY_NORMAL_RATIO_THRESHOLD


def test_status_codes_are_valid_http_codes() -> None:
    dataset = generate_logs(start=START, days=7)

    assert dataset.observed["status_code"].between(100, 599).all()


def test_latency_is_always_positive() -> None:
    dataset = generate_logs(start=START, days=7)

    assert (dataset.observed["latency_ms"] > 0).all()


def test_timestamps_are_within_requested_range() -> None:
    days = 7
    dataset = generate_logs(start=START, days=days)

    end = START + timedelta(days=days)
    assert (dataset.observed["timestamp"] >= START).all()
    assert (dataset.observed["timestamp"] < end).all()


def test_anomaly_rows_are_not_labelled_normal() -> None:
    dataset = generate_logs(start=START, days=14)

    anomaly_rows = dataset.ground_truth[dataset.ground_truth["label"] == "anomaly"]
    assert set(anomaly_rows["anomaly_type"].unique()).issubset(
        {"latency_spike", "error_spike"}
    )


def test_noise_rows_do_not_leak_into_anomaly_label() -> None:
    dataset = generate_logs(start=START, days=14)

    noise_rows = dataset.ground_truth[
        dataset.ground_truth["anomaly_type"] == "isolated_latency_blip"
    ]
    assert (noise_rows["label"] == "noise").all()


def test_injected_episode_count_is_deterministic_per_week() -> None:
    days = 21
    weeks = days // DAYS_PER_WEEK
    dataset = generate_logs(start=START, days=days)

    for anomaly_type in ("latency_spike", "error_spike"):
        rows = dataset.ground_truth[
            dataset.ground_truth["anomaly_type"] == anomaly_type
        ]
        assert _count_episodes(rows["timestamp"]) == weeks
