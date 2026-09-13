# Step2: 前処理・構造化

Issue: #5

## 方針

- `src/log_anomaly_detection_poc/preprocessing.py` に `aggregate_observed_logs` を実装する
- シグネチャ: `aggregate_observed_logs(observed: pd.DataFrame, start: datetime, end: datetime, freq: str = "5min") -> pd.DataFrame`
  - `start`/`end`を明示的に受け取るのは、実際のトラフィックが存在しない先頭・末尾バケットも
    含めた完全なグリッドを生成するため(データの`min`/`max`だけでは復元できない)
- 出力列: `window_start`, `endpoint`, `avg_latency_ms`, `error_rate`, `request_count`
- `error_rate`は5xxステータスのみを対象とする(4xxはクライアント起因ノイズとして除外し、
  error_spike異常のシグナルを薄めないため。docstringに根拠を明記)
- 全エンドポイント×全期間の5分バケットを0埋めで網羅する完全なグリッドを生成する
  - `request_count=0`のバケット: `error_rate=0.0`(エラーが発生していないため)、
    `avg_latency_ms=NaN`(リクエストがなくレイテンシ自体が未定義のため)
  - STL分解が前提とする等間隔時系列を壊さないこと、「トラフィックがない」ことを
    「データが欠損している」と区別可能にすることが理由

## テスト方針

- 正常系: 既知の小さな入力から期待通りの集計結果になること
- エッジケース: 空の入力、全バケットがトラフィックゼロの期間
- 境界値: 5分バケットの境界にまたがるタイムスタンプの振り分け
- error_rate: 4xxのみのバケットでerror_rate=0になること、5xxが含まれるバケットのみ計上されること
- ゼロ埋め: リクエストが存在しないバケットがrequest_count=0・error_rate=0.0・avg_latency_ms=NaNで
  行として存在すること
- 複数エンドポイントが独立して集計されること
