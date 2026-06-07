---
name: interest-profile
description: "Use when the user asks to sync, update, show, or inspect an interest profile from Codex conversation history, with phrases like /interest-profile sync, /interest-profile show, プロファイル更新, 興味プロファイル, or 興味を見せて."
---

# Interest Profile

Build and maintain a personal interest profile from Codex conversation history. This skill only extracts, stores, and summarizes interest signals from conversation logs.

Data stays local to the project:

- `INTERESTS.md` stores the generated profile.
- `data/interests/interest-log.jsonl` stores accumulated interest signals.
- `data/interests/last-sync.json` stores the sync cursor.

## Modes

- **sync**: Run when the user asks to sync, update, or refresh the profile.
- **show**: Run when the user asks to show, display, or inspect the profile.

For scheduled or automatic runs, do not ask the user questions. Run the workflow autonomously, log recoverable errors, and continue when possible.

## Sync Workflow

1. Extract new Codex user messages:

```bash
python3 .codex/skills/interest-profile/scripts/extract_interests.py \
  --state-file "data/interests/last-sync.json" \
  --state-out "data/interests/last-sync.json.pending" \
  --max-messages 500
```

If no messages are returned, commit the pending state and report that no new signals were found.

2. Load recent accumulated signals only:

```bash
python3 .codex/skills/interest-profile/scripts/extract_interests.py \
  --recent-log "data/interests/interest-log.jsonl" \
  --recent-days 90
```

3. Classify new messages into interest signals. Exclude pure operational noise such as commit requests, file operations, permission changes, tool output, one-word replies, and skill invocation with no substantive comment.

Use this JSONL shape for each signal:

```json
{"ts":"<ISO8601>","session_id":"<session id>","source":"codex-conversation","category":"<category>","intensity":1,"topic":"<Japanese topic, <=20 chars>","keywords":["lowercase","english"],"raw_excerpt":"<first 200 chars>"}
```

Categories:

- `question`: questions or requests for explanation, intensity 1-2.
- `deep-dive`: three or more same-topic questions in one session, intensity 3.
- `creation-intent`: wants to build, try, write, design, or implement something, intensity 3.
- `topic-exploration`: comparison, exploration, or reflective discussion, intensity 1-2.
- `opinion`: clear preference or evaluation, intensity 2.

4. Generate `INTERESTS.md` from recent signals plus new signals. Write natural Japanese prose, not tables. Keep it under 80 lines.

Use this structure:

```markdown
---
last_updated: "{YYYY-MM-DD}"
signals_total: {total}
---

# 興味プロファイル

## この人について

## 今の関心（直近14日）

## 継続的な関心

## 新規探索のヒント
```

Score topics by summing `intensity * time_weight`:

- Last 14 days: `1.0`
- 15-30 days: `0.5`
- Older than 30 days: `0.25`

5. Commit state in this order:

- Append new, de-duplicated signals to `data/interests/interest-log.jsonl`. Before appending, skip signals whose `ts` and `raw_excerpt` match an existing line.
- Promote pending state:

```bash
python3 .codex/skills/interest-profile/scripts/extract_interests.py \
  --state-file "data/interests/last-sync.json" \
  --commit "data/interests/last-sync.json.pending"
```

Then report:

```text
興味プロファイルを更新しました。
- 新規メッセージ: {N}件分析
- 新規シグナル: {M}件検出
- 保存先: INTERESTS.md
```

## Show Workflow

Read and display `INTERESTS.md`. If it does not exist, say:

```text
まだプロファイルが生成されていません。`/interest-profile sync` を実行してください。
```
