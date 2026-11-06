# onboarding-agent-v1

## 前提条件

- Azure CLIで対象テナントとサブスクリプションへサインイン済みであること
- Azure Developer CLIとFoundry Agents拡張がインストール済みであること
- `rg-foundry-book / mf-foundry-book / first-project` を利用できること
- 既存の `onbording-search-agent` version `2` を利用できること

認証にはMicrosoft Entra IDを使用します。APIキーやクライアントシークレットは使用しません。

## 依存関係とテスト

リポジトリのルートで実行します。

```bash
uv sync --locked --project apps/agent_v1
uv run --locked --project apps/agent_v1 \
  python -m pytest --import-mode=importlib apps/agent_v1/tests -q
```

## Hosted Agentへのデプロイ

デプロイ定義は、このディレクトリの [azure.yaml](azure.yaml) です。

初回だけ、リポジトリのルートから次を実行してazd環境を作成します。

```bash
cd apps/agent_v1

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
PROJECT_ENDPOINT="https://mf-foundry-book.services.ai.azure.com/api/projects/first-project"
PROJECT_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/rg-foundry-book/providers/Microsoft.CognitiveServices/accounts/mf-foundry-book/projects/first-project"

azd env new foundry-book \
  --subscription "${SUBSCRIPTION_ID}" \
  --location japaneast
azd env set AZURE_AI_PROJECT_ID "${PROJECT_ID}"
azd env set FOUNDRY_PROJECT_ENDPOINT "${PROJECT_ENDPOINT}"
```

デプロイと動作確認は、`apps/agent_v1` ディレクトリで実行します。

```bash
azd env select foundry-book
azd deploy onboarding-agent-v1 --no-prompt
azd ai agent show onboarding-agent-v1 --output json
azd ai agent invoke onboarding-agent-v1 \
  --new-session \
  --new-conversation \
  "入社初日に必要な手続きを3つ教えてください。"
```

既存Foundry projectへcode deployするため、`azd provision` は実行しません。
既存の `onbording-search-agent` は変更せずGPT-5.4のまま再利用します。
既存の `onbording-search-agent` は変更せずGPT-5.4のまま再利用します。
ReviewとFinalizeはGPT-5.6 LunaのResponses APIを使用します。
