import streamlit as st

from log_anomaly_detection_poc.data_layers import raw_data_records_for_window
from log_anomaly_detection_poc.log_generator import DEFAULT_SEED
from log_anomaly_detection_poc.ui_logic import (
    DAY_COUNT_CHOICES,
    flagged_records,
    metadata_by_scenario_id,
    run_detection_pipeline,
)

st.set_page_config(page_title="人間確認UI - log-anomaly-detection-poc")
st.title("異常検知結果の人間確認")
st.caption(
    "第1段階(下の一覧)はメタデータ層のみを表示する。"
    "生データ層(顧客IDを含む)は各行の「生データ層を確認する」ボタンを"
    "押した場合にのみ、そのバケットだけを対象に表示する。"
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
