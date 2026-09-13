# Step5: サイレント運用モード

Issue: #13

## 方針

- `src/log_anomaly_detection_poc/silent_mode.py`(新規)
  - `SilentModeRecord`(frozen dataclass): `scenario_id`・`algorithm`・`score`・`flagged`
  - `accumulate_silent_mode_records(metadata: Sequence[MetadataRecord], scores: Sequence[float], threshold: float, algorithm: str) -> list[SilentModeRecord]`:
    純粋関数。通知(print・アラート送信等)の副作用を一切持たず、データを返すだけであることで
    「検知結果を即座に通知しない」ことを設計上保証する(Step3の型分離と同じく、実行時チェックではなく
    関数の契約自体で担保する発想)
  - `SilentModeDecision`(frozen dataclass): `algorithm`・`precision`・`threshold`・`ready_for_production`・
    `reason`(`Literal["ready", "insufficient_precision", "insufficient_samples"]`)
  - `decide_production_readiness(algorithm: str, result: PrecisionRecall, threshold: float = 0.5) -> SilentModeDecision`:
    - `result.precision`がNaN(評価不能。実異常サンプルが0件等)の場合は`ready_for_production=False`・
      `reason="insufficient_samples"`
    - precisionが閾値未満の場合は`ready_for_production=False`・`reason="insufficient_precision"`
    - precisionが閾値以上の場合は`ready_for_production=True`・`reason="ready"`
    - 「精度不足」と「評価不能」を区別することで、Step4のREADMEで確立した
      「N/Aと0.000は違う」という誠実さの粒度をStep5の判定結果にも引き継ぐ
  - 入力は`Sequence[MetadataRecord]`のみ(Step1・Step3由来の型分離を維持)
- `evaluate_cli.py`に統合: Step4で算出済みのフィルタ後`PrecisionRecall`を使い、日数・アルゴリズムごとに
  「本番移行可能か」の判定結果を追加出力する
- 永続化(CSV/JSON出力、DB保存等)は行わない。Step6の人間確認UIが実際にどんな形式を必要とするかは
  Step6の設計時に決める(まだ使われていない機能のためにスキーマを先回りで拡張しない、というStep1・Step3
  以来の一貫した判断)
- 閾値50%はStep4の実測結果(STL/IsolationForestとも8〜13%程度)を踏まえると「移行不可」判定になる
  見込みだが、これはバグではなく意図通りの結果である。精度を上げるために閾値を恣意的に下げるような
  調整は行わない(Step4のcontamination="auto"・固定閾値の議論と同じ方針)

## テスト方針

- `accumulate_silent_mode_records`: 正常系(スコアが閾値以上/未満で`flagged`が正しく分かれる)・
  空入力・入力順序の保持
- `decide_production_readiness`: 閾値ちょうど(`>=`境界)・閾値未満・NaN(評価不能)の3パターンで
  `ready_for_production`と`reason`が正しく分かれること
- `evaluate_cli.py`統合部分: 実データでの動作確認(実リソースに対する実行、結果をこのplanに記録)

## 実行結果

`uv run python -m log_anomaly_detection_poc.evaluate_cli` を実行(所要時間はStep4と同水準:
7日25.2秒・14日52.7秒・30日138.8秒、前提制約2の見積り通り)。

| 日数 | STL判定 | IsolationForest判定 |
|---|---|---|
| 7日 | 精度不足(precision=0.133) | 精度不足(precision=0.080) |
| 14日 | 精度不足(precision=0.000) | 精度不足(precision=0.000) |
| 30日 | 精度不足(precision=0.103) | 精度不足(precision=0.060) |

いずれも`reason="insufficient_precision"`(precisionが正しく算出された上での閾値未達)であり、
`reason="insufficient_samples"`(NaN)にはならなかった。14日分はrecallはN/A(実異常サンプル0件)
だったが、precision自体は0.000(TP+FP=30件と39件、いずれも的中0件)として正しく算出されており、
「精度不足」と「評価不能」が意図通り区別されていることを確認した。

閾値50%に対して全て「移行不可(精度不足)」という判定は、Step4の実測結果からすれば予想通りであり、
バグではない。閾値を下げて`ready_for_production=True`にするような調整は行っていない。
