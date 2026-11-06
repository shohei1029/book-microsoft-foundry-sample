# AgentWeaveのローカル環境を作って実行する

この手順ではAgentWeave CLI、Python 3.12、`uv`を使い、最小のAgent Projectを作成してローカルで実行します。顧客案件ではチームの既存テンプレートとREADMEを優先してください。

## 前提

- 会社管理端末を使用している。
- SourceNestへサインインできる。
- Python 3.12と`uv`がCompany Appsから導入済みである。
- GateOneの開発用モデル接続が付与されている。

バージョンを確認します。

```bash
python3 --version
uv --version
git --version
```

## プロジェクトを作成する

作業用ディレクトリで次を実行します。

```bash
mkdir delivery-faq-agent
cd delivery-faq-agent
uv init
uv add agentweave
uv run agentweave init --template minimal
```

初期化後、次のファイルがあることを確認します。

```text
delivery-faq-agent/
├── agentweave.yaml
├── src/
│   └── agent.py
├── tests/
├── evaluations/
│   └── smoke.yaml
├── .env.example
└── README.md
```

`.env.example`には変数名と説明だけを置き、認証情報や実際の値をコミットしません。ローカルの資格情報はGateOneと開発者向け安全保管機能を使います。

## 設定を検証する

```bash
uv run agentweave validate
```

終了コード`0`なら構成は有効です。`2`の場合は、`agentweave.yaml`の必須項目、ファイルパス、コマンド引数を確認します。`1`はConnectorの検証失敗など実行上の問題です。

## ローカルで実行する

```bash
uv run agentweave dev
```

標準では `http://127.0.0.1:4310` で開発UIとAPIが起動します。起動ログで次を確認します。

- 読み込んだAgent Projectのパス
- 使用するDevelopment接続
- `health: ready`
- シークレット値がログへ表示されていないこと

ブラウザーで開発UIを開き、合成データの質問を送ります。応答本文だけでなく、使用したTool、引用、実行時間を確認します。

## 停止と再開

実行したターミナルで`Ctrl+C`を押して停止します。停止後にプロセスが残っていないことを確認します。設定を変えたら`validate`を再実行してから起動します。

本番データをローカルへコピーしません。顧客固有の再現が必要な場合は、識別子と内容を合成データへ置き換えます。