import argparse
from datetime import datetime, timezone

from log_anomaly_detection_poc.log_generator import DEFAULT_SEED, generate_logs

DEFAULT_OUTPUT_PATH = "data/logs.csv"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ダミーアクセスログを生成する")
    parser.add_argument("--days", type=int, required=True, choices=[7, 14, 30])
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    start = datetime.now(tz=timezone.utc).replace(microsecond=0)
    df = generate_logs(start=start, days=args.days, seed=args.seed)
    df.to_csv(args.output, index=False)
    print(f"{len(df)}件のログを {args.output} に出力しました")


if __name__ == "__main__":
    main()
