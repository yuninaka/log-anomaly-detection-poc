# Step6: 人間確認UI(Streamlit、2段階開示)

Issue: #15

## 方針

- `src/log_anomaly_detection_poc/ui_logic.py`(新規、pure/オーケストレーション関数)
  - `run_detection_pipeline(days: int, seed: int) -> tuple[pd.DataFrame, list[SilentModeRecord]]`:
    本番相当のパイプライン(`generate_logs` → `aggregate_observed_logs` →
    `to_metadata_records` → `compute_stl_anomaly_score`/`compute_isolation_forest_anomaly_score`
    → `accumulate_silent_mode_records`)を実行する。`ground_truth`は一切使わない
    (Step4/5の評価専用パイプライン`evaluate_cli.evaluate_at_scale`とは別物であり、
    本番運用でラベルが存在しないことを反映する)。戻り値は
    (観測ログDataFrame, 全SilentModeRecordのリスト)。観測ログDataFrameは
    第2段階の生データ層開示のために保持する
  - `flagged_records(records: Sequence[SilentModeRecord]) -> list[SilentModeRecord]`:
    `flagged=True`のみを抽出するpure関数
  - 閾値はSTLが`evaluation.STL_ANOMALY_THRESHOLD`、IsolationForestが
    `evaluation.ISOLATION_FOREST_ANOMALY_THRESHOLD`をそのまま流用する
    (Step4で確立した固定閾値の方針を継続。UIのために閾値を独自に調整しない)
- `src/log_anomaly_detection_poc/data_layers.py`に追加:
  - `raw_data_records_for_window(observed: pd.DataFrame, module_name: str, window_start: datetime, freq: str = DEFAULT_FREQ, seed: int = 0) -> list[RawDataRecord]`:
    指定した1バケット(`module_name`+`window_start`)のみを`RawDataRecord`に変換する。
    既存の`to_raw_data_records`は観測ログ全体を無条件で変換するためUIからは使わず、
    この新関数を使うことで「人間が明示的に確認を選択した場合にのみ」生データ層への
    変換自体が発生することをコードのフローとして保証する
- `src/log_anomaly_detection_poc/ui.py`(新規、Streamlitレンダリングのみの薄い層)
  - 日数セレクタ: `[7, 14, 30]`(Step4で実測済みの値に限定。他の値は所要時間の実績が
    ないため選択肢に含めない)
  - 実行中は`st.spinner`等で明確なローディング表示を出す(Step4/5の実測で
    7日=約25秒・14日=約50秒・30日=約125〜140秒かかることが分かっているため)
  - 第1段階: `flagged_records`の一覧を表示(`scenario_id`・`module_name`・
    `window_start`・`algorithm`・`score`のみ。`RawDataRecord`は一切importしない
    表示関数として実装する)
  - 第2段階: 一覧の各行に「生データ層を確認する」ボタンを設置し、押下時のみ
    `raw_data_records_for_window`を呼び出し、該当バケットの`RawDataRecord`
    (`timestamp`/`endpoint`/`status_code`/`latency_ms`/`customer_id`)を表示する
  - `st.session_state`でどのボタンが押されたかを管理し、ページ再描画のたびに
    生データ層を再計算しないようにする
- `uv add streamlit`で依存関係に追加

## テスト方針

- `ui_logic.run_detection_pipeline`: 実データでの動作確認(実リソースに対する実行)。
  戻り値のSilentModeRecord件数・flagged件数が妥当な範囲か確認し、結果をこのplanに記録
- `ui_logic.flagged_records`: 正常系(flagged True/False混在)・空リスト
- `data_layers.raw_data_records_for_window`: 指定バケットのみが対象になること
  (他バケットの行が混入しないこと)・該当行が0件の場合・境界値(バケット境界ちょうどの
  タイムスタンプ)
- `ui.py`自体はpytestでの自動テスト対象外(Streamlitレンダリング)。
  `uv run streamlit run src/log_anomaly_detection_poc/ui.py`で実際に起動し、
  日数選択→ローディング表示→一覧表示→ボタン押下→生データ層表示、の一連のフローを
  ブラウザで確認する

## 実行結果

(実装後に記録)
