from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

# sklearn/statsmodelsはpy.typedマーカーを提供していないため型スタブが解決できない
# (外部ライブラリの実装詳細であり、こちら側の型設計の問題ではない)。
from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]
from statsmodels.tsa.seasonal import STL  # type: ignore[import-untyped]

from log_anomaly_detection_poc.data_layers import MetadataRecord

DAILY_PERIOD_AT_FIVE_MIN = 288  # 24h * 60min / 5min足
MIN_POINTS_FOR_STL = 2 * DAILY_PERIOD_AT_FIVE_MIN
MIN_SAMPLES_FOR_ISOLATION_FOREST = 10
ISOLATION_FOREST_ANOMALY_LABEL = -1
DEFAULT_ISOLATION_FOREST_SEED = 0


def _metadata_to_frame(metadata: Sequence[MetadataRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "module_name": [m.module_name for m in metadata],
            "window_start": [m.window_start for m in metadata],
            "avg_latency_ms": [m.avg_latency_ms for m in metadata],
            "error_rate": [m.error_rate for m in metadata],
        }
    )


def _interpolate_latency(values: pd.Series) -> pd.Series:
    # request_count=0のバケットはavg_latency_msがNaN(Step2の設計)。STLも
    # IsolationForestもNaNを扱えないため、時系列順に線形補間する。全点NaNの
    # 場合は補間できないため0で埋める。
    interpolated = values.interpolate(limit_direction="both")
    return pd.Series(interpolated.fillna(0.0))


def _zscore(residual: pd.Series) -> pd.Series:
    std = residual.std(ddof=0)
    if not std or np.isnan(std):
        return pd.Series(np.zeros(len(residual)), index=residual.index)
    return (residual - residual.mean()).abs() / std


def _stl_residual_zscore(series: pd.Series, period: int) -> pd.Series:
    if len(series) < 2 * period:
        return pd.Series(np.zeros(len(series)), index=series.index)
    result = STL(series, period=period, robust=True).fit()
    return _zscore(pd.Series(result.resid, index=series.index))


def _stl_score_for_module(group: pd.DataFrame) -> pd.Series:
    ordered = group.sort_values("window_start")
    latency = _interpolate_latency(ordered["avg_latency_ms"])
    latency_z = _stl_residual_zscore(latency, DAILY_PERIOD_AT_FIVE_MIN)
    error_z = _stl_residual_zscore(ordered["error_rate"], DAILY_PERIOD_AT_FIVE_MIN)
    combined = pd.concat([latency_z, error_z], axis=1).max(axis=1)
    return pd.Series(combined.to_numpy(), index=ordered.index)


def _compute_scores_per_module(
    df: pd.DataFrame,
    score_for_module: Callable[[pd.DataFrame], pd.Series],
    *,
    show_progress: bool,
    label: str,
) -> list[float]:
    modules = sorted(df["module_name"].unique())
    scores = pd.Series(np.zeros(len(df)), index=df.index)
    for i, module_name in enumerate(modules, start=1):
        if show_progress:
            print(f"[{label} {i}/{len(modules)}] {module_name} を計算中...", flush=True)
        group = df[df["module_name"] == module_name]
        scores.loc[group.index] = score_for_module(group)
    return list(scores.sort_index())


def compute_stl_anomaly_score(
    metadata: Sequence[MetadataRecord], *, show_progress: bool = False
) -> list[float]:
    """module_name(=endpoint)ごとにSTL分解し、残差ベースの異常スコアを算出する。

    avg_latency_ms・error_rateそれぞれの残差zスコアのうち大きい方を採用する
    (latency_spike・error_spikeの両方の異常パターンを拾うため)。STLはrobust=True
    (反復再重み付け)で実行するため、データ量が大きいと数十秒〜数分かかる。
    show_progress=Trueでモジュールごとの進捗を表示できる(手動実行スクリプト向け)。
    """
    if not metadata:
        return []
    df = _metadata_to_frame(metadata)
    return _compute_scores_per_module(
        df, _stl_score_for_module, show_progress=show_progress, label="STL"
    )


def _isolation_forest_score_for_module(group: pd.DataFrame, seed: int) -> pd.Series:
    ordered = group.sort_values("window_start")
    features = pd.DataFrame(
        {
            "avg_latency_ms": _interpolate_latency(ordered["avg_latency_ms"]),
            "error_rate": ordered["error_rate"],
        }
    )
    if len(features) < MIN_SAMPLES_FOR_ISOLATION_FOREST:
        return pd.Series(np.zeros(len(ordered)), index=ordered.index)

    model = IsolationForest(contamination="auto", random_state=seed)
    predictions = model.fit_predict(features)
    is_anomaly = predictions == ISOLATION_FOREST_ANOMALY_LABEL
    return pd.Series(np.where(is_anomaly, 1.0, 0.0), index=ordered.index)


def compute_isolation_forest_anomaly_score(
    metadata: Sequence[MetadataRecord],
    seed: int = DEFAULT_ISOLATION_FOREST_SEED,
    *,
    show_progress: bool = False,
) -> list[float]:
    """module_name(=endpoint)ごとにIsolationForestをfitし、多変量異常検知を行う。

    特徴量はavg_latency_ms・error_rateの2つ。request_countは特徴量に含めない
    (深夜の正常な低トラフィックが誤検知の原因になるため)。contamination="auto"
    はscikit-learn内部の推定であり、正解ラベルは一切使用しない。
    """
    if not metadata:
        return []
    df = _metadata_to_frame(metadata)
    return _compute_scores_per_module(
        df,
        lambda group: _isolation_forest_score_for_module(group, seed),
        show_progress=show_progress,
        label="IsolationForest",
    )
