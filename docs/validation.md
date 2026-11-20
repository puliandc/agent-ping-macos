# Validation / 验证步骤

## Automated checks / 自动检查

```sh
scripts/build
python3 -m unittest discover -s tests -v
node --test tests/dsh-plugin.test.mjs
git diff --check
```

Build first so the Python suite can validate the native event reader.
先构建，再运行 Python 测试，以便覆盖原生事件读取。

## Display and focus / 窗口与焦点

- Run `bin/agent-ping demo --source Codex --delay 8`. Switch to the app or full-screen Space you want to check before the alert appears. Confirm that the alert is visible and the current app retains keyboard focus.
- Click the confirmation button. Check that Codex opens or comes forward and the alert closes. With multiple displays, check that confirming on one screen closes the other copies.

中文步骤：

1. 运行 `bin/agent-ping demo --source Codex --delay 8`。在提醒出现前切换到要测试的应用或全屏空间，确认弹窗可见，当前应用仍保有键盘焦点。
2. 点击「确定」，确认 Codex 打开或切到前台，且浮窗关闭。如果连接了多个显示器，确认其他屏幕上的同一条浮窗也已关闭。

## Live delivery / 真实事件投递

After configuring the integrations, check turn completion, questions, and approval requests from the clients you use. Confirm an alert for each event and handle the interaction in the originating client. The demo only exercises the display path.

配置接入后，在实际使用的客户端中检查回合结束、提问和审批请求。确认每类事件都有提醒，并在来源客户端处理交互。演示命令只验证显示链路。
