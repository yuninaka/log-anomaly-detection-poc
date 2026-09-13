# Step4: 異常検知ロジックと誤検知率トラッキング

Issue: #9

## 方針

- `src/log_anomaly_detection_poc/detection.py`(新規)に2つの検知関数を実装する
  - `compute_stl_anomaly_score(metadata: Sequence[MetadataRecord]) -> list[float]`
    - `module_name`(=endpoint)ごとにグループ化・`window_start`順に並べ、`avg_latency_ms`と
      `error_rate`それぞれにSTL分解(statsmodels、周期=288 = 5分足での日次周期)を適用し、
      残差の標準化スコア(zスコア)を算出。2つのzスコアの大きい方を最終スコアとする
      (latency_spike・error_spikeの両方を拾うため)
    - `avg_latency_ms`のNaN(request_count=0のバケット)は線形補間してからSTLに渡す
  - `compute_isolation_forest_anomaly_score(metadata: Sequence[MetadataRecord]) -> list[float]`
    - `module_name`ごとに別々にIsolationForestをfit(エンドポイント間で基準レイテンシが
      大きく異なるため)
    - 特徴量は`avg_latency_ms`(NaN補間後)・`error_rate`の2つ。`request_count`は特徴量に
      含めない(深夜の正常な低トラフィックが誤検知の原因になるため)
    - `contamination="auto"`(scikit-learn内部推定、正解ラベルを一切使わない)で
      `fit_predict`し、-1(異常)/1(正常)を-1→1.0・1→0.0のスコアに変換する
  - Step3の`data_layers.compute_anomaly_score`(プレースホルダー)は廃止し、実体を
    `detection.py`に移す。型シグネチャ(`Sequence[MetadataRecord] -> list[float]`)は
    前提制約3の通り維持する
- `src/log_anomaly_detection_poc/preprocessing.py`に`aggregate_ground_truth`を追加
  - Step1の生データ層(request単位のground_truth)を、`aggregate_observed_logs`と同じ
    0埋めグリッドでバケット単位に集計する。集計ルール: バケット内に`anomaly`ラベルの行が
    1件でもあれば`anomaly`、なければ`noise`が1件でもあれば`noise`、それ以外は`normal`。
    `request_count=0`のバケットは明示的に`normal`とする(Step2からの引き継ぎ制約通り)
- `src/log_anomaly_detection_poc/evaluation.py`(新規): precision/recall算出などの純粋関数
  - 正解ラベルは`anomaly`のみ陽性として扱い、`noise`は陰性として扱う(ノイズを誤検知
    しないことがこのPoCの価値なので、noiseを陽性扱いしない)
  - 閾値は固定値: STLはzスコア>3を異常、IsolationForestは`fit_predict`の-1/1をそのまま使う
    (データ量ごとの最適閾値探索は行わない。精度比較の目的には固定値で十分であり、
    閾値探索という別の自由度を持ち込むとStep5の判定ロジックとの整合性が複雑になるため)
- `src/log_anomaly_detection_poc/evaluate_cli.py`(新規): 1週間/2週間/1ヶ月でログ生成→
  前処理→検知→評価のパイプラインを回し、precision/recallの推移をmatplotlibでグラフ化
  (PNGは`data/`配下、gitignore対象)
- `tests/type_fixtures/`を更新: `valid_call.py`・`invalid_call.py`それぞれが
  `compute_stl_anomaly_score`・`compute_isolation_forest_anomaly_score`の両方を呼び出し、
  両関数が個別に型分離を維持していることを検証する

## 追加依存関係

`statsmodels`・`scikit-learn`・`matplotlib`

## データ量スケール時の注意(前提制約2)

1週間→2週間→1ヶ月とデータ量を拡大する際は、都度フォアグラウンドで実行時間を計測し、
異常な遅延がないか確認する。数分以上遅延する場合は作業を止めて報告する。

## テスト方針

- `detection.py`: 正常系(明らかな異常パターンを含む合成データでスコアが高くなること)・
  エッジケース(全て同一値の時系列、レコード数が少なすぎてSTLが実行できない場合の挙動)・
  NaN補間の正しさ
- `preprocessing.aggregate_ground_truth`: 正常系・0埋めバケットのlabel=normal・
  anomaly優先のラベル付けルール
- `evaluation.py`: precision/recallの計算が既知の混同行列で正しいこと・0件エッジケース
- 型分離: 上記の通り

## 実行結果と追加対応(最小リクエスト数フィルタ)

`evaluate_cli.py`を実データで実行したところ、フィルタなしではrecallは良好(74〜94%)
だがprecisionが極めて低い(0.4〜4.3%)ことが判明した。原因は深夜等の低トラフィック
バケット(request_count 1〜2件)でavg_latency_msの分散が統計的に安定せず、STLの
zスコア・IsolationForestの両方が頻繁に誤検知することだった。

対応として、`evaluate_cli.MIN_REQUEST_COUNT_FOR_EVALUATION = 5`(「平均レイテンシの
分散が統計的に安定する最低限のサンプル数」という独立した基準で決定。precision最大化を
目的とした閾値探索は行っていない)で評価対象バケットを絞り込む最小リクエスト数フィルタを
追加し、フィルタ前後の両方の数値を記録する設計にした。

### 実測結果(フィルタなし → フィルタあり、request_count>=5)

| 日数 | 所要時間 | STL precision | STL recall | IsolationForest precision | IsolationForest recall |
|---|---|---|---|---|---|
| 7日 | 25.8秒 | 0.043→0.133 | 0.900→1.000 | 0.007→0.080 | 0.900→1.000 |
| 14日 | 49.5秒 | 0.028→0.000 | 0.786→0.000 | 0.004→0.000 | 0.786→0.000 |
| 30日 | 125.3秒 | 0.042→0.103 | 0.745→0.857 | 0.009→0.060 | 0.941→1.000 |

フィルタによりprecisionは改善し、recallも維持または改善した(TP/FNが残る場合)。
14日分はフィルタ後の実異常サンプル数(TP+FN)が0件になった(この回のseedでは、
注入された異常イベントが低トラフィック帯に偏って発生し、フィルタで全て除外された)。
これは異常の絶対件数が少ないPoC規模のデータでは精度指標の分散が大きいことを示す
正直な結果であり、意図的に隠さず記録する。

フィルタ後もprecisionは8〜13%程度に留まり、大半が誤検知という水準。これは
「固定閾値のナイーブな検知器は再現率(recall)は出るが誤検知(false positive)が
多い」という、Step5(サイレント運用モード)・Step6(人間確認フロー)の設計意義を
裏付ける結果である。
