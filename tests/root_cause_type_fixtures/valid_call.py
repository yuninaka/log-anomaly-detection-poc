from datetime import datetime, timezone

from log_anomaly_detection_poc.data_layers import MetadataRecord
from log_anomaly_detection_poc.root_cause import (
    RootCauseAnalysisInput,
    build_root_cause_prompt,
)

metadata = MetadataRecord(
    scenario_id="dummy",
    module_name="/api/login",
    window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    avg_latency_ms=100.0,
    error_rate=0.0,
    request_count=1,
)
record = RootCauseAnalysisInput(
    scenario_id="dummy",
    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    endpoint="/api/login",
    status_code=200,
    latency_ms=100.0,
)

build_root_cause_prompt(metadata, [record])
