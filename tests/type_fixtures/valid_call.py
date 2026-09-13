from datetime import datetime, timezone

from log_anomaly_detection_poc.data_layers import MetadataRecord
from log_anomaly_detection_poc.detection import (
    compute_isolation_forest_anomaly_score,
    compute_stl_anomaly_score,
)

record = MetadataRecord(
    scenario_id="dummy",
    module_name="/api/login",
    window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    avg_latency_ms=100.0,
    error_rate=0.0,
    request_count=1,
)

compute_stl_anomaly_score([record])
compute_isolation_forest_anomaly_score([record])
