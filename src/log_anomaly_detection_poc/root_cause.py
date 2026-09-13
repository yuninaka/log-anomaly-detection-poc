import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from openai import AzureOpenAI

from log_anomaly_detection_poc.data_layers import MetadataRecord, RawDataRecord

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "根本原因分析に失敗しました。時間をおいて再度お試しください。"
SYSTEM_PROMPT = (
    "あなたはWebサービスの障害調査を支援するアシスタントです。"
    "与えられたアクセスログの要約から、考えられる根本原因を簡潔に日本語で述べてください。"
)


class AzureOpenAIConfigurationError(RuntimeError):
    """Azure OpenAIの接続情報(環境変数)が不足している場合に送出する。"""


@dataclass(frozen=True)
class RootCauseAnalysisInput:
    """外部LLM APIに送信してよい情報のみを保持する(RawDataRecordからcustomer_idを除く)。

    人間が画面上で確認してよい情報(RawDataRecord、Step6)と、外部LLM APIに
    送信してよい情報は別の許可レベルである。根本原因分析(タイムスタンプ・
    ステータスコード・レイテンシのパターン分析)という目的に対してcustomer_idは
    不要な情報のため、そもそも保持しない。
    """

    scenario_id: str
    timestamp: datetime
    endpoint: str
    status_code: int
    latency_ms: float


def to_root_cause_analysis_input(
    records: Sequence[RawDataRecord],
) -> list[RootCauseAnalysisInput]:
    """RawDataRecordからcustomer_idを除いたLLM入力専用の型に変換する。"""
    return [
        RootCauseAnalysisInput(
            scenario_id=r.scenario_id,
            timestamp=r.timestamp,
            endpoint=r.endpoint,
            status_code=r.status_code,
            latency_ms=r.latency_ms,
        )
        for r in records
    ]


def _format_record(record: RootCauseAnalysisInput) -> str:
    return (
        f"{record.timestamp.isoformat()} {record.endpoint} "
        f"status={record.status_code} latency_ms={record.latency_ms:.1f}"
    )


def build_root_cause_prompt(
    metadata: MetadataRecord, records: Sequence[RootCauseAnalysisInput]
) -> str:
    """根本原因分析用のプロンプトを構築する(pure関数)。

    引数の型はRootCauseAnalysisInputのみを受け付け、RawDataRecordを渡すと
    mypyエラーになる(Step3・Step6と同じ型分離の手法)。
    """
    lines = [_format_record(r) for r in records]
    joined = "\n".join(lines)
    return (
        f"バケット: {metadata.module_name} ({metadata.window_start.isoformat()})\n"
        f"平均レイテンシ: {metadata.avg_latency_ms:.1f}ms, "
        f"エラー率: {metadata.error_rate:.1%}, "
        f"リクエスト数: {metadata.request_count}\n\n"
        f"リクエストログ:\n{joined}"
    )


@dataclass(frozen=True)
class AzureOpenAIConfig:
    """Azure OpenAI呼び出しに必要な設定一式(APIキー自体は保持しない)。

    summarize_root_causeがclientとは別にdeployment_nameを必要とするため、
    os.environの再読込に頼らずこの2つをまとめて渡せるようにする。
    """

    client: AzureOpenAI
    deployment_name: str


def create_azure_openai_client() -> AzureOpenAIConfig:
    """環境変数からAzure OpenAIクライアントと設定を構築する。

    未設定の環境変数がある場合はAzureOpenAIConfigurationErrorを送出する
    (どの環境変数が不足しているかは伝えるが、APIキーの値そのものは
    例外メッセージに一切含めない)。
    """
    required_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT_NAME",
        "AZURE_OPENAI_API_VERSION",
    ]
    missing = [name for name in required_vars if not os.environ.get(name)]
    if missing:
        raise AzureOpenAIConfigurationError(
            f"環境変数が設定されていません: {', '.join(missing)}"
        )
    deployment_name = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
    client = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=deployment_name,
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    )
    return AzureOpenAIConfig(client=client, deployment_name=deployment_name)


def summarize_root_cause(client: AzureOpenAI, deployment_name: str, prompt: str) -> str:
    """Azure OpenAIに根本原因分析を依頼する(IOを伴う)。

    失敗時は例外の詳細をログにのみ残し、呼び出し元には固定文言を返す
    (CLAUDE.mdの機微情報の扱い節: ユーザー向け画面には固定文言のみ表示する)。
    """
    try:
        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception:
        logger.exception("Azure OpenAIへの根本原因分析リクエストに失敗しました")
        return FALLBACK_MESSAGE

    content = response.choices[0].message.content
    return content if content else FALLBACK_MESSAGE
