import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from log_anomaly_detection_poc.cli import _positive_int, main
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
    output_a = tmp_path / "a.csv"
    output_b = tmp_path / "b.csv"

    main(["--days", "7", "--output", str(output_a), "--seed", "1"])
    main(["--days", "7", "--output", str(output_b), "--seed", "1"])

    assert output_a.read_text() == output_b.read_text()


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
