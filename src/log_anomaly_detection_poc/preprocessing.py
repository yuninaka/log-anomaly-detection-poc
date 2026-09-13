from datetime import datetime

import numpy as np
import pandas as pd

# 4xxはクライアント起因(不正リクエスト・認証切れ等)で業務時間中は常に一定割合発生する
# ノイズのため、error_rateには含めない。含めるとStep1のerror_spike異常(5xx急増)の
# シグナルが基準ノイズに埋もれ、STL分解・IsolationForestでの検知精度が落ちる。
SERVER_ERROR_STATUS_THRESHOLD = 500

AGGREGATED_COLUMNS = [
    "window_start",
    "endpoint",
    "avg_latency_ms",
    "error_rate",
    "request_count",
]

GROUND_TRUTH_AGGREGATED_COLUMNS = ["window_start", "endpoint", "label"]
# anomalyがバケット内に1件でもあればanomaly、なければnoiseが1件でもあればnoise、
# それ以外はnormalとする優先度(数値が大きいほど優先)。
LABEL_PRIORITY = {"anomaly": 2, "noise": 1, "normal": 0}


def load_observed_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["timestamp"])


DEFAULT_FREQ = "5min"


def floor_to_bucket(timestamps: pd.Series, freq: str = DEFAULT_FREQ) -> pd.Series:
    """タイムスタンプをfreq単位のバケット開始時刻に丸める。

    data_layers.pyのRawDataRecord構築でも、ここと同じバケット境界を使う必要が
    あるため(MetadataRecordのscenario_idと一致させるため)公開関数にしている。
    """
    return pd.Series(timestamps.dt.floor(freq))


def _bucket_starts(start: datetime, end: datetime, freq: str) -> pd.DatetimeIndex:
    return pd.date_range(start=start, end=end, freq=freq, inclusive="left")


def _assign_buckets(observed: pd.DataFrame, freq: str) -> pd.DataFrame:
    df = observed.copy()
    df["window_start"] = floor_to_bucket(df["timestamp"], freq)
    return df


def _aggregate_buckets(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby(["window_start", "endpoint"])
    return grouped.agg(
        avg_latency_ms=("latency_ms", "mean"),
        request_count=("status_code", "size"),
        error_count=(
            "status_code",
            lambda s: int((s >= SERVER_ERROR_STATUS_THRESHOLD).sum()),
        ),
    ).reset_index()


def _full_grid_index(
    bucket_starts: pd.DatetimeIndex, endpoints: list[str]
) -> pd.MultiIndex:
    return pd.MultiIndex.from_product(
        [bucket_starts, endpoints], names=["window_start", "endpoint"]
    )


def _reindex_to_full_grid(
    aggregated: pd.DataFrame, full_index: pd.MultiIndex
) -> pd.DataFrame:
    indexed = aggregated.set_index(["window_start", "endpoint"])
    reindexed = indexed.reindex(full_index)
    reindexed["request_count"] = reindexed["request_count"].fillna(0).astype(int)
    reindexed["error_count"] = reindexed["error_count"].fillna(0).astype(int)
    return reindexed.reset_index()


def _compute_error_rate(df: pd.DataFrame) -> pd.DataFrame:
    # request_count=0のバケットはエラーも発生しようがないため0.0(NaNにしない)。
    # avg_latency_msは逆にNaNのまま残す(リクエストがなくレイテンシ自体が未定義のため)。
    df["error_rate"] = np.where(
        df["request_count"] > 0, df["error_count"] / df["request_count"], 0.0
    )
    return df.drop(columns=["error_count"])


def _assign_ground_truth_buckets(ground_truth: pd.DataFrame, freq: str) -> pd.DataFrame:
    df = ground_truth.copy()
    df["window_start"] = floor_to_bucket(df["timestamp"], freq)
    return df


def _dominant_label_per_bucket(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_priority"] = df["label"].map(LABEL_PRIORITY)
    dominant_index = df.groupby(["window_start", "endpoint"])["_priority"].idxmax()
    return df.loc[dominant_index, ["window_start", "endpoint", "label"]]


def aggregate_ground_truth(
    ground_truth: pd.DataFrame, start: datetime, end: datetime, freq: str = DEFAULT_FREQ
) -> pd.DataFrame:
    """Step1の生データ層(request単位のground_truth)をバケット単位に集計する。

    aggregate_observed_logsと同じグリッド・バケット境界を使うため、精度評価で
    observed側の集計結果(window_start, endpoint)と直接結合できる。バケット内の
    ラベルはLABEL_PRIORITY順(anomaly > noise > normal)で1つに決める。トラフィックが
    存在しないバケット(observed側でrequest_count=0)は明示的にnormalとする。
    """
    endpoints = (
        sorted(ground_truth["endpoint"].unique()) if not ground_truth.empty else []
    )
    full_index = _full_grid_index(_bucket_starts(start, end, freq), endpoints)

    bucketed = _assign_ground_truth_buckets(ground_truth, freq)
    dominant = _dominant_label_per_bucket(bucketed)
    indexed = dominant.set_index(["window_start", "endpoint"])
    reindexed = indexed.reindex(full_index)
    reindexed["label"] = reindexed["label"].fillna("normal")
    return reindexed.reset_index()[GROUND_TRUTH_AGGREGATED_COLUMNS]


def aggregate_observed_logs(
    observed: pd.DataFrame, start: datetime, end: datetime, freq: str = DEFAULT_FREQ
) -> pd.DataFrame:
    """観測ログをendpoint×freq単位のバケットに集計する。

    start/endの全期間・全エンドポイントを0埋めで網羅した完全なグリッドを返す
    (トラフィックが存在しないバケットも行として存在する)。STL分解が前提とする
    等間隔の時系列を壊さないこと、「トラフィックがない」ことを「データが欠損している」
    と区別できるようにすることが目的。エンドポイント一覧はobserved中に実際に
    出現したものから導出するため、期間中一度も出現しないエンドポイントは含まれない。
    """
    endpoints = sorted(observed["endpoint"].unique()) if not observed.empty else []
    full_index = _full_grid_index(_bucket_starts(start, end, freq), endpoints)

    bucketed = _assign_buckets(observed, freq)
    aggregated = _aggregate_buckets(bucketed)
    reindexed = _reindex_to_full_grid(aggregated, full_index)
    result = _compute_error_rate(reindexed)
    return result[AGGREGATED_COLUMNS]
