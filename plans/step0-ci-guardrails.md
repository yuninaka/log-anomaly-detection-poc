# Step0: CI雛形構築

Issue: #1

## 方針

- `uv` でPythonプロジェクトを初期化（`src/log_anomaly_detection_poc/` パッケージレイアウト）
- `python-ci-guardrails` スキルのテンプレート（ruff strict + mypy strict + vulture report-only +
  単一 `scripts/ci_check.sh`）をベースに、Step0要件にある gitleaks（シークレット検知）・
  pip-audit（依存脆弱性チェック）を同じ `ci_check.sh` に追加し、pytestはカバレッジ出力付きにする
- CIワークフローは `pull_request` トリガーで、環境セットアップ（`uv sync` / gitleaksのapt install）
  のみを行い、実際のチェックはすべて `ci_check.sh` に委譲する（ローカル/CIの内容を1箇所に集約）
- pre-commitで ruff・mypy・gitleaks（ステージ差分）をコミット時に実行

## 決定事項

- ゼロテスト禁止のため、`src/log_anomaly_detection_poc/__init__.py` に `__version__` を持たせ、
  それを検証する最小テストを1本追加した（Step1以降の実アプリケーションコードとは別物）
- gitleaks/pip-audit は report-only ではなく通常ゲート（失敗時にビルドを止める）として扱った
  （vultureのみ既存テンプレート通りreport-only）
- gitleaksはローカル・CI双方で apt (`gitleaks 8.16.0-1build2` 相当) を使用し、インストール手順を
  ローカル/CIで揃えた

## 結果

- `./scripts/ci_check.sh` ローカル実行: 全チェック通過（pytest 1件・ruff・mypy・vulture・
  gitleaks・pip-audit）
- `uv run pre-commit run --all-files`: 通過
- GitHub Actions実行結果: PR作成後に確認する
