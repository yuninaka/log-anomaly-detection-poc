from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import numpy as np
import pandas as pd

Label = Literal["normal", "noise", "anomaly"]
AnomalyType = Literal["isolated_latency_blip", "latency_spike", "error_spike"] | None

LOG_COLUMNS = [
    "timestamp",
    "endpoint",
    "status_code",
    "latency_ms",
    "label",
    "anomaly_type",
]

BUSINESS_HOUR_START = 9
BUSINESS_HOUR_END = 19
SATURDAY_WEEKDAY = 5
WEEKEND_TRAFFIC_MULTIPLIER = 0.3
NIGHT_TRAFFIC_MULTIPLIER = 0.15
BASE_REQUESTS_PER_HOUR = 200

NOISE_PROBABILITY = 0.0005
NOISE_LATENCY_MULTIPLIER = 6.0

LATENCY_ANOMALY_MULTIPLIER = 4.0
LATENCY_ANOMALY_MIN_MINUTES = 30
LATENCY_ANOMALY_MAX_MINUTES = 60

ERROR_ANOMALY_RATE = 0.5
ERROR_ANOMALY_MIN_MINUTES = 15
ERROR_ANOMALY_MAX_MINUTES = 45
ERROR_ANOMALY_STATUS_CODES = (500, 503)

DEFAULT_SEED = 42


@dataclass(frozen=True)
class EndpointProfile:
    name: str
    mean_latency_ms: float
    std_latency_ms: float
    baseline_error_rate: float


ENDPOINT_PROFILES: tuple[EndpointProfile, ...] = (
    EndpointProfile(
        "/api/login",
        mean_latency_ms=120.0,
        std_latency_ms=30.0,
        baseline_error_rate=0.02,
    ),
    EndpointProfile(
        "/api/search",
        mean_latency_ms=200.0,
        std_latency_ms=60.0,
        baseline_error_rate=0.01,
    ),
    EndpointProfile(
        "/api/orders",
        mean_latency_ms=150.0,
        std_latency_ms=40.0,
        baseline_error_rate=0.015,
    ),
    EndpointProfile(
        "/api/users",
        mean_latency_ms=80.0,
        std_latency_ms=20.0,
        baseline_error_rate=0.005,
    ),
    EndpointProfile(
        "/health", mean_latency_ms=10.0, std_latency_ms=3.0, baseline_error_rate=0.001
    ),
)


def _traffic_multiplier(hour_start: datetime) -> float:
    if hour_start.weekday() >= SATURDAY_WEEKDAY:
        return WEEKEND_TRAFFIC_MULTIPLIER
    if BUSINESS_HOUR_START <= hour_start.hour < BUSINESS_HOUR_END:
        return 1.0
    return NIGHT_TRAFFIC_MULTIPLIER


def _empty_log_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=LOG_COLUMNS)


def _sample_profiles(n: int, rng: np.random.Generator) -> list[EndpointProfile]:
    indices = rng.integers(0, len(ENDPOINT_PROFILES), size=n)
    return [ENDPOINT_PROFILES[i] for i in indices]


def _sample_timestamps(
    hour_start: datetime, n: int, rng: np.random.Generator
) -> list[datetime]:
    offsets_seconds = rng.uniform(0, 3600, size=n)
    return [hour_start + timedelta(seconds=float(s)) for s in offsets_seconds]


def _sample_latency(
    profiles: list[EndpointProfile], rng: np.random.Generator
) -> np.ndarray:
    means = np.array([p.mean_latency_ms for p in profiles])
    stds = np.array([p.std_latency_ms for p in profiles])
    return np.asarray(
        rng.lognormal(mean=np.log(means), sigma=stds / means), dtype=float
    )


def _sample_status_codes(
    profiles: list[EndpointProfile], rng: np.random.Generator
) -> np.ndarray:
    error_rates = np.array([p.baseline_error_rate for p in profiles])
    n = len(error_rates)
    is_error = rng.random(n) < error_rates
    ok_codes = rng.choice([200, 201], size=n)
    error_codes = rng.choice([400, 404, 500], size=n)
    return np.where(is_error, error_codes, ok_codes)


def _generate_hour_requests(
    hour_start: datetime, rng: np.random.Generator
) -> pd.DataFrame:
    expected = BASE_REQUESTS_PER_HOUR * _traffic_multiplier(hour_start)
    n = int(rng.poisson(expected))
    if n == 0:
        return _empty_log_frame()

    profiles = _sample_profiles(n, rng)
    return pd.DataFrame(
        {
            "timestamp": _sample_timestamps(hour_start, n, rng),
            "endpoint": [p.name for p in profiles],
            "status_code": _sample_status_codes(profiles, rng).astype(int),
            "latency_ms": _sample_latency(profiles, rng),
            "label": ["normal"] * n,
            "anomaly_type": [None] * n,
        }
    )


def _generate_baseline_requests(
    start: datetime, days: int, rng: np.random.Generator
) -> pd.DataFrame:
    total_hours = days * 24
    hours = [start + timedelta(hours=h) for h in range(total_hours)]
    frames = [_generate_hour_requests(hour, rng) for hour in hours]
    if not frames:
        return _empty_log_frame()
    return pd.concat(frames, ignore_index=True)


def _inject_isolated_noise(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    if df.empty:
        return df
    is_noise = rng.random(len(df)) < NOISE_PROBABILITY
    df.loc[is_noise, "latency_ms"] = (
        df.loc[is_noise, "latency_ms"] * NOISE_LATENCY_MULTIPLIER
    )
    df.loc[is_noise, "label"] = "noise"
    df.loc[is_noise, "anomaly_type"] = "isolated_latency_blip"
    return df


def _random_window(
    week_start: datetime, rng: np.random.Generator, min_minutes: int, max_minutes: int
) -> tuple[datetime, datetime]:
    offset_hours = float(rng.uniform(0, 7 * 24))
    duration_minutes = int(rng.integers(min_minutes, max_minutes + 1))
    window_start = week_start + timedelta(hours=offset_hours)
    window_end = window_start + timedelta(minutes=duration_minutes)
    return window_start, window_end


def _random_endpoint_name(rng: np.random.Generator) -> str:
    return ENDPOINT_PROFILES[int(rng.integers(0, len(ENDPOINT_PROFILES)))].name


def _rows_in_window(
    df: pd.DataFrame, window_start: datetime, window_end: datetime, endpoint: str
) -> pd.Series:
    return (
        (df["timestamp"] >= window_start)
        & (df["timestamp"] < window_end)
        & (df["endpoint"] == endpoint)
    )


def _inject_one_latency_spike(
    df: pd.DataFrame, week_start: datetime, rng: np.random.Generator
) -> pd.DataFrame:
    window_start, window_end = _random_window(
        week_start, rng, LATENCY_ANOMALY_MIN_MINUTES, LATENCY_ANOMALY_MAX_MINUTES
    )
    endpoint = _random_endpoint_name(rng)
    in_window = _rows_in_window(df, window_start, window_end, endpoint)
    df.loc[in_window, "latency_ms"] = (
        df.loc[in_window, "latency_ms"] * LATENCY_ANOMALY_MULTIPLIER
    )
    df.loc[in_window, "label"] = "anomaly"
    df.loc[in_window, "anomaly_type"] = "latency_spike"
    return df


def _inject_one_error_spike(
    df: pd.DataFrame, week_start: datetime, rng: np.random.Generator
) -> pd.DataFrame:
    window_start, window_end = _random_window(
        week_start, rng, ERROR_ANOMALY_MIN_MINUTES, ERROR_ANOMALY_MAX_MINUTES
    )
    endpoint = _random_endpoint_name(rng)
    in_window = _rows_in_window(df, window_start, window_end, endpoint)
    becomes_error = in_window & (rng.random(len(df)) < ERROR_ANOMALY_RATE)
    df.loc[becomes_error, "status_code"] = rng.choice(
        ERROR_ANOMALY_STATUS_CODES, size=int(becomes_error.sum())
    )
    df.loc[in_window, "label"] = "anomaly"
    df.loc[in_window, "anomaly_type"] = "error_spike"
    return df


def _inject_weekly_anomalies(
    df: pd.DataFrame, start: datetime, days: int, rng: np.random.Generator
) -> pd.DataFrame:
    for week in range(max(1, days // 7)):
        week_start = start + timedelta(days=week * 7)
        df = _inject_one_latency_spike(df, week_start, rng)
        df = _inject_one_error_spike(df, week_start, rng)
    return df


def generate_logs(start: datetime, days: int, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = _generate_baseline_requests(start, days, rng)
    if df.empty:
        return df
    df = _inject_isolated_noise(df, rng)
    df = _inject_weekly_anomalies(df, start, days, rng)
    return df.sort_values("timestamp").reset_index(drop=True)
