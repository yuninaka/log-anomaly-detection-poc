from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from log_anomaly_detection_poc.preprocessing import DEFAULT_FREQ, floor_to_bucket

CUSTOMER_ID_PREFIX = "cust"


@dataclass(frozen=True)
class MetadataRecord:
    """異常検知アルゴリズムが受け取ってよい情報のみを保持する(5分バケット単位)。

    生ログの実測値・顧客IDなどの機微情報は一切含まない。このdataclassのみを
    受け取る型シグネチャにすることで、検知関数への機微データ混入を型レベルで防ぐ。
    """

    scenario_id: str
    module_name: str
    window_start: datetime
    avg_latency_ms: float
    error_rate: float
    request_count: int


@dataclass(frozen=True)
class RawDataRecord:
    """人間が明示的に確認を選択した場合にのみ表示してよい生データ層(リクエスト単位)。

    scenario_idで対応するMetadataRecordのバケットに紐付く。異常検知関数には
    絶対に渡してはならない(別のdataclassのため、渡すとmypyでエラーになる)。
    """

    scenario_id: str
    timestamp: datetime
    endpoint: str
    status_code: int
    latency_ms: float
    customer_id: str


def _scenario_id(module_name: str, window_start: datetime) -> str:
    return f"{module_name}::{window_start.isoformat()}"


def to_metadata_records(aggregated: pd.DataFrame) -> list[MetadataRecord]:
    """Step2の集計結果(aggregate_observed_logsの出力)からメタデータ層を構築する。"""
    return [
        MetadataRecord(
            scenario_id=_scenario_id(endpoint, window_start),
            module_name=endpoint,
            window_start=window_start,
            avg_latency_ms=avg_latency_ms,
            error_rate=error_rate,
            request_count=request_count,
        )
        for window_start, endpoint, avg_latency_ms, error_rate, request_count in zip(
            aggregated["window_start"],
            aggregated["endpoint"],
            aggregated["avg_latency_ms"],
            aggregated["error_rate"],
            aggregated["request_count"],
            strict=True,
        )
    ]


def _synthesize_customer_ids(n: int, seed: int) -> list[str]:
    # 顧客IDを模したダミー文字列。Step1のCSVスキーマには存在しないため、
    # 生データ層を構築するこの関数でのみ合成する(顧客IDそのものは架空の値であり、
    # 検知アルゴリズムに渡ることは絶対にない)。
    rng = np.random.default_rng(seed)
    numbers = rng.integers(0, 1_000_000, size=n)
    return [f"{CUSTOMER_ID_PREFIX}-{number:06d}" for number in numbers]


def _build_raw_record(
    timestamp: datetime,
    endpoint: str,
    status_code: int,
    latency_ms: float,
    window_start: datetime,
    customer_id: str,
) -> RawDataRecord:
    return RawDataRecord(
        scenario_id=_scenario_id(endpoint, window_start),
        timestamp=timestamp,
        endpoint=endpoint,
        status_code=status_code,
        latency_ms=latency_ms,
        customer_id=customer_id,
    )


def to_raw_data_records(
    observed: pd.DataFrame, freq: str = DEFAULT_FREQ, seed: int = 0
) -> list[RawDataRecord]:
    """Step1の観測ログ(LogDataset.observed)から生データ層を構築する。

    scenario_idはMetadataRecordと同じバケット境界(floor_to_bucket)で計算するため、
    同じフリークエンシー(freq)を指定すれば1対多で正しく対応付けられる。
    """
    window_starts = floor_to_bucket(observed["timestamp"], freq)
    customer_ids = _synthesize_customer_ids(len(observed), seed)
    rows = zip(
        observed["timestamp"],
        observed["endpoint"],
        observed["status_code"],
        observed["latency_ms"],
        window_starts,
        customer_ids,
        strict=True,
    )
    return [_build_raw_record(*row) for row in rows]
