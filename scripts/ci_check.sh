#!/usr/bin/env bash
# ローカル・GitHub Actions共通の品質ゲート。
#
# 「ローカルでは通ったのにCIで落ちる」という食い違いを防ぐため、チェック内容は
# この1ファイルに集約している。ローカルでPRを出す前にこのスクリプトを実行し、
# 緑になってからpushする運用とする。CI側のワークフローファイルはこのスクリプトを
# 呼び出すだけの薄いラッパーにし、個別のチェックコマンドを直接書かないこと。
#
# 前提: ローカルで gitleaks コマンド(バージョンは.pre-commit-config.yaml /
# .github/workflows/ci.ymlのGITLEAKS_VERSIONと同一に揃えること)が実行できること。
#
# 実行順は「速い/致命的なチェックを先に、遅いチェックを後に」で並べている。
# pip-auditはPyPIへのネットワークアクセスを伴うため最後に置く。
set -euo pipefail

echo "==> gitleaks (シークレット検知・リポジトリ全体/全履歴を監査)"
# pre-commit側はステージ済み差分のみの高速チェックであるのに対し、
# こちらはPR単位でリポジトリ全体・全履歴を監査する役割分担にしている。
gitleaks detect --source . --no-banner --redact

echo "==> ruff"
uv run ruff check .

echo "==> mypy"
uv run mypy src tests

echo "==> pytest (coverage付き、閾値50%未満で失敗)"
uv run pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=50

echo "==> vulture (report only, does not fail the build)"
uv run vulture src/ --min-confidence 80 || true

echo "==> pip-audit (依存脆弱性チェック)"
uv run pip-audit

echo "全チェック通過"
