import argparse
import math
import time
from datetime import datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 -- matplotlib.use()の後に読み込む必要がある
import pandas as pd  # noqa: E402 -- 同上

from log_anomaly_detection_poc.data_layers import to_metadata_records  # noqa: E402
from log_anomaly_detection_poc.detection import (  # noqa: E402
    compute_isolation_forest_anomaly_score,
    compute_stl_anomaly_score,
)
from log_anomaly_detection_poc.evaluation import (  # noqa: E402
    ISOLATION_FOREST_ANOMALY_THRESHOLD,
    STL_ANOMALY_THRESHOLD,
    PrecisionRecall,
    classify_by_threshold,
    labels_to_positive_flags,
    precision_recall,
)
from log_anomaly_detection_poc.log_generator import DEFAULT_SEED, generate_logs  # noqa: E402
from log_anomaly_detection_poc.preprocessing import (  # noqa: E402
    aggregate_ground_truth,
    aggregate_observed_logs,
)
from log_anomaly_detection_poc.silent_mode import (  # noqa: E402
    DEFAULT_PROMOTION_THRESHOLD,
    SilentModeDecision,
    decide_production_readiness,
)

# 日本語ラベルを描画するため、CJK対応フォントを優先する(なければDejaVu Sansに
# フォールバックし、グリフ欠落の警告付きで英数字以外が表示されなくなる)。
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "Noto Sans CJK JP",
    "IPAexGothic",
    "Hiragino Sans",
    "DejaVu Sans",
]

# 評価結果の再現性のため、実行時刻(datetime.now())ではなく固定の開始日時を使う。
DEFAULT_EVAL_START = datetime(2026, 1, 5, tzinfo=timezone.utc)
DAY_COUNTS = [7, 14, 30]
DEFAULT_OUTPUT_PATH = "data/precision_recall.png"

# 深夜等の低トラフィックバケットはrequest_countが極端に少なく、avg_latency_msの
# 分散が統計的に安定しないため異常判定が信頼できない。「平均レイテンシの分散が
# 統計的に安定する最低限のサンプル数」という独立した基準で決めており、
# precisionを最大化するための閾値探索ではない。
MIN_REQUEST_COUNT_FOR_EVALUATION = 5


def evaluate_at_scale(
    days: int, seed: int = DEFAULT_SEED, show_progress: bool = False
) -> pd.DataFrame:
    """指定日数分のログを生成し、検知結果と正解ラベルを結合したDataFrameを返す。"""
    start = DEFAULT_EVAL_START
    end = start + timedelta(days=days)
    dataset = generate_logs(start=start, days=days, seed=seed)

    observed_agg = aggregate_observed_logs(dataset.observed, start=start, end=end)
    ground_truth_agg = aggregate_ground_truth(
        dataset.ground_truth, start=start, end=end
    )
    metadata = to_metadata_records(observed_agg)

    observed_agg = observed_agg.assign(
        stl_score=compute_stl_anomaly_score(metadata, show_progress=show_progress),
        if_score=compute_isolation_forest_anomaly_score(
            metadata, show_progress=show_progress
        ),
    )
    return observed_agg.merge(ground_truth_agg, on=["window_start", "endpoint"])


def _summarize_subset(subset: pd.DataFrame) -> dict[str, PrecisionRecall]:
    actual = labels_to_positive_flags(subset["label"].tolist())
    stl_predicted = classify_by_threshold(
        subset["stl_score"].tolist(), STL_ANOMALY_THRESHOLD
    )
    if_predicted = classify_by_threshold(
        subset["if_score"].tolist(), ISOLATION_FOREST_ANOMALY_THRESHOLD
    )
    return {
        "STL": precision_recall(stl_predicted, actual),
        "IsolationForest": precision_recall(if_predicted, actual),
    }


def summarize(merged: pd.DataFrame) -> dict[str, dict[str, PrecisionRecall]]:
    """フィルタなし・最小リクエスト数フィルタあり両方でprecision/recallを算出する。

    フィルタなしの数値は「低トラフィックバケットが誤検知を支配する」という
    事実そのものを示す記録として残し、フィルタありの数値をグラフ化に使う。
    """
    filtered = merged[merged["request_count"] >= MIN_REQUEST_COUNT_FOR_EVALUATION]
    return {
        "unfiltered": _summarize_subset(merged),
        "filtered": _summarize_subset(filtered),
    }


def plot_precision_by_days(
    results: dict[int, dict[str, PrecisionRecall]], output_path: str
) -> None:
    days_list = sorted(results.keys())
    fig, ax = plt.subplots()
    for algorithm in ("STL", "IsolationForest"):
        precisions = [results[days][algorithm].precision for days in days_list]
        ax.plot(days_list, precisions, marker="o", label=algorithm)
    ax.set_xlabel("学習データ量(日数)")
    ax.set_ylabel("precision")
    ax.set_title(
        f"学習データ量に対するprecisionの推移(request_count>={MIN_REQUEST_COUNT_FOR_EVALUATION})"
    )
    ax.set_ylim(0, 1.05)
    ax.legend()
    fig.savefig(output_path)
    plt.close(fig)


def _format_ratio(value: float) -> str:
    # NaNは「評価不能(分母が0)」を表す。0.000と表示すると「完全に失敗した」と
    # 誤読されるため、N/Aと明示する。
    return "N/A" if math.isnan(value) else f"{value:.3f}"


def _print_variant(label: str, variant: dict[str, PrecisionRecall]) -> None:
    print(f"  [{label}]")
    for algorithm, r in variant.items():
        counts = f"TP={r.true_positive} FP={r.false_positive} FN={r.false_negative}"
        precision = _format_ratio(r.precision)
        recall = _format_ratio(r.recall)
        print(f"    {algorithm}: precision={precision} recall={recall} ({counts})")


def _print_summary(
    days: int, elapsed_seconds: float, summary: dict[str, dict[str, PrecisionRecall]]
) -> None:
    print(f"{days}日分: 所要時間{elapsed_seconds:.1f}秒")
    _print_variant("フィルタなし", summary["unfiltered"])
    _print_variant(
        f"request_count>={MIN_REQUEST_COUNT_FOR_EVALUATION}", summary["filtered"]
    )


REASON_LABELS: dict[str, str] = {
    "ready": "移行可能",
    "insufficient_precision": "精度不足",
    "insufficient_samples": "評価不能(実異常サンプルなし)",
}


def _print_silent_mode_decisions(filtered: dict[str, PrecisionRecall]) -> None:
    threshold = DEFAULT_PROMOTION_THRESHOLD
    print(f"  [サイレント運用: 本番移行判定(閾値precision>={threshold})]")
    for algorithm, result in filtered.items():
        decision: SilentModeDecision = decide_production_readiness(algorithm, result)
        label = REASON_LABELS[decision.reason]
        precision = _format_ratio(decision.precision)
        print(f"    {algorithm}: {label}(precision={precision})")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="学習データ量ごとにSTL/IsolationForestの精度を評価する"
    )
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--show-progress", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    filtered_results: dict[int, dict[str, PrecisionRecall]] = {}

    for days in DAY_COUNTS:
        print(f"=== {days}日分のデータで評価中 ===", flush=True)
        start_time = time.time()
        merged = evaluate_at_scale(
            days, seed=args.seed, show_progress=args.show_progress
        )
        summary = summarize(merged)
        _print_summary(days, time.time() - start_time, summary)
        _print_silent_mode_decisions(summary["filtered"])
        filtered_results[days] = summary["filtered"]

    plot_precision_by_days(filtered_results, args.output)
    condition = f"request_count>={MIN_REQUEST_COUNT_FOR_EVALUATION}"
    print(f"グラフ({condition}) を {args.output} に出力しました")


if __name__ == "__main__":
    main()
