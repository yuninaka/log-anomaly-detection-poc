# Step7: LLM根本原因分析(Azure OpenAI、人間確認後のみ)

Issue: #17

## 方針

- `src/log_anomaly_detection_poc/root_cause.py`(新規)
  - `RootCauseAnalysisInput`(frozen dataclass): `scenario_id`・`timestamp`・
    `endpoint`・`status_code`・`latency_ms`。`RawDataRecord`から`customer_id`を
    除いた専用型。「人間が画面上で確認してよい情報」(Step6)と「外部LLM APIに
    送信してよい情報」は別の許可レベルであり、混同しない。根本原因分析
    (タイムスタンプ・ステータスコード・レイテンシのパターン分析)という目的に
    対してcustomer_idは不要な情報であるため、そもそも渡さない設計にする
  - `to_root_cause_analysis_input(records: Sequence[RawDataRecord]) -> list[RootCauseAnalysisInput]`:
    pureな変換関数
  - `build_root_cause_prompt(metadata: MetadataRecord, records: Sequence[RootCauseAnalysisInput]) -> str`:
    pureなプロンプト構築関数
  - `summarize_root_cause(client: AzureOpenAI, prompt: str) -> str`: IOを伴う
    Azure OpenAI呼び出し。型シグネチャは`Sequence[RootCauseAnalysisInput]`
    由来のプロンプト文字列のみを受け付ける(呼び出し元で`RawDataRecord`から
    直接プロンプトを組み立てることを防ぐため、`build_root_cause_prompt`の
    引数型を`Sequence[RootCauseAnalysisInput]`のみとし、`RawDataRecord`を
    渡すとmypyエラーになるようにする。Step3・Step6と同じ型分離の手法)
  - `create_azure_openai_client() -> AzureOpenAI`: 環境変数
    (`AZURE_OPENAI_API_KEY`・`AZURE_OPENAI_ENDPOINT`・
    `AZURE_OPENAI_DEPLOYMENT_NAME`・`AZURE_OPENAI_API_VERSION`)からクライアントを
    構築するIO関数。未設定の場合は`AzureOpenAIConfigurationError`
    (カスタム例外)を送出し、詳細な環境変数名は例外メッセージに含めるが
    APIキーの値そのものは絶対に含めない
  - 例外は`logging`モジュールでサーバー側ログにのみ詳細を残し、UI(呼び出し元)
    には固定文言のみを返す設計にする(CLAUDE.mdの機微情報の扱い節に準拠)
- `tests/root_cause_type_fixtures/`(新規、`tests/type_fixtures/`と同じ手法):
  - `valid_call.py`: `RootCauseAnalysisInput`を正しく渡す呼び出し
  - `invalid_call.py`: `RawDataRecord`を渡す誤った呼び出し
  - `tests/test_root_cause_type_separation.py`: 上記2ファイルにmypyを
    subprocessで実行し、境界が壊れていないことを検証(`tests/test_type_separation.py`
    と同じ構造)
- UI(`ui.py`)に3段階目を追加: Step6の「生データ層を確認する」ボタンで
  生データ層を開示した後にのみ、「LLMによる根本原因分析を依頼する」ボタンを
  表示する。押下時のみ`create_azure_openai_client`・`summarize_root_cause`が
  呼ばれる(それまではAzure OpenAIへの接続自体が一切発生しない)
- 結果は永続化しない(Step5・Step6と同じ、まだ使われていない機能のために
  スキーマを先回りで拡張しない判断)
- `uv add openai`(Azure OpenAI SDK)

## 実APIへの接続検証について

今回はAzure OpenAIの認証情報(APIキー・エンドポイント)が用意されていないため、
`summarize_root_cause`はモック(フェイククライアント)でのみ検証する。実credentials
を使った動作確認はユーザーが後日自分の環境(`AZURE_OPENAI_API_KEY`等を設定)で
行う。`create_azure_openai_client`・`summarize_root_cause`の実リソースに対する
動作確認は、この計画ファイルには「未実施」として明記し、隠さず残す。

## テスト方針

- `to_root_cause_analysis_input`: 正常系(複数件)・空リスト・customer_idが
  結果に含まれないことの明示的な否定テスト
- `build_root_cause_prompt`: プロンプトに必要な情報(scenario_id・timestamp・
  endpoint・status_code・latency_ms)が含まれること、customer_idという
  文字列そのものがプロンプトに含まれないこと
- `summarize_root_cause`: フェイククライアント(`unittest.mock.Mock`または
  手製フェイク)でのモック検証。API呼び出し失敗時に固定文言を返すことを確認
- `create_azure_openai_client`: 環境変数未設定時に`AzureOpenAIConfigurationError`
  を送出すること(pytestの`monkeypatch.delenv`で検証)。実際にAzure OpenAIに
  接続する実リソーステストは行わない(上記の通り)
- 型分離: `tests/test_root_cause_type_separation.py`でmypy subprocess検証

## 実行結果

(実装後に記録)
