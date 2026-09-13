from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from log_anomaly_detection_poc.evaluate_cli import (
    DEFAULT_OUTPUT_PATH,
    MIN_REQUEST_COUNT_FOR_EVALUATION,
    _parse_args,
    plot_precision_by_days,
    summarize,
)
from log_anomaly_detection_poc.evaluation import PrecisionRecall

START = datetime(2026, 1, 5, tzinfo=timezone.utc)
HIGH_REQUEST_COUNT = MIN_REQUEST_COUNT_FOR_EVALUATION + 1
LOW_REQUEST_COUNT = MIN_REQUEST_COUNT_FOR_EVALUATION - 1


def _merged_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "window_start": START,
                "endpoint": "/api/login",
                "label": "anomaly",
                "stl_score": 5.0,
                "if_score": 1.0,
                "request_count": HIGH_REQUEST_COUNT,
            },
            {
                "window_start": START + timedelta(minutes=5),
                "endpoint": "/api/login",
                "label": "normal",
                "stl_score": 0.5,
                "if_score": 0.0,
                "request_count": HIGH_REQUEST_COUNT,
            },
            {
                "window_start": START + timedelta(minutes=10),
                "endpoint": "/api/login",
                "label": "noise",
                "stl_score": 4.0,
                "if_score": 1.0,
                "request_count": HIGH_REQUEST_COUNT,
            },
        ]
    )


def test_summarize_treats_noise_as_negative_for_both_algorithms() -> None:
    result = summarize(_merged_frame())

    for algorithm in ("STL", "IsolationForest"):
        pr = result["unfiltered"][algorithm]
        # 3件中: anomaly(検知される想定)1件、noise(検知されるが陽性ではない)1件、
        # normal 1件。true_positive=1, false_positive=1(noiseの誤検知)。
        assert pr.true_positive == 1
        assert pr.false_positive == 1


def test_summarize_returns_both_algorithms_for_each_variant() -> None:
    result = summarize(_merged_frame())

    assert set(result.keys()) == {"unfiltered", "filtered"}
    for variant in result.values():
        assert set(variant.keys()) == {"STL", "IsolationForest"}
        assert all(isinstance(v, PrecisionRecall) for v in variant.values())


def test_summarize_filters_out_low_request_count_buckets() -> None:
    merged = _merged_frame()
    merged.loc[0, "request_count"] = LOW_REQUEST_COUNT

    result = summarize(merged)

    # フィルタありでは0件目(anomalyだった行)が除外され、TPが0になる。
    assert result["filtered"]["STL"].true_positive == 0
    assert result["unfiltered"]["STL"].true_positive == 1


def test_plot_precision_by_days_writes_a_file(tmp_path: Path) -> None:
    results = {
        7: {
            "STL": PrecisionRecall(0.5, 0.5, 1, 1, 1),
            "IsolationForest": PrecisionRecall(0.6, 0.4, 1, 1, 1),
        },
        14: {
            "STL": PrecisionRecall(0.7, 0.6, 2, 1, 1),
            "IsolationForest": PrecisionRecall(0.8, 0.5, 2, 1, 1),
        },
    }
    output = tmp_path / "plot.png"

    plot_precision_by_days(results, str(output))

    assert output.exists()
    assert output.stat().st_size > 0


def test_parse_args_defaults() -> None:
    args = _parse_args([])

    assert args.output == DEFAULT_OUTPUT_PATH
    assert args.show_progress is False


CUSTOM_SEED = 5


def test_parse_args_overrides() -> None:
    args = _parse_args(
        ["--output", "custom.png", "--seed", str(CUSTOM_SEED), "--show-progress"]
    )

    assert args.output == "custom.png"
    assert args.seed == CUSTOM_SEED
    assert args.show_progress is True
