# 20: azdによるローカルDockerビルド

この例では、`azd deploy` がローカルDocker daemonを使って
`linux/amd64`イメージをビルドします。azdはビルド後のイメージを既存ACRへpushし、
Hosted Agent versionを作成します。

## ファイル構成

```text
20_deploy_hosted_agent_local_container_azd/
├── README.md
├── azure.yaml
└── src/
    ├── Dockerfile
    ├── main.py
    ├── pyproject.toml
    ├── uv.lock
    └── uv.toml
```

[azure.yaml](azure.yaml) にAgent設定、[src/](src/) に実行ソースと依存関係、
[src/Dockerfile](src/Dockerfile) にビルド手順を同梱しています。
他のサンプルからファイルをコピーする必要はありません。

`docker.remoteBuild: false` が、azd自身によるローカルDockerビルドを指定します。
これはZIPデプロイの `dependencyResolution: remote_build` とは別の設定です。

## 前提条件

- Azure CLI、Azure Developer CLI（azd）、`azure.ai.agents` 拡張（1.0.0-beta.4以上）
- Dockerと、動作中のローカルDocker daemon
- 既存のFoundry projectと、そこで利用可能な `gpt-5.4` モデルデプロイ
- 既存のACRと、既存projectにHosted Agentをデプロイ・呼び出しできる権限

デプロイ実行者には通常ACRの `AcrPush`、ABACモードのACRでは対象repositoryの
`Container Registry Repository Writer` が必要です。
azdがAgent専用identityにpull権限を割り当てられる権限も必要です。
別のモデルを利用する場合は、[azure.yaml](azure.yaml) の
`AZURE_AI_MODEL_DEPLOYMENT_NAME` を変更してください。
既存projectとACRを利用するため、`azd provision` は実行しません。

## 認証とazd環境の設定

以降は、このディレクトリをカレントディレクトリにして実行します。
すでにこのディレクトリ内にいる場合は、`cd` は不要です。
プレースホルダーを使用するFoundry projectとACRの値に置き換えます。

```bash
cd 20_deploy_hosted_agent_local_container_azd
az login
azd auth login
az account set --subscription "<subscription-id>"

azd env new foundry-book \
  --subscription "<subscription-id>" \
  --location "<location>"
azd env set AZURE_AI_PROJECT_ID "<project-resource-id>"
azd env set FOUNDRY_PROJECT_ENDPOINT "<project-endpoint>"

ACR_NAME="<acr-name>"
LOGIN_SERVER="$(az acr show --name "${ACR_NAME}" --query loginServer -o tsv)"
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT "${LOGIN_SERVER}"
```

## デプロイ

```bash
docker version
azd deploy hosted-agent-local-container --no-prompt
azd ai agent show hosted-agent-local-container --output json
azd ai agent invoke hosted-agent-local-container \
  --new-session \
  --new-conversation \
  "オンボーディングのチェックリストを1文で説明してください。"
```

azdはAgent専用identityへ、通常ACRでは `AcrPull`、ABACモードでは
`Container Registry Repository Reader` を割り当てます。
