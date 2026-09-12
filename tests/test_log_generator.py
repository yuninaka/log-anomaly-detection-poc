from datetime import datetime, timedelta, timezone

import pandas as pd

from log_anomaly_detection_poc.log_generator import (
    LOG_COLUMNS,
    generate_logs,
)

START = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)  # 月曜日
MAJORITY_NORMAL_RATIO_THRESHOLD = 0.9


def test_generates_expected_columns_for_seven_days() -> None:
    df = generate_logs(start=START, days=7)

    assert list(df.columns) == LOG_COLUMNS
    assert len(df) > 0


def test_generates_more_rows_for_longer_periods() -> None:
    df_7d = generate_logs(start=START, days=7)
    df_30d = generate_logs(start=START, days=30)

    assert len(df_30d) > len(df_7d)


def test_zero_days_produces_empty_frame() -> None:
    df = generate_logs(start=START, days=0)

    assert df.empty
    assert list(df.columns) == LOG_COLUMNS


def test_same_seed_is_reproducible() -> None:
    df_a = generate_logs(start=START, days=7, seed=1)
    df_b = generate_logs(start=START, days=7, seed=1)

    pd.testing.assert_frame_equal(df_a, df_b)


def test_different_seeds_produce_different_data() -> None:
    df_a = generate_logs(start=START, days=7, seed=1)
    df_b = generate_logs(start=START, days=7, seed=2)

    assert not df_a["latency_ms"].equals(df_b["latency_ms"])


def test_label_distribution_contains_all_three_categories() -> None:
    df = generate_logs(start=START, days=30)

    labels = set(df["label"].unique())
    assert labels == {"normal", "noise", "anomaly"}


def test_normal_is_the_majority_label() -> None:
    df = generate_logs(start=START, days=30)

    normal_ratio = (df["label"] == "normal").mean()
    assert normal_ratio > MAJORITY_NORMAL_RATIO_THRESHOLD


def test_status_codes_are_valid_http_codes() -> None:
    df = generate_logs(start=START, days=7)

    assert df["status_code"].between(100, 599).all()


def test_latency_is_always_positive() -> None:
    df = generate_logs(start=START, days=7)

    assert (df["latency_ms"] > 0).all()


def test_timestamps_are_within_requested_range() -> None:
    days = 7
    df = generate_logs(start=START, days=days)

    end = START + timedelta(days=days)
    assert (df["timestamp"] >= START).all()
    assert (df["timestamp"] < end).all()


def test_anomaly_rows_are_not_labelled_normal() -> None:
    df = generate_logs(start=START, days=14)

    anomaly_rows = df[df["label"] == "anomaly"]
    assert set(anomaly_rows["anomaly_type"].unique()).issubset(
        {"latency_spike", "error_spike"}
    )


def test_noise_rows_do_not_leak_into_anomaly_label() -> None:
    df = generate_logs(start=START, days=14)

    noise_rows = df[df["anomaly_type"] == "isolated_latency_blip"]
    assert (noise_rows["label"] == "noise").all()
