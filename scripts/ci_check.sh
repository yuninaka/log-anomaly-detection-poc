#!/usr/bin/env bash
# ローカル・GitHub Actions共通の品質ゲート。
#
# 「ローカルでは通ったのにCIで落ちる」という食い違いを防ぐため、チェック内容は
# この1ファイルに集約している。ローカルでPRを出す前にこのスクリプトを実行し、
# 緑になってからpushする運用とする。CI側のワークフローファイルはこのスクリプトを
# 呼び出すだけの薄いラッパーにし、個別のチェックコマンドを直接書かないこと。
#
# 前提: ローカルで gitleaks コマンドが実行できること (apt install gitleaks 等)。
# CI側は GitHub Actions ワークフロー内で apt install 済みの前提で実行する。
set -euo pipefail

echo "==> pytest (coverage付き)"
uv run pytest tests/ -v --cov=src --cov-report=term-missing

echo "==> ruff"
uv run ruff check .

echo "==> mypy"
uv run mypy src

echo "==> vulture (report only, does not fail the build)"
uv run vulture src/ --min-confidence 80 || true

echo "==> gitleaks (シークレット検知)"
gitleaks detect --source . --no-banner --redact

echo "==> pip-audit (依存脆弱性チェック)"
uv run pip-audit

echo "全チェック通過"
