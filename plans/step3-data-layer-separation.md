# Step3: メタデータ層と生データ層の型分離

Issue: #7

## 方針

PoC全体の存在意義となる最重要ステップのため、他のどのステップより丁寧に進める。

- `src/log_anomaly_detection_poc/data_layers.py` に2つの frozen dataclass を定義する
  - `MetadataRecord`(5分バケット単位、Step2の集計結果から構築): `scenario_id`(一意識別子)・
    `module_name`(=endpoint)・`window_start`・`avg_latency_ms`・`error_rate`・`request_count`。
    機微情報は一切含まない
  - `RawDataRecord`(個々のリクエスト単位、Step1のobservedから構築): `scenario_id`(所属する
    バケットのID、MetadataRecordと同じキーで紐付け)・`timestamp`・`endpoint`・`status_code`・
    `latency_ms`・`customer_id`(ダミー顧客ID、`data_layers.py`内で合成。Step1のCSVスキーマは
    変更しない)
- 検知関数は `Sequence[MetadataRecord]` のみを型として受け取るダミー実装にする
  (`_dummy_anomaly_score`。実際の検知ロジックはStep4のSTL分解・IsolationForestで実装)。
  `RawDataRecord`は別のdataclassなのでnominal typingにより自然にmypyエラーになる
- 「型分離が崩れていないこと」自体を検証するテスト
  - `tests/type_fixtures/valid_call.py`: `MetadataRecord`を正しく渡す呼び出し(mypy通過)
  - `tests/type_fixtures/invalid_call.py`: `RawDataRecord`を渡す誤った呼び出し(mypyエラー)
  - `tests/test_type_separation.py`: `.venv/bin/mypy`をsubprocessで実行し、正常系は
    exit code 0、異常系は exit code 1 であることを主基準に検証する。メッセージはmypy
    バージョン依存で変わりうるため、完全一致ではなく緩い部分一致(対象クラス名を含むか程度)
    に留める
  - `pyproject.toml`の`[tool.mypy]`に`exclude`を追加し、`tests/type_fixtures/`を通常の
    CI用mypy実行(`mypy src tests`)から除外する(意図的な型エラーファイルのため)

## 事前検証結果

- `.venv/bin/mypy`の起動オーバーヘッドは約0.12秒/回。正常系・異常系の2回で約0.25秒の
  追加(現在の全体テスト実行時間2.8秒に対して約9%増)。許容範囲と判断
- Step2までで発生したpytest特異的なフレーキー停止(原因未特定)を踏まえ、このテスト追加後の
  ci_check.sh実行時間に異常な増加がないかフォアグラウンドで確認する

## テスト方針

- `data_layers.py`の変換関数: 正常系・エッジケース(空DataFrame)・
  MetadataRecordとRawDataRecordのscenario_idが正しく対応すること・customer_idが
  Step1のCSVには存在しない合成値であること
- 型分離検証テスト: 上記の通り
