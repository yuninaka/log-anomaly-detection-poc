from datetime import datetime, timezone

from log_anomaly_detection_poc.data_layers import MetadataRecord
from log_anomaly_detection_poc.silent_mode import SilentModeRecord
from log_anomaly_detection_poc.ui_logic import (
    flagged_records,
    metadata_by_scenario_id,
    run_detection_pipeline,
)

START = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _record(scenario_id: str, flagged: bool) -> SilentModeRecord:
    return SilentModeRecord(
        scenario_id=scenario_id, algorithm="STL", score=0.0, flagged=flagged
    )


def test_flagged_records_filters_out_unflagged() -> None:
    records = [_record("a", True), _record("b", False), _record("c", True)]

    result = flagged_records(records)

    assert [r.scenario_id for r in result] == ["a", "c"]


def test_flagged_records_empty_input() -> None:
    assert flagged_records([]) == []


def _metadata(scenario_id: str) -> MetadataRecord:
    return MetadataRecord(
        scenario_id=scenario_id,
        module_name="/api/login",
        window_start=START,
        avg_latency_ms=100.0,
        error_rate=0.0,
        request_count=5,
    )


def test_metadata_by_scenario_id_builds_lookup() -> None:
    metadata = [_metadata("a"), _metadata("b")]

    lookup = metadata_by_scenario_id(metadata)

    assert lookup["a"].scenario_id == "a"
    assert lookup["b"].scenario_id == "b"


def test_metadata_by_scenario_id_empty_input() -> None:
    assert metadata_by_scenario_id([]) == {}


def test_run_detection_pipeline_returns_consistent_scenario_ids() -> None:
    # 1日分の実データで実行し、observed/metadata/recordsが正しく対応することを
    # 実リソースに対する実行で確認する(前提制約2: フォアグラウンドで実行時間を計測)。
    observed, metadata, records = run_detection_pipeline(days=1, seed=1)

    assert not observed.empty
    assert len(metadata) > 0
    # STL・IsolationForestそれぞれが全メタデータレコード分のスコアを持つため、
    # recordsの件数はmetadataの2倍になる。
    assert len(records) == len(metadata) * 2

    metadata_scenario_ids = {m.scenario_id for m in metadata}
    assert {r.scenario_id for r in records}.issubset(metadata_scenario_ids)
