# log-anomaly-detection-poc プロジェクト規約

このファイルは、Claude Codeがこのリポジトリで作業する際に毎回参照する規約です。
「読まなくても壊れないコードベースにする」という考え方
（参考: https://zenn.dev/singularity/articles/stopped-reviewing-my-code）を、
このPython/uvプロジェクトに適用したもの。

## PR前の品質チェック

コードを変更したら、PRを出す前に必ず以下をローカルで実行し、緑になってから push すること。

```bash
./scripts/ci_check.sh
```

GitHub Actions（`.github/workflows/ci.yml`）でも同じスクリプトが自動的にもう一度実行される。
ローカルとCIのチェック内容を1つのスクリプトに集約しているのは、「ローカルでは通ったのにCIで
落ちる」という食い違いを防ぐため。チェック内容を変更する場合は、必ず `scripts/ci_check.sh` 側を
直し、ワークフローファイル側には個別のチェックコマンドを追記しないこと。

`ci_check.sh` には pytest（カバレッジ付き）・ruff・mypy・vulture（report only）に加え、
gitleaks（シークレット検知）・pip-audit（依存脆弱性チェック）も含まれる。ローカルで
gitleaks を実行するには `gitleaks` コマンドが必要（`sudo apt install gitleaks`）。

## テストでカバーすべきケース

新しいロジックを書いたら、以下の観点で「カバーできているか」を確認する。すべてのケースが
毎回必要なわけではないが、抜けている場合は意図的に省略した理由を説明できるようにしておく。

- **正常系**: 典型的な入力で期待通り動くこと
- **エッジケース**: 空リスト・空文字列・要素数1・最大要素数付近
- **コーナーケース**: 複数の条件が同時に成立する組み合わせ
- **境界値**: `>=` と `>` を間違えていないか、ちょうど閾値と同じ値
- **空・null/undefined相当**: `None`・空リスト・空dict
- **不正入力**: 型は合っているが値がおかしい入力（例: 存在しないキー、負の数）
- **エラー**: 依存先（外部API/DB等）が例外を投げるケース
- **否定**: 「〜が含まれない」「〜ではない」ことを確認するテスト
- **リグレッション**: 過去に実際に発生したバグの再発防止

### 過去に実際に見つかったバグ（リグレッションケースの具体例）

<!-- 実際にバグが見つかるたびに、ここに1行ずつ追記していく。最初は空でよい。
     「今のデータでは起きないから」と後回しにせず、テストを先に書いて現象を
     再現してから修正した記録を残すことで、同種の考慮漏れへの気付きが積み上がる。 -->

| バグ | 該当ケース | 発見箇所 |
|---|---|---|
| (例) 空入力でXがY件返るはずがZ件返っていた | 空・境界値 | PR #N レビュー |

## IOとpureロジックの分離

IOを伴うロジック（外部API/DBへの呼び出し）と、pureなロジック（変換・整形・計算等）を
分離し、pure関数を優先的に単体テストする。IOを伴う配線部分は単体テスト化が難しい場合、
実リソースに対する実行で動作確認し、結果を`plans/`等の記録に残す。

## lint/型エラーの黙らせ方

`# noqa` や `# type: ignore` で安易に黙らせない。使う場合は必ず対象行（またはその直前）に
理由をコメントで明記すること。理由は以下のいずれかであるべきで、「面倒だから」は理由にならない。

- 外部ライブラリの実装詳細（静的解析からは見えない挙動）
- 診断・検証用スクリプトなど、複雑さが本質的なもの
- 型システムの表現力の限界

理由が古くなった・当てはまらなくなった場合は、`# noqa` / `# type: ignore` のエントリ自体を
削除すること（「一応残しておく」は禁止）。

## 機微情報の扱い

Step7以降でAzure OpenAIのAPIキーを扱う想定のため、この節は有効のまま維持する。

APIキー・エンドポイント等の機微情報を、標準出力・ログ・エラーメッセージに含めない。

- ユーザー向けの画面・メッセージには固定文言のみを表示し、例外の詳細（外部SDKの
  エラーメッセージ等）は`logging`モジュールでサーバー側ログにのみ残す
- `.env`の値をデバッグ目的で出力する場合も、機微な値（APIキー等）は対象から除外すること
- Step6/7のUIでは、メタデータ層と生データ層の境界を型レベルで強制する設計（Step3参照）を
  絶対に崩さないこと。生データ層を渡す関数・ログ経路は必ず別のものとして分離する

## Step1からの引き継ぎ制約(検知アルゴリズムへの入力)

Step1で生成したデータは `log_generator.LogDataset(observed, ground_truth)` の型で
構造的に分離されている(`observed`はlabel/anomaly_type列を持たない)。

- Step2以降、STL分解・IsolationForestなど検知アルゴリズムへの入力は必ず`observed`型
  (またはそこから導出したメタデータ型)のみとする
- `ground_truth`(正解ラベル)は精度評価スクリプト(Step4)内でのみ、検知結果と突き合わせる
  目的で使用する。結合したDataFrameをそのまま検知関数に渡さないこと
- 検知関数の型シグネチャは`observed`由来の型のみを受け付ける設計にし、
  `ground_truth`由来の型を渡すとmypyでエラーになるようにする(Step3の型分離と同じ考え方)

## Step2からの引き継ぎ制約(5分集計のゼロ埋めグリッド)

Step2の`aggregate_observed_logs`は、全エンドポイント×全期間の5分バケットを0埋めで
網羅する完全なグリッドを生成する(欠損バケットを行ごと落とさない)。STL分解が前提とする
「等間隔の時系列」を壊さないため、また「トラフィックがない」こと自体を正常な情報として
区別可能にするための設計。

- `request_count=0`のバケットは`error_rate=0.0`(エラーが発生していないため)
- `request_count=0`のバケットは`avg_latency_ms=NaN`(リクエストがなくレイテンシ自体が
  未定義のため0ではない)。Step4でSTL分解に渡す前に補間(interpolate等)が必要
- `ground_truth`側は`preprocessing.aggregate_ground_truth`で、`aggregate_observed_logs`と
  同じグリッド(全エンドポイント×全期間の5分バケット)・同じバケット境界(`floor_to_bucket`)で
  集計している。ラベルは`LABEL_PRIORITY`(anomaly > noise > normal)順に1つに決め、
  `request_count=0`のバケット(observed側にレコードがない=ground_truth側にも該当行がない)は
  `reindex`後に明示的に`label=normal`を補完する。observed側とground_truth側は同じグリッドで
  生成しているため`window_start`・`endpoint`をキーにそのまま結合できる

## Step4開始時の前提制約

### 前提制約1: データ分離(Step1からの引き継ぎ)

Step1で生成したデータは`LogDataset(observed, ground_truth)`の型で分離されている。
検知アルゴリズム(STL分解・IsolationForest)への入力は必ず`observed`型のみとし、
`ground_truth`(正解ラベル)は精度評価スクリプト内でのみ、検知結果と突き合わせる目的で
使用すること。結合したDataFrameをそのまま検知関数に渡すことのないよう、
検知関数の型シグネチャは`observed`型(またはそこから導出したメタデータ型)のみを
受け付ける設計にすること。

### 前提制約2: 既知の未解決事項(Step2からの引き継ぎ、Step4で追加検証済み)

Step1のログ生成テストで、pytest実行時のみ(素のPythonスクリプトループでは
再現しない)、特定のデータ量で数分間ハングする現象が過去に発生した
(coverageトレースオーバーヘッドという仮説は検証の結果誤りと判明し、
根本原因は未特定のまま)。現状はテストの`--days`を1に縮小して回避している。

Step4でSTL/IsolationForest/matplotlib等の依存関係を追加した後、この現象が
再発した。追加検証の結果:

- `cli.py`(該当テストが経由する唯一の自作モジュール)は`detection.py`を
  直接・間接問わず一切importしていないことを`python -X importtime`で確認した
  (合計importtime約300ms、pandasのみ)。Step4の依存関係追加とこの現象は無関係
- 該当テスト単体10回・フルスイート(coverageなし)3回・フルスイート
  (coverageあり、`ci_check.sh`と同条件)4回、計17回連続実行して1度も再現しなかった
  (体感発生率25〜33%という以前の見積りと矛盾しない結果であり、発生率が
  上がったという証拠ではない)

つまりこの事象は**Step2時点から変わらず未解決のまま**であり、pytest経由でのみ・
データ量に応じて発生する何かという以上の特定はできていない。今後大きいデータ量を
扱う処理(データ生成・前処理・モデル学習等)を追加・実行する際は、都度フォアグラウンドで
実行時間を計測し、異常な遅延がないか確認しながら進めること。数分以上遅延する場合は、
勝手にリトライやタイムアウト回避を繰り返さず、一度作業を止めて遅延箇所を報告すること。

**次に発生した際に優先すべき調査方針**: 発生率が低く狙って再現させるのが非効率なため、
「発生した瞬間にその場でスタックトレースを取得する」ことを最優先にする。
`ci_check.sh`やpytestが30〜60秒以上停止したら、直ちに`ps aux`でPIDを特定し、
`sudo env "PATH=$PATH" py-spy dump --pid <pid>`(このサンドボックスではptraceが
制限されているため`sudo`が必要)、またはfaulthandlerベースのウォッチドッグで
その場のスタックトレースを取得する。単純な追加検証(発生率の再計測や新しい仮説の
当てずっぽうの検証)を繰り返すのではなく、実際にハングした瞬間の証拠を掴むことが
次の突破口になる。

## Step4からの引き継ぎ制約

- `evaluate_cli.MIN_REQUEST_COUNT_FOR_EVALUATION`(現在5)は`evaluate_cli.py`内に
  のみ存在する評価専用の定数であり、`detection.py`の検知関数(`compute_stl_anomaly_score`・
  `compute_isolation_forest_anomaly_score`)には一切組み込まれていない。実運用の検知
  パイプラインには影響せず、精度評価の母集団(低トラフィックで統計的に不安定なバケットを
  除外)を絞るためだけの措置である。Step5のサイレント運用モードを設計する際、この
  フィルタが「評価専用」であって「検知ロジック自体の一部」ではないことを踏まえること
- `detection.py`の`compute_stl_anomaly_score`・`compute_isolation_forest_anomaly_score`は
  ともに`Sequence[MetadataRecord]`のみを受け付ける型シグネチャになっており、
  `RawDataRecord`を渡すとmypyエラーになることが`tests/type_fixtures/`
  (`valid_call.py`・`invalid_call.py`)・`tests/test_type_separation.py`で検証済み。
  Step3で確立した型分離が、実際の検知アルゴリズムを実装したStep4でも維持されている。
  Step5以降で新しい検知・評価関数を追加する場合も、この型分離を必ず維持し、
  シグネチャを変更する際はfixture・検証テストを同時に更新すること

## Step5からの引き継ぎ制約

- `silent_mode.py`は永続化(CSV/JSON出力、DB保存等)を一切行わない。Step6の人間確認UIが
  実際にどんな形式(単なるオンメモリのリスト、SQLite等)を必要とするかはStep6の設計時に
  決める。まだ使われていない機能のためにスキーマを先回りで拡張しないという、Step1(顧客ID
  ダミーの合成タイミング)・Step3(型分離)以来の一貫した判断
- `SilentModeDecision.reason`は`"ready"` / `"insufficient_precision"` / `"insufficient_samples"`
  の3値で、「精度不足で移行不可」と「評価不能で移行不可」を区別する。判定は`result.precision`
  (`PrecisionRecall.precision`)がNaNかどうかのみで決まる。precisionがNaNになるのは
  `TP+FP=0`(サイレントモード期間中にアルゴリズムが陽性判定を一件も出さなかった)場合であり、
  `TP+FN=0`(実異常サンプルが0件、recallがNaNになる条件)とは別の条件である点に注意
  (14日分の実データはrecallがN/Aだがprecisionは0.000で算出可能だったため
  `insufficient_precision`になった。recallの評価可否は`decide_production_readiness`の
  判定に一切関与しない)。どちらのreasonも`ready_for_production=False`になるが原因が
  異なるため、Step6のUIでこの判定結果を表示する際は`reason`をそのまま見せ、
  `ready_for_production`のbool値だけに丸めないこと
- `decide_production_readiness`には`evaluate_cli.py`の`_print_silent_mode_decisions`から
  `summary["filtered"]`(`MIN_REQUEST_COUNT_FOR_EVALUATION>=5`適用後)の`PrecisionRecall`が
  渡される。フィルタ前の値を使うとフィルタ前後の意図(低トラフィックバケットの分散不安定性
  除去)が本番移行判定に混入するため、フィルタ後のみを使う設計
- 閾値(`DEFAULT_PROMOTION_THRESHOLD=0.5`)に対して、Step4の実測データ(7日/14日/30日いずれも
  STL・IsolationForestともprecision 13%以下)では全て`reason="insufficient_precision"`
  (移行不可)と判定される。これはバグではなく実測結果通りの挙動であり、閾値を恣意的に
  下げて`ready_for_production=True`にするような調整は行っていない。Step6以降でも
  この判定ロジックを甘くする方向の変更をしないこと

## Step6からの引き継ぎ制約

- `ui_logic.py`(pure/オーケストレーション関数)と`ui.py`(Streamlitレンダリングのみの
  薄い層)を分離している。IOとpureロジックの分離方針(このファイル冒頭)に従い、
  新しいUIロジックを追加する際もこの分離を維持し、pureな部分はpytestで単体テストする
  こと。`ui.py`自体はレンダリング層のためpytestでの自動テスト対象外とし、
  `streamlit run`での実行(または`streamlit.testing.v1.AppTest`でのヘッドレス検証)で
  動作確認すること
- `ui_logic.run_detection_pipeline`は`ground_truth`を一切使わない本番相当のパイプライン
  であり、Step4/5の評価パイプライン(`evaluate_cli.evaluate_at_scale`)とは別物。
  本番運用に正解ラベルは存在しないという想定を反映しているため、UIに評価用の関数を
  混用しないこと
- 生データ層への変換は`data_layers.raw_data_records_for_window`(1バケットのみ変換)を
  使い、`to_raw_data_records`(観測ログ全体を無条件変換)はUIから直接呼ばないこと。
  「人間が明示的に確認を選択した場合にのみ生データ層に触れる」という設計をコードの
  フローとして保証するため
- `SilentModeRecord`は`scenario_id`のみを持ちmodule_name/window_startを持たないため、
  UI側で`ui_logic.metadata_by_scenario_id`を使ってMetadataRecordを引く。同じ
  `scenario_id`がSTL・IsolationForest両方でflaggedになりうるため、Streamlitの
  ウィジェットkeyには`scenario_id`だけでなく`algorithm`も含めて一意にすること
  (実際に`AppTest`での検証中に`StreamlitDuplicateElementKey`で発覚した実バグ)。
  ただし開示状態(`revealed_scenario_id`)自体はscenario_id単位で管理しているため、
  同じバケットが両アルゴリズムでflaggedの場合は両方の行で開示される(データ内容は
  同一のため誤りではないが、行ごとに独立した開示状態にはしていない)
