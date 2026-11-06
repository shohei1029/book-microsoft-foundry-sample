# 21: azdによる完成済みコンテナーイメージのデプロイ

この例では、コンテナーイメージのbuild、scan、sign、ACRへのpushを事前に完了させ、
azdには完成済みimageだけを渡します。azdはDockerfileをビルドしません。

## ファイル構成

```text
21_deploy_hosted_agent_prebuilt_container_azd/
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
[src/Dockerfile](src/Dockerfile) に事前ビルド用の手順を同梱しています。
他のサンプルからファイルをコピーする必要はありません。

`image` を指定するとazdはDockerfileのbuildをスキップします。デプロイ時にazdが
イメージをAgent用repositoryへtag・publishする場合がありますが、Dockerfileからの再buildは行いません。

## 前提条件

- Azure CLI、Azure Developer CLI（azd）、`azure.ai.agents` 拡張（1.0.0-beta.4以上）
- Dockerと、動作中のDocker daemon（完成済みimageがある場合は事前ビルド不要）
- 既存のFoundry projectと、そこで利用可能な `gpt-5.4` モデルデプロイ
- 既存のACRと、既存projectにHosted Agentをデプロイ・呼び出しできる権限

イメージのpush・publishには通常ACRの `AcrPush`、ABACモードのACRでは対象repositoryの
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
cd 21_deploy_hosted_agent_prebuilt_container_azd
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

## ローカルビルドとACRへのpush

Hosted Agent用のイメージは `linux/amd64` でビルドします。
完成済みimageを利用する場合は、この手順をスキップしてください。
本番用途で必要なscan・signは、利用環境のポリシーに従って別途実施します。

```bash
IMAGE_REPOSITORY="agents/hosted-agent-prebuilt"
IMAGE_TAG="v1"
IMAGE="${LOGIN_SERVER}/${IMAGE_REPOSITORY}:${IMAGE_TAG}"

az acr login --name "${ACR_NAME}"
docker build \
  --platform linux/amd64 \
  --tag "${IMAGE}" \
  src
docker push "${IMAGE}"
printf '%s\n' "${IMAGE}"
```

表示されたimageの値（完成済みimageを利用する場合はその参照）を、
[azure.yaml](azure.yaml) の `<container-image>` に直接記載します。
本番用途では、更新可能なtagではなく `@sha256:...` digestでimageを固定してください。

## デプロイ

```bash
azd deploy hosted-agent-prebuilt-container --no-prompt
azd ai agent show hosted-agent-prebuilt-container --output json
azd ai agent invoke hosted-agent-prebuilt-container \
  --new-session \
  --new-conversation \
  "オンボーディングのチェックリストを1文で説明してください。"
```
