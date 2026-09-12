from pathlib import Path

import pandas as pd

from log_anomaly_detection_poc.cli import main
from log_anomaly_detection_poc.log_generator import LOG_COLUMNS


def test_main_writes_csv_with_requested_days(tmp_path: Path) -> None:
    output = tmp_path / "logs.csv"

    main(["--days", "7", "--output", str(output), "--seed", "1"])

    df = pd.read_csv(output)
    assert list(df.columns) == LOG_COLUMNS
    assert len(df) > 0


def test_main_is_reproducible_with_same_seed(tmp_path: Path) -> None:
    output_a = tmp_path / "a.csv"
    output_b = tmp_path / "b.csv"

    main(["--days", "7", "--output", str(output_a), "--seed", "1"])
    main(["--days", "7", "--output", str(output_b), "--seed", "1"])

    assert output_a.read_text() == output_b.read_text()
