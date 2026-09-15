# サイレント運用環境の構築手順書

Issue: #20

## 方針

`docs/setup-guide-for-silent-mode.md`を新規作成する。GitHubでリポジトリを
共有された後、実装内容(型分離・サイレント運用の設計)は説明済みだが実際に
手元で構築した経験はまだないエンド社員が、サイレント運用モード(Step5相当)を
自分のマシンで動かせる状態にするまでの手順を書く。対象読者はPython開発経験は
あるが、このリポジトリの内部構造(uv・mypy strict・CIガードレール等)には
初めて触れる人。

## 検証方針

Dockerがこの環境では利用できず、uv・gitleaksは既にこのマシンにインストール
済みのため、以下の方針で検証する(ユーザー確認済み):

- クリーンな新規ディレクトリにリポジトリをcloneし、以降の手順(uv sync・
  ci_check.sh・ダミーログ生成・evaluate_cli)は実際に実行してターミナル出力を
  記録する
- uv・gitleaksの「未インストール状態からのインストール手順」自体は実行検証
  せず、公式ドキュメント・READMEに準拠したコマンドを記載する(未検証である旨を
  明記する)
- 出力に含まれる環境依存の絶対パス(この検証で使った一時ディレクトリのパス等)は
  `~/projects/log-anomaly-detection-poc`のような汎用的な表記に置き換える

## 検証結果

- クリーンなclone → `uv sync`(0.4秒、ローカルにuvのグローバルキャッシュが
  ある場合の所要時間。キャッシュがない初回は数十秒〜数分かかりうる) → 成功
- `./scripts/ci_check.sh` → gitleaks・ruff・mypy・pytest(109件)・vulture・
  pip-auditすべて通過(85秒程度)
- ダミーログ生成コマンド(`uv run python -m log_anomaly_detection_poc --days 20
  --output data/logs.csv --seed 42`)を**README記載のコマンドをそのまま**
  実行したところ、`data/`ディレクトリが存在せずエラーになった
  (`OSError: Cannot save file into a non-existent directory: 'data'`)。
  `data/`は`.gitignore`対象でリポジトリに空ディレクトリとして含まれないため、
  cloneした直後には存在しない。`mkdir -p data`を事前に実行する必要があり、
  これは実際につまずいた点としてガイドに明記する
- `evaluate_cli.py --show-progress`を実行し、7日/14日/30日分の判定結果を
  取得(所要時間合計約3分24秒)。結果はREADMEに記載済みの実測値
  (7日: STL precision 0.133・IsolationForest precision 0.080、14日:
  両方ともprecision 0.000でrecallはN/A、30日: STL precision 0.103・
  IsolationForest precision 0.060)と一致し、全パターンで
  `reason="insufficient_precision"`(精度不足)と判定された
- gitleaksの固定バージョンインストール手順(CI workflowと同じ、チェックサム
  検証込み)も、システムのgitleaksを上書きしない形で別途検証し、成功を確認した

## 機微情報チェック

- ダミーログ生成・evaluate_cliの出力に含まれるのは合成データ(エンドポイント名
  `/api/login`等、ステータスコード、レイテンシ)のみで、実データ・実在の情報は
  含まれない
- 検証時の絶対パス(検証用一時ディレクトリのパス)は全て`~/projects/...`形式の
  汎用パスに置き換えて記載した
