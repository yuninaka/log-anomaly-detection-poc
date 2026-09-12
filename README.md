# log-anomaly-detection-poc

AIが機微データ（生ログ・実データ）に一切触れず、メタデータのみで異常の絞り込みを行う、
という設計思想を実装レベルで検証するPoC。

## セットアップ

```bash
uv sync
```

## 品質ゲートの実行

PRを出す前に、ローカルで以下を実行して緑になることを確認する。

```bash
./scripts/ci_check.sh
```

pytest（カバレッジ付き）・ruff・mypy（strict）・vulture（report only）・gitleaks・pip-audit を
まとめて実行する。GitHub Actions（`.github/workflows/ci.yml`）でも同じスクリプトを実行する。

ローカルで gitleaks を使うには別途インストールが必要（Ubuntu/Debianの場合 `sudo apt install gitleaks`）。

## pre-commitフック

```bash
uv run pre-commit install
```

コミット時に ruff・mypy・gitleaks（ステージ済みの差分）が自動実行される。

## ダミーログ生成(Step1)

```bash
uv run python -m log_anomaly_detection_poc --days 20 --output data/logs.csv --seed 42
```

- `--days` は任意の正の整数を指定できる(1週間=7・2週間=14・1ヶ月=30 に限定されない)
- `--seed` を固定すると常に同一データが生成される(デフォルト42)
- 出力は2ファイルに分離される
  - `--output` で指定したファイル: 観測ログ(`timestamp`/`endpoint`/`status_code`/`latency_ms`)。
    検知パイプラインに渡してよいのはこちらのみ
  - `<output>_ground_truth.csv`(`--ground-truth-output`で変更可): 正解ラベル
    (`label`/`anomaly_type`)。Step4の精度評価専用で、検知パイプラインには渡さない
- 異常イベント(`latency_spike`・`error_spike`)は「1週間ごとに1回ずつ」注入されるが、
  発生時刻・継続時間・対象エンドポイントは乱数で決まる。業務時間/夜間/週末でトラフィック量が
  最大6.7倍変動するため、該当行数は生成日数に対して単調に増えるとは限らない
