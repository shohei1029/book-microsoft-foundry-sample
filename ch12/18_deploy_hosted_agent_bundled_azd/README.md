# 18: azdによるbundledソースコードデプロイ

この例では、Python依存関係をローカルでLinux互換の `packages/` へ展開し、
ソースコードと一緒にZIPデプロイします。Foundry Agent Serviceは依存関係を再解決せず、
アップロードされたZIPをそのまま実行します。

`bundled` はコンテナーイメージのビルド方式ではありません。DockerfileとACRは不要です。

## ファイル構成

```text
18_deploy_hosted_agent_bundled_azd/
├── README.md
├── azure.yaml
└── src/
    ├── main.py
    ├── pyproject.toml
    ├── uv.lock
    ├── uv.toml
    └── packages/  （以下の手順で生成）
```

[azure.yaml](azure.yaml) にAgent設定、[src/](src/) に実行ソースと依存関係を同梱しています。
`codeConfiguration.dependencyResolution: bundled` が展開済み依存関係の利用を指定します。
他のサンプルからファイルをコピーする必要はありません。

## 前提条件

- Azure CLI、Azure Developer CLI（azd）、`azure.ai.agents` 拡張（1.0.0-beta.4以上）
- uv（コンテナーで依存関係を展開する場合はDockerも必要）
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
cd 18_deploy_hosted_agent_bundled_azd
az login
azd auth login

azd env new foundry-book \
  --subscription "<subscription-id>" \
  --location "<location>"
azd env set AZURE_AI_PROJECT_ID "<project-resource-id>"
azd env set FOUNDRY_PROJECT_ENDPOINT "<project-endpoint>"
```

## Linux互換依存関係の準備

Python 3.13 / Linux x86_64で動作するwheelを `packages/` へ展開します。
wheelファイルを置くだけではなく、`--target` でモジュールを展開してください。
再生成する場合は、先に既存の `src/packages/` を削除します。

```bash
cd src
uv export \
  --locked \
  --no-dev \
  --no-emit-project \
  --format requirements.txt \
  --output-file requirements.lock
uv pip install \
  --requirements requirements.lock \
  --target packages \
  --python-platform x86_64-manylinux2014 \
  --python-version 3.13 \
  --only-binary :all:
cd ..
```

クロスプラットフォーム解決が難しい場合は、上のコマンドの代わりに
uv入りのLinuxコンテナーで同じ処理を実行します。実行後はディレクトリのルートに戻ります。

```bash
cd src
docker run --rm \
  --platform linux/amd64 \
  --volume "$PWD:/work" \
  --workdir /work \
  ghcr.io/astral-sh/uv:0.12.19 \
  sh -c 'uv export --locked --no-dev --no-emit-project --format requirements.txt --output-file requirements.lock &&
         uv pip install --requirements requirements.lock --target packages --python-version 3.13 --only-binary :all:'
cd ..
```

## デプロイ

```bash
azd deploy hosted-agent-bundled-azd --no-prompt
azd ai agent show hosted-agent-bundled-azd --output json
azd ai agent invoke hosted-agent-bundled-azd \
  --new-session \
  --new-conversation \
  "オンボーディングのチェックリストを1文で説明してください。"
```
