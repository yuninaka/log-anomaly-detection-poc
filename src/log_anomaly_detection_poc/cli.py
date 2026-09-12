import argparse
from datetime import datetime, timezone
from pathlib import Path

from log_anomaly_detection_poc.log_generator import DEFAULT_SEED, generate_logs

DEFAULT_OUTPUT_PATH = "data/logs.csv"
GROUND_TRUTH_SUFFIX = "_ground_truth"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"{value} は正の整数である必要があります")
    return parsed


def _derive_ground_truth_path(output_path: str) -> str:
    path = Path(output_path)
    return str(path.with_name(f"{path.stem}{GROUND_TRUTH_SUFFIX}{path.suffix}"))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ダミーアクセスログを生成する")
    parser.add_argument(
        "--days", type=_positive_int, required=True, help="生成する日数(正の整数)"
    )
    parser.add_argument(
        "--output", type=str, default=DEFAULT_OUTPUT_PATH, help="観測ログの出力先"
    )
    parser.add_argument(
        "--ground-truth-output",
        type=str,
        default=None,
        help="正解ラベルの出力先(省略時は出力先ファイル名に_ground_truthを付与)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="乱数シード(同じ値なら常に同一データを生成する)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    ground_truth_output = args.ground_truth_output or _derive_ground_truth_path(
        args.output
    )

    start = datetime.now(tz=timezone.utc).replace(microsecond=0)
    dataset = generate_logs(start=start, days=args.days, seed=args.seed)
    dataset.observed.to_csv(args.output, index=False)
    dataset.ground_truth.to_csv(ground_truth_output, index=False)

    print(f"観測ログ {len(dataset.observed)}件を {args.output} に出力しました")
    print(f"正解ラベル {len(dataset.ground_truth)}件を {ground_truth_output} に出力")


if __name__ == "__main__":
    main()
