# サイレント運用環境 構築手順書

この手順書は、`log-anomaly-detection-poc`リポジトリを共有された後、自分のマシンで
サイレント運用モード(Step5相当)を動かせる状態にするまでの環境構築手順をまとめたもの。

**対象読者**: Pythonの開発経験はあるが、このリポジトリの内部構造(uv・mypy strict・
CIガードレール等)には初めて触れる人。リポジトリの設計思想(型分離・段階的な導入)は
既に説明を受けている前提。

**検証方法**: 各ステップは、クリーンな新規ディレクトリに実際にリポジトリをcloneして
実行し、その実行結果をそのまま貼り付けている(スクリーンショットではなく、コピー&
ペースト可能なテキストのコードブロック)。出力に含まれる絶対パスは
`~/projects/log-anomaly-detection-poc`という汎用的な表記に置き換えている。
uv・gitleaksの「未インストール状態からのインストール」手順自体は、検証環境に既に
両方インストール済みだったため実行検証していない(該当箇所に明記する)。

## 1. リポジトリのclone

```bash
git clone https://github.com/yuninaka/log-anomaly-detection-poc.git
cd log-anomaly-detection-poc
```

つまずきやすいポイント: 特になし。GitHubのアクセス権限(リポジトリがprivateの場合)
だけ事前に確認しておくこと。

## 2. uvのインストール確認

```bash
uv --version
```

既にインストール済みなら、バージョン番号が表示される(検証環境では`uv 0.12.10`)。
**未インストールの場合**(このリポジトリでは未検証、[uv公式ドキュメント](https://docs.astral.sh/uv/getting-started/installation/)に準拠):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

インストール後はシェルを再起動するか、案内されるPATHの設定を反映させること。

つまずきやすいポイント: `curl`が使えない環境(社内プロキシ制限等)では、上記スクリプトが
失敗する。その場合はuv公式のインストールページに記載された別の方法(pipインストール等)を
確認すること。

## 3. `uv sync` での依存関係インストール

```bash
uv sync
```

実行結果(検証環境、ローカルにuvのキャッシュがある状態での実行):

```
Using CPython 3.12.14
Creating virtual environment at: .venv
Resolved 108 packages in 2ms
   Building log-anomaly-detection-poc @ file:///home/you/projects/log-anomaly-detection-poc
      Built log-anomaly-detection-poc @ file:///home/you/projects/log-anomaly-detection-poc
Prepared 1 package in 10ms
Installed 105 packages in 227ms
 + altair==6.2.2
 + annotated-types==0.8.0
 ...(105パッケージ、streamlit・openai・scikit-learn・statsmodels等を含む)
 + log-anomaly-detection-poc==0.1.0 (from file:///home/you/projects/log-anomaly-detection-poc)
 ...
```

つまずきやすいポイント: 上記は既存のuvキャッシュがある状態での実行時間(0.4秒)であり、
**初めてこのマシンでuvを使う場合はパッケージのダウンロードが発生し、数十秒〜数分かかる**。
遅いこと自体は異常ではない。`.python-version`(このリポジトリでは`3.12`)に合うPythonが
自動的にインストールされる。

## 4. gitleaksのインストール(pre-commitフック・ローカルCIチェック用)

`ci_check.sh`とpre-commitフックはgitleaksを直接呼び出すため、別途インストールが必要
(GitHub Actions上のCIは別途チェックサム検証込みで自動インストールするため、CI実行自体には
不要)。

```bash
gitleaks version
```

既にインストール済みなら、バージョン番号が表示される(検証環境では`8.30.1`)。
**未インストールの場合**、2つの方法がある。

Ubuntu/Debian(README記載の方法、このリポジトリでは未検証):

```bash
sudo apt install gitleaks
```

CIと完全に同じバージョン(`8.30.1`)をチェックサム検証つきで入れたい場合
(`.github/workflows/ci.yml`と同じ手順、以下は実際に検証済み):

```bash
GITLEAKS_VERSION="8.30.1"
asset="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
curl -sSL -o "$asset" "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${asset}"
curl -sSL -o checksums.txt "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_checksums.txt"
grep " ${asset}\$" checksums.txt | sha256sum -c -
tar -xzf "$asset" gitleaks
sudo mv gitleaks /usr/local/bin/gitleaks
```

実行結果(チェックサム検証部分、実際の検証ログ):

```
gitleaks_8.30.1_linux_x64.tar.gz: OK
```

つまずきやすいポイント: `apt`が使えないディストリビューション(macOS等)では、上記の
チェックサム検証つきインストール方法を使うか(`linux_x64`の部分をOS/アーキテクチャに
合わせて変更する必要がある)、[gitleaks公式のリリースページ](https://github.com/gitleaks/gitleaks/releases)
から該当OSのバイナリを取得すること。

pre-commitフック自体のインストール(コミット時にruff・mypy・gitleaksが自動実行される):

```bash
uv run pre-commit install
```

## 5. `./scripts/ci_check.sh` の実行

```bash
./scripts/ci_check.sh
```

実行結果(検証環境、抜粋。gitleaks・ruff・mypyのサマリ部分と、pytestの末尾):

```
==> gitleaks (シークレット検知・リポジトリ全体/全履歴を監査)
11:23PM INF 27 commits scanned.
11:23PM INF scanned ~800165 bytes (800.16 KB) in 237ms
11:23PM INF no leaks found
==> ruff
All checks passed!
==> mypy
Success: no issues found in 26 source files
==> pytest (coverage付き、閾値50%未満で失敗)
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0 -- ~/projects/log-anomaly-detection-poc/.venv/bin/python
cachedir: .pytest_cache
rootdir: ~/projects/log-anomaly-detection-poc
configfile: pyproject.toml
plugins: cov-7.1.0, anyio-4.15.1
collecting ... collected 109 items

tests/test_cli.py::test_main_writes_observed_and_ground_truth_csv PASSED [  0%]
...(109件全てPASSED)

================================ tests coverage ================================
TOTAL                                              608     97    84%
Required test coverage of 50% reached. Total coverage: 84.05%
============================= 109 passed in 25.48s =============================
==> vulture (report only, does not fail the build)
==> pip-audit (依存脆弱性チェック)
No known vulnerabilities found
全チェック通過
```

`全チェック通過`と表示されれば成功。ここまでの所要時間は検証環境で25秒程度(pytestが
大半を占める)。

### トラブルシューティング(通りやすいエラーとその原因)

| エラー | 想定される原因 | 対処 |
|---|---|---|
| `gitleaks: command not found` | 手順4のインストールが未実施 | 手順4を実施し、`gitleaks version`が通ることを確認してから再実行 |
| `mypy: command not found` / `pytest: command not found` | `uv sync`が未実施、または`uv run`を付けずに直接コマンドを実行している | `ci_check.sh`は内部で`uv run`を使うため、`uv sync`が完了していればこのエラーは通常出ない。直接デバッグする場合は各コマンドの前に`uv run`を付ける |
| pytestが数十秒〜数分単位で停止する | このリポジトリで低頻度・原因未特定のまま観測されている既知の事象(`CLAUDE.md`の「前提制約2」参照) | 数分待っても終わらない場合はCtrl+Cで中断し、再実行する。再実行で解消することが多い |
| ruffやmypyでエラーが出る | cloneしたコードそのものに問題がある可能性は低いが、ローカルの変更を加えた場合はエラー内容に従って修正 | エラーメッセージのファイル・行番号を確認して修正 |

## 6. ダミーログ生成コマンドの実行例

```bash
mkdir -p data
uv run python -m log_anomaly_detection_poc --days 20 --output data/logs.csv --seed 42
```

実行結果:

```
観測ログ 42453件を data/logs.csv に出力しました
正解ラベル 42453件を data/logs_ground_truth.csv に出力
```

つまずきやすいポイント(実際に検証中に発生した): **README記載のコマンドをそのまま
実行すると失敗する**。

```
OSError: Cannot save file into a non-existent directory: 'data'
```

`data/`ディレクトリは`.gitignore`対象でリポジトリに含まれておらず、cloneした直後には
存在しない。上記のように`mkdir -p data`を先に実行しておくこと。

## 7. `evaluate_cli.py` によるサイレント運用の判定結果出力

```bash
uv run python -m log_anomaly_detection_poc.evaluate_cli --show-progress
```

7日/14日/30日分のデータを生成し、STL分解・IsolationForestそれぞれで検知精度を測定した上で、
サイレント運用モードの「本番移行判定」を出力する。**所要時間は3分半程度**(30日分のSTL計算が
特に時間がかかる)。`--show-progress`を付けるとエンドポイントごとの計算進捗が表示される。

実行結果(検証環境、実際の出力をそのまま。数値は`README.md`記載の実測値と一致):

```
=== 7日分のデータで評価中 ===
[STL 1/5] /api/login を計算中...
[STL 2/5] /api/orders を計算中...
[STL 3/5] /api/search を計算中...
[STL 4/5] /api/users を計算中...
[STL 5/5] /health を計算中...
[IsolationForest 1/5] /api/login を計算中...
[IsolationForest 2/5] /api/orders を計算中...
[IsolationForest 3/5] /api/search を計算中...
[IsolationForest 4/5] /api/users を計算中...
[IsolationForest 5/5] /health を計算中...
7日分: 所要時間24.9秒
  [フィルタなし]
    STL: precision=0.043 recall=0.900 (TP=9 FP=202 FN=1)
    IsolationForest: precision=0.007 recall=0.900 (TP=9 FP=1239 FN=1)
  [request_count>=5]
    STL: precision=0.133 recall=1.000 (TP=2 FP=13 FN=0)
    IsolationForest: precision=0.080 recall=1.000 (TP=2 FP=23 FN=0)
  [サイレント運用: 本番移行判定(閾値precision>=0.5)]
    STL: 精度不足(precision=0.133)
    IsolationForest: 精度不足(precision=0.080)
=== 14日分のデータで評価中 ===
...(進捗表示は省略)
14日分: 所要時間55.1秒
  [フィルタなし]
    STL: precision=0.028 recall=0.786 (TP=11 FP=382 FN=3)
    IsolationForest: precision=0.004 recall=0.786 (TP=11 FP=2545 FN=3)
  [request_count>=5]
    STL: precision=0.000 recall=N/A (TP=0 FP=30 FN=0)
    IsolationForest: precision=0.000 recall=N/A (TP=0 FP=39 FN=0)
  [サイレント運用: 本番移行判定(閾値precision>=0.5)]
    STL: 精度不足(precision=0.000)
    IsolationForest: 精度不足(precision=0.000)
=== 30日分のデータで評価中 ===
...(進捗表示は省略)
30日分: 所要時間121.5秒
  [フィルタなし]
    STL: precision=0.042 recall=0.745 (TP=38 FP=869 FN=13)
    IsolationForest: precision=0.009 recall=0.941 (TP=48 FP=5480 FN=3)
  [request_count>=5]
    STL: precision=0.103 recall=0.857 (TP=6 FP=52 FN=1)
    IsolationForest: precision=0.060 recall=1.000 (TP=7 FP=109 FN=0)
  [サイレント運用: 本番移行判定(閾値precision>=0.5)]
    STL: 精度不足(precision=0.103)
    IsolationForest: 精度不足(precision=0.060)
グラフ(request_count>=5) を data/precision_recall.png に出力しました
```

つまずきやすいポイント: 手順6で`data/`ディレクトリを作成済みならこのコマンド自体は問題なく
動く(`evaluate_cli.py`の出力先はデフォルトで`data/precision_recall.png`のため)。

## 8. 判定結果の読み方

出力の`[サイレント運用: 本番移行判定]`行が、サイレント運用モードの判定結果。読み方は以下の3パターン。

| 表示 | `reason`の値 | 意味 |
|---|---|---|
| `移行可能(precision=X.XXX)` | `ready` | precisionが閾値(デフォルト50%)以上。本番トリアージフローへの移行を検討できる |
| `精度不足(precision=X.XXX)` | `insufficient_precision` | precisionは算出できたが閾値未満。検知ロジックの見直しが必要 |
| `評価不能(実異常サンプルなし)(precision=N/A)` | `insufficient_samples` | サイレント運用期間中に陽性判定を一件も出せず、precision自体が算出不能(0/0)。検知ロジックの問題ではなく、データを待つ必要がある |

上記の実行例では、7日・14日・30日いずれも全て`精度不足`(`insufficient_precision`)と
判定されている。これはバグではなく、実測されたprecision(8〜13%程度)をそのまま反映した
結果である。**閾値を恣意的に下げて「移行可能」に見せるような調整は行っていない**(詳細は
`README.md`の「サイレント運用モード(Step5)」節、`CLAUDE.md`の「Step5からの引き継ぎ制約」を
参照)。

`精度不足`と`評価不能`は、どちらも「移行不可」という結論は同じだが、次に取るべき対応が
異なる。`精度不足`は検知ロジック自体(閾値・特徴量選択等)を見直す必要があるサインであり、
`評価不能`は判定に使うデータ量が足りていないサインである。この2つを区別せずに「移行不可」
とだけ見てしまうと、本来は検知ロジックを直すべき場面でデータを待ってしまう、といった
判断ミスにつながる。
