#!/usr/bin/env python3
"""
Extract unprocessed user messages from Codex session JSONL files.

The extractor uses a two-phase cursor update:

1. Extraction writes messages to stdout and the next cursor to --state-out.
2. Commit promotes --commit to --state-file after downstream work succeeds.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

NOISE_PREFIXES = (
    "<environment_context>",
    "<permissions instructions>",
    "<app-context>",
    "<collaboration_mode>",
    "<skills_instructions>",
    "<plugins_instructions>",
    "<scheduled-task",
    "<local-command",
    "<command-message",
    "<task-notification",
    "<command-name>",
)

MIN_LENGTH = 20


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def default_logs_dir() -> Path:
    return codex_home() / "sessions"


def normalize_text_blocks(content) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in {"input_text", "text"} and isinstance(block.get("text"), str):
                texts.append(block["text"])
        return "\n".join(texts) if texts else None
    return None


def extract_user_text(obj: dict) -> str | None:
    if obj.get("type") != "response_item":
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "message" or payload.get("role") != "user":
        return None
    return normalize_text_blocks(payload.get("content"))


def extract_session_cwd(obj: dict) -> str | None:
    if obj.get("type") != "session_meta":
        return None
    payload = obj.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("cwd"), str):
        return payload["cwd"]
    return None


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            with open(state_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: state file unreadable, starting fresh: {e}", file=sys.stderr)
    return {"last_sync_at": None, "sessions": {}}


def save_state(state_file: Path, state: dict):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_suffix(state_file.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, state_file)


def should_keep_text(text: str) -> bool:
    stripped = text.lstrip()
    if len(stripped) <= MIN_LENGTH:
        return False
    return not any(stripped.startswith(prefix) for prefix in NOISE_PREFIXES)


def extract_from_session(filepath: Path, project_cwd: str | None, skip_lines: int = 0):
    messages = []
    lines_total = 0
    session_cwd = None
    session_matches_project = project_cwd is None

    with open(filepath, encoding="utf-8") as f:
        for i, line in enumerate(f):
            lines_total = i + 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if session_cwd is None:
                session_cwd = extract_session_cwd(obj)
                if session_cwd is not None and project_cwd is not None:
                    session_matches_project = os.path.abspath(session_cwd) == project_cwd

            if i < skip_lines:
                continue
            if not session_matches_project:
                continue

            content = extract_user_text(obj)
            if content is None or not should_keep_text(content):
                continue

            messages.append({
                "ts": obj.get("timestamp", ""),
                "session_id": session_id_for_path(filepath),
                "content": content[:2000],
            })

    return messages, lines_total


def session_id_for_path(filepath: Path) -> str:
    match = re.search(r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$", filepath.stem)
    return match.group(1) if match else filepath.stem


def read_recent_log(log_file: Path, days: int):
    if not log_file.exists():
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = 0
    with open(log_file, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                ts = json.loads(line).get("ts", "")
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            except (json.JSONDecodeError, ValueError, AttributeError):
                pass
            print(line)
            kept += 1
    print(f"--- Loaded {kept} signals from last {days} days ---", file=sys.stderr)


def commit_state(state_file: Path, pending_file: Path):
    if not pending_file.exists():
        print(f"ERROR: pending file not found: {pending_file}", file=sys.stderr)
        sys.exit(1)
    with open(pending_file, encoding="utf-8") as f:
        state = json.load(f)
    save_state(state_file, state)
    pending_file.unlink()
    print(f"--- Committed state to {state_file} ---", file=sys.stderr)


def iter_session_files(logs_dir: Path):
    return sorted(logs_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(description="Extract user messages from Codex session logs")
    parser.add_argument("--logs-dir", help="Codex sessions directory. Defaults to $CODEX_HOME/sessions or ~/.codex/sessions.")
    parser.add_argument("--state-file", help="Path to last-sync.json state file.")
    parser.add_argument("--state-out", help="Pending state output path for extraction phase.")
    parser.add_argument("--commit", help="Promote pending state to --state-file.")
    parser.add_argument("--recent-log", help="Print recent interest-log.jsonl lines for profile generation.")
    parser.add_argument("--recent-days", type=int, default=90, help="Days to load with --recent-log.")
    parser.add_argument("--max-messages", type=int, default=500, help="Extraction soft cap; 0 or less means unlimited.")
    parser.add_argument("--all-codex-sessions", action="store_true", help="Include sessions from every cwd, not just the current project.")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.recent_log:
        read_recent_log(Path(args.recent_log), args.recent_days)
        return

    if not args.state_file:
        parser.error("--state-file is required unless --recent-log is given")
    state_file = Path(args.state_file)

    if args.commit:
        commit_state(state_file, Path(args.commit))
        return

    logs_dir = Path(args.logs_dir).expanduser() if args.logs_dir else default_logs_dir()
    if not logs_dir.exists():
        print(f"ERROR: logs dir not found: {logs_dir}", file=sys.stderr)
        sys.exit(1)

    project_cwd = None if args.all_codex_sessions else os.path.abspath(os.getcwd())
    state = load_state(state_file)
    sessions_state = state.get("sessions", {})
    new_state = dict(sessions_state)
    all_messages = []
    changed_sessions = 0

    for filepath in iter_session_files(logs_dir):
        key = str(filepath)
        current_mtime = filepath.stat().st_mtime
        prev = sessions_state.get(key, {})
        prev_mtime = prev.get("mtime", 0)
        prev_lines = prev.get("lines_read", 0)

        if current_mtime <= prev_mtime:
            new_state[key] = prev
            continue

        messages, total_lines = extract_from_session(filepath, project_cwd, skip_lines=prev_lines)
        if total_lines < prev_lines:
            messages, total_lines = extract_from_session(filepath, project_cwd, skip_lines=0)
        all_messages.extend(messages)

        new_state[key] = {
            "mtime": current_mtime,
            "lines_read": total_lines,
        }
        changed_sessions += 1

        if args.max_messages > 0 and len(all_messages) >= args.max_messages:
            break

    json.dump(all_messages, sys.stdout, ensure_ascii=False, indent=2)

    if args.state_out:
        state["last_sync_at"] = datetime.now().astimezone().isoformat()
        state["sessions"] = new_state
        save_state(Path(args.state_out), state)

    print(f"\n--- Extracted {len(all_messages)} messages from {changed_sessions} new/updated sessions ---", file=sys.stderr)


if __name__ == "__main__":
    main()
