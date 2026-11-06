# Devagent Runtimeへ段階的にデプロイする

Runtimeでは、SourceNest Pipelineまたは承認済みStudioバージョンから作成された不変の成果物をデプロイします。ローカル端末で再ビルドした成果物をProductionへ直接送信しません。

## デプロイ前

- 対象成果物のコミット、評価結果、承認が確認できる。
- Stagingで統合試験が成功している。
- 設定差分、接続、シークレット参照を確認している。
- 監視、停止条件、ロールバック先を決めている。
- 高リスク変更ではLaunchPadまたは変更レコードの承認がある。

## 新しいデプロイ

1. https://runtime.devagent.example の「Deployments」で「New Deployment」を選びます。
2. Serviceを選びます。サービス名と顧客またはプロジェクトを照合します。
3. Environmentを選びます。Productionを選んだ場合は環境バッジを再確認します。
4. Artifact versionを選び、コミットSHAと評価結果を開いて確認します。
5. Configuration setを選び、現在版との差分を表示します。シークレットは値ではなく参照先だけを確認します。
6. Traffic strategyを選びます。Productionの標準はCanaryです。
7. 最初のトラフィックを5%、観測時間を30分に設定します。案件のリスクに応じて変更します。
8. Rollback versionに直前のHealthyバージョンを指定します。
9. 「差分を確認」と「評価を確認」を選びます。
10. 確認者と停止条件を入力し、「デプロイ」を選びます。

## 段階的に増やす

Deployment詳細で状態がHealthyになった後、Error rate、P95 latency、Evaluation score、Human intervention、顧客の業務指標を確認します。

標準例は5%から25%、50%、100%です。各段階で観測時間を設けます。技術指標が正常でも、誤回答や業務上の失敗が増えた場合は進めません。

## 完了確認

100%へ移行後も標準30分は観測します。Deployment詳細で状態、トラフィック、バージョン、監査記録を確認します。LaunchPadまたは変更レコードへ、開始・完了時刻、最終バージョン、観測結果を記録します。

QueuedやDeployingのまま進まない場合は重複デプロイを作らず、Deployment詳細のイベントとPipelineを確認します。