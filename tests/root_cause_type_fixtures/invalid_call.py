from datetime import datetime, timezone

from log_anomaly_detection_poc.data_layers import MetadataRecord, RawDataRecord
from log_anomaly_detection_poc.root_cause import build_root_cause_prompt

metadata = MetadataRecord(
    scenario_id="dummy",
    module_name="/api/login",
    window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    avg_latency_ms=100.0,
    error_rate=0.0,
    request_count=1,
)
record = RawDataRecord(
    scenario_id="dummy",
    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    endpoint="/api/login",
    status_code=200,
    latency_ms=100.0,
    customer_id="cust-000001",
)

# customer_idを含むRawDataRecordを外部LLM API向けのプロンプト構築に直接渡すのは
# 型レベルで禁止されている。mypyがこの行をエラーとして検出することを
# tests/test_root_cause_type_separation.py で検証している。
build_root_cause_prompt(metadata, [record])
