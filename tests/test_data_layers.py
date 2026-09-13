from datetime import datetime, timedelta, timezone

import pandas as pd

from log_anomaly_detection_poc.data_layers import (
    MetadataRecord,
    RawDataRecord,
    to_metadata_records,
    to_raw_data_records,
)
from log_anomaly_detection_poc.log_generator import generate_logs
from log_anomaly_detection_poc.preprocessing import aggregate_observed_logs

START = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
FIRST_BUCKET_LATENCY_MS = 120.0
FIRST_BUCKET_ERROR_RATE = 0.05
FIRST_BUCKET_REQUEST_COUNT = 3
TWO_BUCKETS = 2


def _aggregated_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "window_start": START,
                "endpoint": "/api/login",
                "avg_latency_ms": 120.0,
                "error_rate": 0.05,
                "request_count": 3,
            },
            {
                "window_start": START + timedelta(minutes=5),
                "endpoint": "/api/login",
                "avg_latency_ms": 0.0,
                "error_rate": 0.0,
                "request_count": 0,
            },
        ]
    )


def test_to_metadata_records_maps_columns_correctly() -> None:
    records = to_metadata_records(_aggregated_frame())

    assert len(records) == TWO_BUCKETS
    first = records[0]
    assert isinstance(first, MetadataRecord)
    assert first.module_name == "/api/login"
    assert first.window_start == START
    assert first.avg_latency_ms == FIRST_BUCKET_LATENCY_MS
    assert first.error_rate == FIRST_BUCKET_ERROR_RATE
    assert first.request_count == FIRST_BUCKET_REQUEST_COUNT


def test_to_metadata_records_scenario_id_is_unique_per_bucket() -> None:
    records = to_metadata_records(_aggregated_frame())

    scenario_ids = {r.scenario_id for r in records}
    assert len(scenario_ids) == len(records)


def test_to_metadata_records_empty_input_produces_empty_list() -> None:
    empty = _aggregated_frame().iloc[0:0]

    assert to_metadata_records(empty) == []


def test_to_raw_data_records_does_not_leak_ground_truth_columns() -> None:
    observed = pd.DataFrame(
        [
            {
                "timestamp": START,
                "endpoint": "/api/login",
                "status_code": 200,
                "latency_ms": 100.0,
            }
        ]
    )

    records = to_raw_data_records(observed)

    assert len(records) == 1
    assert isinstance(records[0], RawDataRecord)
    assert not hasattr(records[0], "label")
    assert not hasattr(records[0], "anomaly_type")


def test_to_raw_data_records_customer_id_is_synthesized_and_reproducible() -> None:
    observed = pd.DataFrame(
        [
            {
                "timestamp": START,
                "endpoint": "/api/login",
                "status_code": 200,
                "latency_ms": 100.0,
            }
        ]
    )

    records_a = to_raw_data_records(observed, seed=1)
    records_b = to_raw_data_records(observed, seed=1)
    records_c = to_raw_data_records(observed, seed=2)

    assert records_a[0].customer_id == records_b[0].customer_id
    assert records_a[0].customer_id != records_c[0].customer_id
    assert records_a[0].customer_id.startswith("cust-")


def test_raw_and_metadata_scenario_ids_correspond_to_the_same_bucket() -> None:
    dataset = generate_logs(start=START, days=1, seed=1)
    end = START + timedelta(days=1)
    aggregated = aggregate_observed_logs(dataset.observed, start=START, end=end)

    metadata_records = to_metadata_records(aggregated)
    raw_records = to_raw_data_records(dataset.observed)

    metadata_scenario_ids = {r.scenario_id for r in metadata_records}
    raw_scenario_ids = {r.scenario_id for r in raw_records}
    assert raw_scenario_ids.issubset(metadata_scenario_ids)
