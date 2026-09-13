import argparse
import subprocess
import sys
import time
from datetime import timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from log_anomaly_detection_poc.cli import _parse_start, _positive_int, main
from log_anomaly_detection_poc.log_generator import (
    GROUND_TRUTH_COLUMNS,
    OBSERVED_COLUMNS,
)


def test_main_writes_observed_and_ground_truth_csv(tmp_path: Path) -> None:
    output = tmp_path / "logs.csv"

    main(["--days", "7", "--output", str(output), "--seed", "1"])

    observed = pd.read_csv(output)
    ground_truth = pd.read_csv(tmp_path / "logs_ground_truth.csv")
    assert list(observed.columns) == OBSERVED_COLUMNS
    assert list(ground_truth.columns) == GROUND_TRUTH_COLUMNS
    assert len(observed) > 0


def test_main_is_reproducible_with_same_seed(tmp_path: Path) -> None:
    # generate_logs自体の再現性はtest_log_generator.pyで検証済みのため、ここでは
    # CLIのファイル書き出し経路が再現性を壊していないことだけを確認すればよい。
    # --startを明示指定することで、実行時刻(datetime.now())への依存を排除する
    # (過去にCIで実際に発生した障害: --start省略時のデフォルトはdatetime.now()の
    # ため、2回のmain()呼び出しが実時刻の秒境界をまたぐと全タイムスタンプが1秒
    # ずれ、この単純比較が失敗していた)。
    output_a = tmp_path / "a.csv"
    output_b = tmp_path / "b.csv"
    start = "2026-01-05T00:00:00+00:00"

    main(["--days", "1", "--output", str(output_a), "--seed", "1", "--start", start])
    main(["--days", "1", "--output", str(output_b), "--seed", "1", "--start", start])

    assert output_a.read_text() == output_b.read_text()


def test_main_is_reproducible_across_a_real_second_boundary(tmp_path: Path) -> None:
    # リグレッション再発防止テスト: 2026-09-13のCIで実際に発生した障害の再現。
    # --startを明示指定していれば、2回のmain()呼び出しの間に実時刻の秒境界を
    # またいでも出力は完全一致するはずである。
    output_a = tmp_path / "a.csv"
    output_b = tmp_path / "b.csv"
    start = "2026-01-05T00:00:00+00:00"

    main(["--days", "1", "--output", str(output_a), "--seed", "1", "--start", start])
    time.sleep(1.2)  # 意図的に実時刻の秒境界をまたぐ
    main(["--days", "1", "--output", str(output_b), "--seed", "1", "--start", start])

    assert output_a.read_text() == output_b.read_text()


def test_main_without_start_uses_current_time(tmp_path: Path) -> None:
    # --start省略時はdatetime.now()由来のstartを使う(本番実行時のデフォルト挙動)。
    output = tmp_path / "logs.csv"

    main(["--days", "1", "--output", str(output), "--seed", "1"])

    observed = pd.read_csv(output, parse_dates=["timestamp"])
    assert len(observed) > 0


def test_parse_start_accepts_tz_aware_iso_string() -> None:
    parsed = _parse_start("2026-01-05T00:00:00+00:00")

    assert parsed.utcoffset() == timedelta(0)


def test_parse_start_treats_naive_string_as_utc() -> None:
    parsed = _parse_start("2026-01-05T00:00:00")

    assert parsed.tzinfo == timezone.utc


def test_parse_start_rejects_invalid_format() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_start("not-a-date")


def test_main_accepts_arbitrary_positive_day_count(tmp_path: Path) -> None:
    output = tmp_path / "logs.csv"

    main(["--days", "20", "--output", str(output), "--seed", "1"])

    assert output.exists()


def test_main_rejects_non_positive_days(tmp_path: Path) -> None:
    output = tmp_path / "logs.csv"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "log_anomaly_detection_poc",
            "--days",
            "0",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert not output.exists()


def test_ground_truth_output_can_be_overridden(tmp_path: Path) -> None:
    output = tmp_path / "logs.csv"
    ground_truth_output = tmp_path / "custom_ground_truth.csv"

    main(
        [
            "--days",
            "7",
            "--output",
            str(output),
            "--ground-truth-output",
            str(ground_truth_output),
            "--seed",
            "1",
        ]
    )

    assert ground_truth_output.exists()


@pytest.mark.parametrize("value", ["0", "-1"])
def test_positive_int_rejects_non_positive_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_int(value)
