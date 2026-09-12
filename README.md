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
