from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from openai import AzureOpenAI

from log_anomaly_detection_poc.data_layers import MetadataRecord, RawDataRecord
from log_anomaly_detection_poc.root_cause import (
    FALLBACK_MESSAGE,
    AzureOpenAIConfigurationError,
    build_root_cause_prompt,
    create_azure_openai_client,
    summarize_root_cause,
    to_root_cause_analysis_input,
)

DEPLOYMENT_NAME = "gpt-4o-dummy-deployment"

START = datetime(2026, 1, 5, tzinfo=timezone.utc)
EXPECTED_STATUS_CODE = 200
EXPECTED_LATENCY_MS = 100.0
REQUIRED_ENV_VARS = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "AZURE_OPENAI_API_VERSION",
]


def _raw_record(customer_id: str = "cust-000001") -> RawDataRecord:
    return RawDataRecord(
        scenario_id="dummy",
        timestamp=START,
        endpoint="/api/login",
        status_code=200,
        latency_ms=100.0,
        customer_id=customer_id,
    )


def test_to_root_cause_analysis_input_drops_customer_id() -> None:
    records = to_root_cause_analysis_input([_raw_record()])

    assert not hasattr(records[0], "customer_id")


def test_to_root_cause_analysis_input_preserves_other_fields() -> None:
    records = to_root_cause_analysis_input([_raw_record()])

    assert records[0].scenario_id == "dummy"
    assert records[0].timestamp == START
    assert records[0].endpoint == "/api/login"
    assert records[0].status_code == EXPECTED_STATUS_CODE
    assert records[0].latency_ms == EXPECTED_LATENCY_MS


def test_to_root_cause_analysis_input_empty_input() -> None:
    assert to_root_cause_analysis_input([]) == []


def _metadata() -> MetadataRecord:
    return MetadataRecord(
        scenario_id="dummy",
        module_name="/api/login",
        window_start=START,
        avg_latency_ms=100.0,
        error_rate=0.0,
        request_count=1,
    )


def test_build_root_cause_prompt_does_not_leak_customer_id() -> None:
    records = to_root_cause_analysis_input([_raw_record(customer_id="cust-999999")])

    prompt = build_root_cause_prompt(_metadata(), records)

    assert "cust-999999" not in prompt
    assert "customer_id" not in prompt


def test_build_root_cause_prompt_includes_endpoint_and_status() -> None:
    records = to_root_cause_analysis_input([_raw_record()])

    prompt = build_root_cause_prompt(_metadata(), records)

    assert "/api/login" in prompt
    assert "status=200" in prompt


def test_build_root_cause_prompt_empty_records() -> None:
    prompt = build_root_cause_prompt(_metadata(), [])

    assert "/api/login" in prompt


def test_summarize_root_cause_returns_model_response() -> None:
    client = Mock()
    client.chat.completions.create.return_value.choices = [
        Mock(message=Mock(content="レイテンシスパイクが疑われます"))
    ]

    result = summarize_root_cause(client, DEPLOYMENT_NAME, "dummy prompt")

    assert result == "レイテンシスパイクが疑われます"
    client.chat.completions.create.assert_called_once()
    assert client.chat.completions.create.call_args.kwargs["model"] == DEPLOYMENT_NAME


def test_summarize_root_cause_returns_fallback_on_api_error() -> None:
    client = Mock()
    client.chat.completions.create.side_effect = RuntimeError("API error")

    result = summarize_root_cause(client, DEPLOYMENT_NAME, "dummy prompt")

    assert result == FALLBACK_MESSAGE


def test_summarize_root_cause_returns_fallback_on_empty_content() -> None:
    client = Mock()
    client.chat.completions.create.return_value.choices = [
        Mock(message=Mock(content=None))
    ]

    result = summarize_root_cause(client, DEPLOYMENT_NAME, "dummy prompt")

    assert result == FALLBACK_MESSAGE


def test_summarize_root_cause_returns_fallback_on_empty_choices_list() -> None:
    # API呼び出し自体は例外を投げないが、コンテンツフィルタ等でchoicesが
    # 空リストになるケース(実際のAzure OpenAIで起こりうる)。
    # response.choices[0]がIndexErrorを起こし、tryの外で未捕捉のまま
    # UIまで伝播しないことを確認する回帰テスト。
    client = Mock()
    client.chat.completions.create.return_value.choices = []

    result = summarize_root_cause(client, DEPLOYMENT_NAME, "dummy prompt")

    assert result == FALLBACK_MESSAGE


def test_summarize_root_cause_returns_fallback_on_missing_message_attribute() -> None:
    # 想定外のレスポンス構造(messageを持たない)でAttributeErrorになる
    # ケースも未捕捉のまま伝播しないことを確認する。
    client = Mock()
    choice = Mock(spec=[])  # messageもcontentも持たないダミー
    client.chat.completions.create.return_value.choices = [choice]

    result = summarize_root_cause(client, DEPLOYMENT_NAME, "dummy prompt")

    assert result == FALLBACK_MESSAGE


def test_create_azure_openai_client_raises_when_env_vars_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(AzureOpenAIConfigurationError, match="AZURE_OPENAI_API_KEY"):
        create_azure_openai_client()


def test_create_azure_openai_client_error_does_not_leak_api_key_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret-value-should-not-leak")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

    with pytest.raises(AzureOpenAIConfigurationError) as excinfo:
        create_azure_openai_client()

    assert "secret-value-should-not-leak" not in str(excinfo.value)


def test_create_azure_openai_client_returns_config_when_env_vars_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AzureOpenAIのコンストラクタ自体はネットワーク接続を行わないため、
    # ダミーの値でも(実際のAzure OpenAIへの接続なしに)構築を検証できる。
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "dummy-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", DEPLOYMENT_NAME)
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2026-01-01-preview")

    config = create_azure_openai_client()

    assert config.deployment_name == DEPLOYMENT_NAME
    assert isinstance(config.client, AzureOpenAI)
