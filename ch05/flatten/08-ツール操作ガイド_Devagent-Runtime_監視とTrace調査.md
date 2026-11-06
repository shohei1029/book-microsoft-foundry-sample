# Devagent Runtimeの監視とTrace調査

Observabilityでは、サービス全体の傾向から一件のTraceへ絞り込みます。最初から個別ログだけを読み、全体影響を見落とさないようにします。

![Devagent RuntimeのObservability画面。要求数、エラー率、遅延、評価スコアとトレースを確認する。](assets_runtime-observability.svg)

## 画面の見方

1. **対象と操作**: Service、Production環境、状態、ロールバック操作を確認します。
2. **主要指標**: Requests、Error rate、P95 latency、Tokens、Eval score、Human interventionを同じ期間で比較します。
3. **Trace**: 失敗または遅い一件を開き、モデル・Tool・分岐のどこで問題が起きたか確認します。

## 調査の順番

1. ServiceとEnvironmentが依頼対象と一致することを確認します。
2. 期間を「過去60分」など問題が起きた範囲に設定します。
3. Versionで全版と現在版を比較します。デプロイ直後から変化したか確認します。
4. Requestsの変化を確認します。負荷増加か、同じ負荷での品質劣化かを分けます。
5. Error rateとP95 latencyを確認します。平均値だけでなく上位遅延を見ます。
6. Evaluation scoreとHuman interventionを確認し、技術成功でも品質が下がっていないか確認します。
7. グラフ上の変化時刻をデプロイ、接続変更、外部システム障害と照合します。
8. Recent tracesをStatusまたはLatencyで絞ります。
9. Traceを開き、Input、Model call、Tool call、Retry、Outputの順に確認します。

## Traceで記録すること

- Trace IDと発生時刻
- バージョンと環境
- 最初に失敗したSpan
- 外部依存先と応答状態
- 再試行、Fallback、人への引き継ぎ結果
- 顧客影響の有無

ログ本文をHelpPortやRelayへ貼り付ける前に、顧客情報と個人情報を確認します。共有にはTrace IDと必要な抜粋を使います。

## エスカレーション

広い利用者影響、継続するSLO違反、データ漏えいの疑いがあれば、調査完了を待たず対応を上げます。製品障害は `#runtime-status`、セキュリティはGuardLineです。次回更新時刻を決め、事実と仮説を分けて共有します。