# 16: azdによるremote_buildソースコードデプロイ

この例では、PythonソースコードをZIPとしてリモートビルドするHosted Agentをデプロイします。
コンテナーイメージの作成やContainer Registryへのpushは行いません。
azdがソースをZIP化し、Foundry Agent Serviceが `pyproject.toml` と `uv.lock` を使って
依存関係をインストールします。

## ファイル構成

```text
16_deploy_hosted_agent_azd/
├── README.md
├── azure.yaml
└── src/
    ├── main.py
    ├── pyproject.toml
    ├── uv.lock
    └── uv.toml
```

[azure.yaml](azure.yaml) にAgent設定、[src/](src/) に実行ソースと依存関係を同梱しています。
`codeConfiguration.dependencyResolution: remote_build` がリモートでの依存解決を指定します。
ファイルを新規作成したり、他のサンプルからコピーしたりする必要はありません。

## 前提条件

- Azure CLI、Azure Developer CLI（azd）、`azure.ai.agents` 拡張（1.0.0-beta.4以上）
- 既存のFoundry projectと、そこで利用可能な `gpt-5.4` モデルデプロイ
- 既存projectにHosted Agentをデプロイ・呼び出しできる権限

別のモデルを利用する場合は、[azure.yaml](azure.yaml) の
`AZURE_AI_MODEL_DEPLOYMENT_NAME` を変更してください。
既存projectを利用するため、`azd provision` は実行しません。

## 認証とazd環境の設定

以降は、このディレクトリをカレントディレクトリにして実行します。
すでにこのディレクトリ内にいる場合は、`cd` は不要です。
プレースホルダーを使用するFoundry projectの値に置き換えます。

```bash
cd 16_deploy_hosted_agent_azd
az login
azd auth login

azd env new foundry-book \
  --subscription "<subscription-id>" \
  --location "<location>"
azd env set AZURE_AI_PROJECT_ID "<project-resource-id>"
azd env set FOUNDRY_PROJECT_ENDPOINT "<project-endpoint>"
```

## デプロイ

```bash
azd deploy hosted-agent-azd-sample --no-prompt
azd ai agent show hosted-agent-azd-sample --output json
azd ai agent invoke hosted-agent-azd-sample \
  --new-session \
  --new-conversation \
  "オンボーディングのチェックリストを1文で説明してください。"
```
