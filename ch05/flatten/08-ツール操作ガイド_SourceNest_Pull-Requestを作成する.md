# SourceNestでPull Requestを作成する

SourceNestでは短命ブランチからPull Requestを作り、CIとレビューを通してメインブランチへ統合します。例ではAgentWeaveのリポジトリを使います。

## 作業を始める

1. SourceNestのリポジトリ画面で、README、CONTRIBUTING、CODEOWNERSを確認します。
2. 関連Issueを自分へ割り当て、完了条件を確認します。
3. ローカルのメインブランチを最新にします。

```bash
git switch main
git pull --ff-only
git switch -c fix/2841-tool-timeout
```

ブランチ名には変更種別とIssue番号または短い目的を含めます。顧客名や機密の案件名を入れません。

## 変更を確認する

チームのREADMEに記載されたテスト、型検査、lintを実行します。生成物やロックファイルが変わった場合は、意図した変更か確認します。

```bash
git status --short
git diff --check
git diff
```

シークレット、顧客データ、個人情報が差分にないことを確認します。

## Pull Requestを作る

1. ブランチをSourceNestへpushします。

```bash
git push -u origin fix/2841-tool-timeout
```

2. SourceNestの「Pull Requests」から「New Pull Request」を選びます。
3. Source branchとTarget branchを確認します。通常のTargetは `main` です。
4. タイトルを変更結果が分かる命令形で記載します。
5. Summaryに、問題、変更、対象外を記載します。
6. Validationに実行したテストと結果を記載します。
7. Riskに失敗時の利用者影響、Rollbackに戻し方を記載します。
8. 関連Issueとリリースノート要否を設定します。
9. 作業途中ならDraft、レビュー可能ならReady for reviewを選びます。

## 作成後

必須CIが開始されたこと、CODEOWNERSに基づくレビュアーが追加されたことを確認します。認証、権限、暗号、個人情報、課金の変更では領域オーナーが含まれていることを確認します。

自分で気付いた問題は、レビューを待たず修正します。修正push後に、変更内容と再実行した検証をコメントします。