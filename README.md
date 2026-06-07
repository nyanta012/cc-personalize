# cc-personalize

Codex / Claude Code の会話履歴から、ユーザーの興味や関心テーマを抽出し、ローカルに興味プロファイルを生成・更新するための個人用カスタマイズリポジトリです。

## 概要

このリポジトリには、会話ログから興味シグナルを抽出し、`INTERESTS.md` として要約する `interest-profile` スキルが含まれています。

主な用途:

- Codex / Claude Code との会話から関心テーマを記録する
- 最近の興味や継続的な関心を自然文で整理する
- 個人向けの作業支援・探索テーマのヒントを得る

## 構成

```text
.codex/skills/interest-profile/   # Codex 用スキル
.claude/skills/interest-profile/  # Claude Code 用スキル
data/interests/                   # 生成される興味シグナル・同期状態
INTERESTS.md                      # 生成される興味プロファイル
```

## 使い方

Codex で興味プロファイルを更新する場合:

```text
/interest-profile sync
```

または自然文で以下のように依頼します。

```text
興味プロファイルを更新して
```

現在のプロファイルを表示する場合:

```text
/interest-profile show
```

## 生成されるファイル

このリポジトリでは、以下のファイルが生成されます。

- `INTERESTS.md`: 興味プロファイルの要約
- `data/interests/interest-log.jsonl`: 抽出された興味シグナル
- `data/interests/last-sync.json`: 同期状態

これらは個人の会話内容や関心情報を含むため、`.gitignore` によりコミット対象から除外しています。

## プライバシー

このプロジェクトはローカルの会話履歴を扱います。生成物には個人的な関心、質問内容、会話の抜粋が含まれる可能性があります。

公開リポジトリにする場合は、`INTERESTS.md` や `data/interests/` を含めないでください。

## 開発メモ

興味抽出ロジックは以下にあります。

- `.codex/skills/interest-profile/scripts/extract_interests.py`
- `.claude/skills/interest-profile/scripts/extract_interests.py`

スキルの動作手順は各 `SKILL.md` に記述されています。
