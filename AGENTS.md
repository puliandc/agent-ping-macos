# AgentPing

macOS 本地任务提醒。默认使用简体中文。

- 脚本原型与原生应用共用 `Sources/main.swift`，不要复制两套窗口逻辑。
- 收到事件时使用不激活应用的 NSPanel；不得自动调用 activate、抢键盘焦点或操作来源应用。
- 默认无声音、不开机自启。DSH 和 Codex 的接入安装应保留既有 hook，并支持撤销。
- 明确区分 `turn-complete`（一轮结束）和 `done`（来源明确报告任务完成）。
- 只接受本地文件队列。不得加入外网监听、凭据、聊天原文采集或自动批准操作。
- UI 测试只使用明确标记的测试事件，不把测试结果描述为真实来源端到端验证。
- 提交前运行 `python3 -m unittest discover -s tests -v`、`scripts/build` 和 `git diff --check`。
- 实际全屏与焦点行为需要界面观察；无法观察时明确记录待验，不凭编译通过宣称效果通过。
