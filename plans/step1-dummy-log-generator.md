# Step1: ダミーログ生成

Issue: #3

## 方針

- `src/log_anomaly_detection_poc/log_generator.py` にログ生成の純粋関数群を実装する
- 1リクエスト1行のログを生成する: `timestamp`, `endpoint`, `status_code`, `latency_ms`
- 評価用の正解ラベルを同じ行に付与する: `label`(`normal` / `noise` / `anomaly`)、`anomaly_type`
  (`None` / `isolated_latency_blip` / `latency_spike` / `error_spike`)
- 生成は `numpy.random.default_rng(seed)` によるベクトル化処理を基本とし、行単位のPython forループは避ける
- 期間は `days: int`(7/14/30)で指定し、CLI(`python -m log_anomaly_detection_poc.log_generator --days 7`)
  からも生成できるようにする
- 出力はCSV。生成データ自体は`.gitignore`対象にし、生成スクリプト・テストのみリポジトリ管理する

## 生成する3パターン

1. **正常 (normal)**: 時間帯(業務時間9-19時で高、夜間・週末で低)に応じたトラフィック量、
   エンドポイントごとの基準レイテンシ分布(対数正規)、低い基準エラー率
2. **ノイズ (noise, `isolated_latency_blip`)**: ごく低確率で単発リクエストのレイテンシのみが
   突発的に上昇する。持続しないため「異常」ではなく「ただのノイズ」として扱う
3. **異常 (anomaly)**:
   - `latency_spike`: 特定エンドポイントで30〜60分間、レイテンシが基準の数倍に持続的に上昇
   - `error_spike`: 15〜45分間、エラー率が持続的に急増(5xxが多発)
   - 週データごとに各異常イベントを最低1回注入し、Step4の評価でprecision/recallが計算できる
     十分な陽性サンプル数を確保する

## テスト方針

- 正常系: `days=7/14/30`それぞれで生成し、件数・カラム構成・値域(status_code, latency_ms>0)を検証
- エッジケース: `days=0`で空(または最小)の結果になること、seed固定で再現可能であること
- ラベル分布: `anomaly`・`noise`が0件にならないこと、`normal`が大多数であること
- 境界値: 異常注入ウィンドウの開始・終了時刻の境界でラベルが正しく切り替わること
