# book-azure-ai-foundry-sample
Azure AI Foundry書籍執筆用サンプルコード

## 環境構築

### 前提条件

- Python==3.12
- uv>=0.7.11 (https://docs.astral.sh/uv/#installation)
- Visual Studio Code

### VSCode拡張

.vscode/extensions.json を参照し、ワークスペース推奨の拡張をインストールしてください。

### パッケージインストール

```bash
uv sync
```

上記コマンドにより.venvディレクトリが作成される。以後、ターミナルを開き直せば自動で.venvがアクティベートされる。

.venvがアクティベートされていない場合、以下のコマンドでアクティベートしてください。

```bash
source .venv/bin/activate
```

### ノートブック用カーネルの準備

```bash
uv run ipykernel install --user --name=book-azure-ai-foundry-sample
```