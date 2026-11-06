# onboarding-agent-v3

## 前提条件

- Azure CLIで対象テナントとサブスクリプションへサインイン済みであること
- Azure Developer CLIとFoundry Agents拡張がインストール済みであること
- `rg-foundry-book / mf-foundry-book / first-project` を利用できること
- `srch-foundry-book` の `onboarding-knowledgebase` を利用できること

認証にはMicrosoft Entra IDを使用します。APIキーやクライアントシークレットは使用しません。

## Retrieval

[retrieval.py](src/retrieval.py) は、Azure公式の Azure AI Search SDK
（`azure-search-documents==12.1.0b2`）の非同期 `KnowledgeBaseRetrievalClient` を使って
既存のFoundry IQ Knowledge Baseを検索します。`2026-08-01-preview` と現在の検索条件に
対応するため、SDKはプレビュー版に固定しています。

`DefaultAzureCredential` をSDKへ渡し、トークン取得とBearer認証はSDKに任せます。
推論強度 `low`、最大5文書、引用された参照元のタイトル・本文の抽出、
`query` / `answer` / `sources` / `raw_response` の戻り値形式は維持します。
接続・読み取りタイムアウトは120秒、自動リトライは従来どおり無効です。
HTTPエラーは `azure.core.exceptions.HttpResponseError`（またはそのサブクラス）として
呼び出し元へ伝播します。`httpx` はホストのテスト用であり、Retrievalには使用しません。

## 依存関係とテスト

リポジトリのルートで実行します。

```bash
uv sync --locked --project apps/agent_v3
uv run --locked --project apps/agent_v3 \
  python -m pytest --import-mode=importlib apps/agent_v3/tests -q
```

## Memory Storeの準備

Memory Storeが存在しない場合だけ、リポジトリのルートで次を実行します。

```bash
FOUNDRY_PROJECT_ENDPOINT="https://mf-foundry-book.services.ai.azure.com/api/projects/first-project" \
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.6-luna" \
AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME="text-embedding-3-large" \
FOUNDRY_MEMORY_STORE_NAME="onboarding-agent-memory-5-6-luna" \
uv run --locked --project apps/agent_v3 \
  python apps/agent_v3/src/main.py --provision-memory
```

## Hosted Agentへのデプロイ

デプロイ定義は、このディレクトリの [azure.yaml](azure.yaml) です。

初回だけ、リポジトリのルートから次を実行してazd環境を作成します。

```bash
cd apps/agent_v3

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
PROJECT_ENDPOINT="https://mf-foundry-book.services.ai.azure.com/api/projects/first-project"
PROJECT_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/rg-foundry-book/providers/Microsoft.CognitiveServices/accounts/mf-foundry-book/projects/first-project"

azd env new foundry-book \
  --subscription "${SUBSCRIPTION_ID}" \
  --location japaneast
azd env set AZURE_AI_PROJECT_ID "${PROJECT_ID}"
azd env set FOUNDRY_PROJECT_ENDPOINT "${PROJECT_ENDPOINT}"
```

デプロイと動作確認は、`apps/agent_v3` ディレクトリで実行します。

```bash
azd env select foundry-book
azd deploy onboarding-agent-v3 --no-prompt
azd ai agent show onboarding-agent-v3 --output json
```

初回デプロイ後、新しく作成されたmanaged identityへ必要なロールを付与します。

```bash
SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
PROJECT_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/rg-foundry-book/providers/Microsoft.CognitiveServices/accounts/mf-foundry-book/projects/first-project"
AGENT_PRINCIPAL_ID="$(azd env get-value AGENT_ONBOARDING_AGENT_V3_INSTANCE_IDENTITY_PRINCIPAL_ID)"
SEARCH_SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/rg-foundry-book/providers/Microsoft.Search/searchServices/srch-foundry-book"

az role assignment create \
  --assignee-object-id "${AGENT_PRINCIPAL_ID}" \
  --assignee-principal-type ServicePrincipal \
  --role "Search Index Data Reader" \
  --scope "${SEARCH_SCOPE}"
az role assignment create \
  --assignee-object-id "${AGENT_PRINCIPAL_ID}" \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope "${PROJECT_ID}"
az role assignment create \
  --assignee-object-id "${AGENT_PRINCIPAL_ID}" \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" \
  --scope "${PROJECT_ID}"
```

権限反映後に動作確認します。

```bash
azd ai agent invoke onboarding-agent-v3 \
  --new-session \
  --new-conversation \
  "バディの役割を簡潔に教えてください。"
```

既存Foundry projectへcode deployするため、`azd provision` は実行しません。
