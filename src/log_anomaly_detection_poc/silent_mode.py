import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from log_anomaly_detection_poc.data_layers import MetadataRecord
from log_anomaly_detection_poc.evaluation import PrecisionRecall

DEFAULT_PROMOTION_THRESHOLD = 0.5

DecisionReason = Literal["ready", "insufficient_precision", "insufficient_samples"]


@dataclass(frozen=True)
class SilentModeRecord:
    """サイレントモード中に蓄積するだけのレコード(通知は一切発生しない)。

    このdataclassを返すだけの関数として実装することで、「検知結果を即座に
    通知しない」ことを実行時チェックではなく関数の契約自体で保証する。
    """

    scenario_id: str
    algorithm: str
    score: float
    flagged: bool


@dataclass(frozen=True)
class SilentModeDecision:
    """サイレントモード期間の精度から、本番トリアージフローへの移行可否を表す。"""

    algorithm: str
    precision: float
    threshold: float
    ready_for_production: bool
    reason: DecisionReason


def accumulate_silent_mode_records(
    metadata: Sequence[MetadataRecord],
    scores: Sequence[float],
    threshold: float,
    algorithm: str,
) -> list[SilentModeRecord]:
    """検知スコアをサイレントモードのレコードとして蓄積する(通知しない)。"""
    return [
        SilentModeRecord(
            scenario_id=m.scenario_id,
            algorithm=algorithm,
            score=score,
            flagged=score >= threshold,
        )
        for m, score in zip(metadata, scores, strict=True)
    ]


def decide_production_readiness(
    algorithm: str,
    result: PrecisionRecall,
    threshold: float = DEFAULT_PROMOTION_THRESHOLD,
) -> SilentModeDecision:
    """サイレントモード期間のprecisionから本番移行可否を判定する。

    resultには、評価対象を絞り込んだ後(MIN_REQUEST_COUNT_FOR_EVALUATION適用後)の
    PrecisionRecallを渡すこと。フィルタ前の値は低トラフィックバケットの分散不安定性を
    含んだままであり、本番移行判定には不適切。

    precisionがNaN(TP+FP=0、サイレントモード期間中に陽性判定を一件も出さなかった場合)と、
    精度不足で閾値に届かない場合を"reason"で区別する。recallがNaN(TP+FN=0、実異常
    サンプルが0件)かどうかはこの判定に関与しない――precisionが算出できている限り
    "insufficient_precision"になる。両方ともready_for_production=Falseになるが、
    原因が異なるため人間が読んだときに次に取るべき対応(データを待つのか、検知ロジックを
    見直すのか)が分かる。
    """
    if math.isnan(result.precision):
        return SilentModeDecision(
            algorithm=algorithm,
            precision=result.precision,
            threshold=threshold,
            ready_for_production=False,
            reason="insufficient_samples",
        )
    ready = result.precision >= threshold
    reason: DecisionReason = "ready" if ready else "insufficient_precision"
    return SilentModeDecision(
        algorithm=algorithm,
        precision=result.precision,
        threshold=threshold,
        ready_for_production=ready,
        reason=reason,
    )
