import logging

import streamlit as st

from log_anomaly_detection_poc.data_layers import raw_data_records_for_window
from log_anomaly_detection_poc.log_generator import DEFAULT_SEED
from log_anomaly_detection_poc.root_cause import (
    AzureOpenAIConfigurationError,
    build_root_cause_prompt,
    create_azure_openai_client,
    summarize_root_cause,
    to_root_cause_analysis_input,
)
from log_anomaly_detection_poc.ui_logic import (
    DAY_COUNT_CHOICES,
    flagged_records,
    metadata_by_scenario_id,
    run_detection_pipeline,
)

logger = logging.getLogger(__name__)

AZURE_NOT_CONFIGURED_MESSAGE = (
    "Azure OpenAIの接続設定が完了していないため、根本原因分析を実行できません。"
)

st.set_page_config(page_title="人間確認UI - log-anomaly-detection-poc")
st.title("異常検知結果の人間確認")
st.caption(
    "第1段階(下の一覧)はメタデータ層のみを表示する。"
    "生データ層(顧客IDを含む)は各行の「生データ層を確認する」ボタンを"
    "押した場合にのみ、そのバケットだけを対象に表示する。"
    "根本原因分析(3段階目)はさらに別のボタンを押した場合にのみ、"
    "customer_idを除いた情報だけを外部LLM(Azure OpenAI)に送信して実行する。"
)

days = st.selectbox("学習データ量(日数)", DAY_COUNT_CHOICES)

if st.button("検知を実行する"):
    with st.spinner(f"{days}日分のログ生成・検知を実行中(数十秒〜数分かかります)..."):
        observed, metadata, records = run_detection_pipeline(days, seed=DEFAULT_SEED)
    st.session_state["observed"] = observed
    st.session_state["metadata_by_scenario_id"] = metadata_by_scenario_id(metadata)
    st.session_state["flagged"] = flagged_records(records)
    st.session_state.pop("revealed_scenario_id", None)

if "flagged" in st.session_state:
    flagged = st.session_state["flagged"]
    st.subheader(f"検知結果(flagged: {len(flagged)}件)")

    if not flagged:
        st.write("flaggedなレコードはありません。")

    for record in flagged:
        metadata = st.session_state["metadata_by_scenario_id"][record.scenario_id]
        with st.container(border=True):
            st.write(
                f"**{record.algorithm}** | {metadata.module_name} | "
                f"{metadata.window_start} | score={record.score:.2f}"
            )
            # scenario_idはSTL・IsolationForestの両方でflaggedになりうるため、
            # algorithmも含めてキーを一意にする(重複するとStreamlitが例外を出す)。
            reveal_key = f"reveal-{record.algorithm}-{record.scenario_id}"
            if st.button("生データ層を確認する", key=reveal_key):
                st.session_state["revealed_scenario_id"] = record.scenario_id

            if st.session_state.get("revealed_scenario_id") == record.scenario_id:
                raw_records = raw_data_records_for_window(
                    st.session_state["observed"],
                    metadata.module_name,
                    metadata.window_start,
                )
                st.dataframe(raw_records)

                analyze_key = f"analyze-{record.algorithm}-{record.scenario_id}"
                if st.button("LLMによる根本原因分析を依頼する", key=analyze_key):
                    with st.spinner("Azure OpenAIに根本原因分析を依頼中..."):
                        try:
                            config = create_azure_openai_client()
                            analysis_input = to_root_cause_analysis_input(raw_records)
                            prompt = build_root_cause_prompt(metadata, analysis_input)
                            result = summarize_root_cause(
                                config.client, config.deployment_name, prompt
                            )
                        except AzureOpenAIConfigurationError:
                            logger.exception("Azure OpenAIの接続設定が不足しています")
                            result = AZURE_NOT_CONFIGURED_MESSAGE
                    root_cause_results = st.session_state.setdefault(
                        "root_cause_results", {}
                    )
                    root_cause_results[record.scenario_id] = result

                root_cause_results = st.session_state.get("root_cause_results", {})
                if record.scenario_id in root_cause_results:
                    st.info(root_cause_results[record.scenario_id])
