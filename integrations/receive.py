#!/usr/bin/env python3
"""Lifecycle receiver. It never approves, blocks, or answers a source request."""
import argparse
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("agentping_sender", str(ROOT / "bin/agent-ping"))
spec = importlib.util.spec_from_loader(loader.name, loader)
sender = importlib.util.module_from_spec(spec)
loader.exec_module(sender)
QUESTION_TOOL = re.compile(r"(?:^|[._])(?:request_user_input(?:_async)?|ask_user_question)$")


def translate(source, payload):
    if not isinstance(payload, dict):
        raise ValueError("事件必须是 JSON 对象")
    event = payload.get("hook_event_name")
    session = str(payload.get("session_id", ""))
    turn = str(payload.get("turn_id", ""))
    if event in {"Ready", "UserPromptSubmit", "PostToolUse"}:
        return None
    if source == "codex":
        name = "Codex"
        if event == "Stop":
            kind, title, message = "turn-complete", "Codex 一轮回复已结束", "当前一轮处理已结束，请返回 Codex 查看结果。"
            identity = f"codex:stop:{session}:{turn}" if session and turn else None
        elif event == "PermissionRequest":
            kind, title, message = "question", "Codex 需要你批准操作", "有一项操作等待你批准。请返回 Codex 查看详情并作出决定。"
            identity = None  # This hook does not always include a unique call id.
        elif event == "PreToolUse" and QUESTION_TOOL.search(str(payload.get("tool_name", ""))):
            kind, title, message = "question", "Codex 有问题需要你回答", "Codex 正在等待你的回答或选择，请返回查看。"
            call = payload.get("tool_use_id")
            identity = f"codex:question:{session}:{turn}:{call}" if call else None
        else:
            return None
    elif source == "dsh":
        name = "DSH"
        identity = payload.get("event_id")
        if event == "TurnCompleted":
            kind, title, message = "turn-complete", "DSH 一轮任务处理已结束", "当前一轮处理已结束，请返回 DeepSeek Harness 查看结果。"
        elif event == "QuestionRequested":
            kind, title, message = "question", "DSH 有问题需要你回答", "DeepSeek Harness 正在等待你的回答或选择。"
        elif event == "ApprovalRequested":
            kind, title, message = "question", "DSH 需要你批准操作", "有一项操作等待你批准。请返回 DeepSeek Harness 查看详情并作出决定。"
        elif event == "TurnFailed":
            kind, title, message = "error", "DSH 本轮处理未完成", "当前一轮处理遇到错误，请返回 DeepSeek Harness 查看。"
        else:
            return None
    else:
        raise ValueError("只支持 Codex 和 DSH")
    return sender.make_event(kind, name, message, title=title, event_id=identity or str(uuid.uuid4()))


def record(source, trigger, event, queued):
    root = sender.data_root()
    sender.prepare_dirs(root)
    info = {"time": dt.datetime.now(dt.timezone.utc).isoformat(), "source": source,
            "trigger": trigger, "kind": event["kind"] if event else None, "queued": queued}
    # Intentionally exclude transcripts, prompts, tool arguments, paths, and answers.
    fd = os.open(root / "integrations.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as output:
        output.write(json.dumps(info, ensure_ascii=False) + "\n")
    status = root / "integrations"
    status.mkdir(mode=0o700, exist_ok=True)
    path = status / f"{source}.json"
    temp = status / f".{source}-{uuid.uuid4()}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(info, output, ensure_ascii=False)
    os.replace(temp, path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=["codex", "dsh"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    raw = sys.stdin.buffer.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("hook 载荷超过 1 MiB")
    payload = json.loads(raw)
    event = translate(args.source, payload)
    if args.dry_run:
        print(json.dumps(event, ensure_ascii=False))
        return 0
    queued = sender.enqueue(event, sender.data_root()) if event else False
    if event:
        sender.launch_app(sender.data_root())
    record(args.source, payload.get("hook_event_name"), event, queued)
    print("{}")  # Valid, neutral output for Codex Stop and permission hooks.
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # A reminder failure must never stop a task or change its approval result.
        print(f"AgentPing receiver: {type(error).__name__}", file=sys.stderr)
        print("{}")
        raise SystemExit(0)
