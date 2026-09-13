from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pandas as pd

from log_anomaly_detection_poc.data_layers import MetadataRecord, to_metadata_records
from log_anomaly_detection_poc.detection import (
    compute_isolation_forest_anomaly_score,
    compute_stl_anomaly_score,
)
from log_anomaly_detection_poc.evaluation import (
    ISOLATION_FOREST_ANOMALY_THRESHOLD,
    STL_ANOMALY_THRESHOLD,
)
from log_anomaly_detection_poc.log_generator import DEFAULT_SEED, generate_logs
from log_anomaly_detection_poc.preprocessing import aggregate_observed_logs
from log_anomaly_detection_poc.silent_mode import (
    SilentModeRecord,
    accumulate_silent_mode_records,
)

# UI用の評価対象開始日時。evaluate_cli.DEFAULT_EVAL_STARTと同じ値を使うことで、
# Step4/5の実測結果(所要時間・精度)がUIでもそのまま参考値として使える。
PIPELINE_START = datetime(2026, 1, 5, tzinfo=timezone.utc)
DAY_COUNT_CHOICES = [7, 14, 30]


def run_detection_pipeline(
    days: int, seed: int = DEFAULT_SEED
) -> tuple[pd.DataFrame, list[MetadataRecord], list[SilentModeRecord]]:
    """本番相当の検知パイプラインを実行する(ground_truthは一切使わない)。

    Step4/5の評価パイプライン(evaluate_cli.evaluate_at_scale)は正解ラベルと
    突き合わせて精度を測るためのものだが、本番運用では正解ラベルは存在しない。
    Step6はこの本番相当の経路を独立して持つ。戻り値の観測ログDataFrameは、
    人間が生データ層の開示を選択した場合にui.py側でraw_data_records_for_window
    に渡すために保持する。MetadataRecordのリストは、SilentModeRecord.scenario_id
    からmodule_name・window_start(raw_data_records_for_windowの引数)を
    引くために返す。
    """
    start = PIPELINE_START
    end = start + timedelta(days=days)
    dataset = generate_logs(start=start, days=days, seed=seed)

    observed_agg = aggregate_observed_logs(dataset.observed, start=start, end=end)
    metadata = to_metadata_records(observed_agg)

    stl_scores = compute_stl_anomaly_score(metadata)
    if_scores = compute_isolation_forest_anomaly_score(metadata)

    records = accumulate_silent_mode_records(
        metadata, stl_scores, STL_ANOMALY_THRESHOLD, "STL"
    ) + accumulate_silent_mode_records(
        metadata, if_scores, ISOLATION_FOREST_ANOMALY_THRESHOLD, "IsolationForest"
    )
    return dataset.observed, metadata, records


def flagged_records(
    records: Sequence[SilentModeRecord],
) -> list[SilentModeRecord]:
    return [r for r in records if r.flagged]


def metadata_by_scenario_id(
    metadata: Sequence[MetadataRecord],
) -> dict[str, MetadataRecord]:
    """scenario_idからMetadataRecordを引く辞書を作る。

    SilentModeRecordはscenario_idしか持たないため、ui.pyが「生データ層を
    確認する」ボタン押下時にmodule_name・window_start(raw_data_records_for_window
    の引数)を得るために使う。
    """
    return {m.scenario_id: m for m in metadata}
