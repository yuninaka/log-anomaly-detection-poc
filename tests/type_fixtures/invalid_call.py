from datetime import datetime, timezone

from log_anomaly_detection_poc.data_layers import RawDataRecord
from log_anomaly_detection_poc.detection import (
    compute_isolation_forest_anomaly_score,
    compute_stl_anomaly_score,
)

record = RawDataRecord(
    scenario_id="dummy",
    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    endpoint="/api/login",
    status_code=200,
    latency_ms=100.0,
    customer_id="cust-000001",
)

# 生データ層を検知関数に渡すのは型レベルで禁止されている。mypyがこの2行を
# それぞれエラーとして検出することを tests/test_type_separation.py で検証している。
compute_stl_anomaly_score([record])
compute_isolation_forest_anomaly_score([record])
