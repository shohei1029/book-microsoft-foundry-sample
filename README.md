# 「AIエージェント開発基盤 - Microsoft Foundry -」サンプルコード

書籍「AIエージェント開発基盤 - Microsoft Foundry -」のハンズオンで使用するデータ、スクリプト、KQLクエリなどを公開しているリポジトリです。書籍の内容に沿ってご利用ください。

コードの不具合や不明な点がありましたら、[Issue](https://github.com/shohei1029/book-microsoft-foundry-sample/issues) やプルリクエストでお知らせいただけると幸いです。

> [!NOTE]
> 技術書典19で頒布された「AIエージェント開発基盤 - Azure AI Foundry -」のサンプルコードをご利用の方は、[shoten19](https://github.com/shohei1029/book-microsoft-foundry-sample/tree/shoten19) ブランチを参照してください。

## リポジトリの構成

書籍中のパスは、すべてこのリポジトリのルートからの相対パスで記載しています。

```text
.
├── data/
│   ├── ch-evaluations/        # 評価章で使用する検証用データ
│   └── ch-governance/         # ガバナンス章で使用する管理台帳テンプレート
├── kql/
│   ├── ch-evaluations/        # 評価章で使用するKQLクエリ
│   └── ch-observability/      # 可観測性章で使用するKQLクエリ
└── script/
    └── ch-evaluations/        # 評価章で使用するPythonスクリプト
```

## 章ごとのサンプル

### Foundry IQでナレッジを接続する（ナレッジの章）

ナレッジソースとして登録するオンボーディング資料（Markdown）は、別リポジトリ [ShuntaIto/on-boarding-agent-foundry](https://github.com/ShuntaIto/on-boarding-agent-foundry) の `markdown/flatten/` で公開しています。書籍の手順に沿ってZIP形式でダウンロードし、Blobコンテナーへアップロードしてください。

### エージェントの実装（Hosted Agent・サンプルユースケースの章）

Microsoft Agent Frameworkで実装したエージェント（`hosted-agent-azd-sample`、`onboarding-agent-v1`〜`v3` など）は、現在 [ShuntaIto/on-boarding-agent-foundry](https://github.com/ShuntaIto/on-boarding-agent-foundry) で公開しています。今後、本リポジトリへ移行する予定です。

### 評価（評価の章）

| ファイル | 内容 |
| --- | --- |
| `data/ch-evaluations/questions.jsonl` | 10分野・合計100件の検証用データ。`case_id`、`category`、`test_type`、`query`、`expected_behavior`、`source`、`evaluation_query` を持つ |
| `data/ch-evaluations/questions-smoke.jsonl` | 動作確認用の少数データ |
| `script/ch-evaluations/prepare_portal_dataset.py` | `questions.jsonl` をFoundry Portalへ登録する形式に変換するスクリプト（標準ライブラリのみで動作し、クラウドへの通信は発生しない） |
| `kql/ch-evaluations/export-stage-inputs.kql` | 同じ実行に属する内部3工程（回答案生成・レビュー・最終整形）の指示と入出力を取得するクエリ |
| `script/ch-evaluations/evaluate_stage.py` | 内部工程の評価データ作成（`prepare`）、ローカル検査（`check`）、評価ジョブ送信（`submit`）、結果取得（`results`）を行うスクリプト |
| `script/ch-evaluations/requirements.txt` | `evaluate_stage.py` で使用するSDKのバージョン指定 |

Portal登録用データへの変換（Linuxなどのシェルの場合）:

```bash
mkdir -p data/ch-evaluations/output
python script/ch-evaluations/prepare_portal_dataset.py \
  --input data/ch-evaluations/questions.jsonl \
  --output data/ch-evaluations/output/questions-portal-100.jsonl
```

内部工程の評価では、エージェント本体とは別の仮想環境を作成して依存パッケージをインストールします。コマンド例はWindowsのPowerShellを前提としています。詳しい手順は書籍を参照してください。

```powershell
python -m venv script/ch-evaluations/.venv
$python = ".\script\ch-evaluations\.venv\Scripts\python.exe"
& $python -m pip install -r script/ch-evaluations/requirements.txt
```

### 観測と監視（可観測性の章）

`kql/ch-observability/` に、Application Insightsの［ログ］で実行するクエリを用意しています。`<TRACE_ID>` などのプレースホルダーは、自分の環境の値に置き換えてください。

| ファイル | 内容 |
| --- | --- |
| `find-stage-spans.kql` | 内部3工程の実行とTrace IDを探す |
| `trace-spans.kql` | 選んだTrace IDに属するスパンを取得する |
| `model-usage.kql` | モデル呼び出しの入力・出力トークン数を取得する |
| `stage-latency.kql` | 内部工程の処理時間を5分ごとに集計する |
| `alert-stage-latency.kql` | 30秒を超えたスパンを検出するアラート用クエリ |

指示と入出力の書き出しには、評価の章と共通の `kql/ch-evaluations/export-stage-inputs.kql` を使用します。

### ガバナンス（ガバナンスの章）

`data/ch-governance/governance-register.csv` は、エージェント資産の管理台帳テンプレートです。作業用の `data/ch-governance/output/` へ複製してから編集してください。

## 出力フォルダーの取り扱い

`data/ch-evaluations/output/` と `data/ch-governance/output/` は、Gitの管理対象から除外しています。ただし、暗号化やアクセス制御が自動で設定されるわけではありません。トレースから書き出した内容や管理台帳には、プロンプトや組織の構成情報が含まれます。検証用のデータだけを扱い、作業後は保持方針に沿って整理してください。APIキーや接続文字列は記入しないでください。

## 前提条件

章によって必要な環境が異なります。詳しくは各章の前提条件を参照してください。

- Azureサブスクリプションと、Microsoft Foundryのプロジェクト
- Python 3.10以降（評価の章のスクリプト）
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)（評価の章のスクリプトは、Azure CLIの資格情報で認証します）
- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)（Hosted Agentのデプロイ）

## ライセンス

[MIT License](LICENSE)
