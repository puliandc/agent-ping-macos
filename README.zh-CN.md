# Agent Ping

[English](README.md)

Agent Ping 是一款 macOS 菜单栏应用。当本地 Agent 结束一轮处理、提出问题或等待审批时，它会显示持续保留的浮窗。项目自带 Codex 和 DeepSeek Harness（DSH）桌面版接入，其他工具可以通过命令行发送提醒。

浮窗可显示在全屏应用上方，弹出时保留当前应用的键盘焦点。点击「确定」可以打开任务链接或返回来源应用。请在来源应用里回答问题或处理审批。

## 快速开始

需要 macOS 13 或更新版本、Python 3.9 或更新版本，以及 Xcode Command Line Tools。在终端中运行以下命令。

```sh
git clone https://github.com/puliandc/agent-ping-macos.git
cd agent-ping-macos
scripts/build
bin/agent-ping start
bin/agent-ping demo --delay 8
```

构建后，`dist/AgentPing.app` 指向本机签名的应用。演示会在 8 秒后弹出测试提醒，方便你先切换到其他应用。运行 `bin/agent-ping status` 可以查看应用是否运行，以及还有几条提醒待处理。

## 接入 Codex 和 DSH

安装脚本会同时配置两种接入。运行前，确认 PATH 中有 `codex` 命令，并已初始化位于 `~/.dsh/profiles/desktop` 的 DSH 桌面配置。手动发送提醒无需安装这两种接入。

```sh
scripts/install-integrations
scripts/install-integrations --check
scripts/check-codex-hooks
```

1. 运行安装脚本添加接入。脚本会备份配置文件，并保留已有的 hook 和 Codex `notify` 设置。
2. 在 Codex 的 **Settings → Hooks** 或 CLI 的 **`/hooks`** 中，审阅并信任 Agent Ping 的三条 hook。它们对应 `Stop`、`PermissionRequest` 和 `PreToolUse`。
3. 用上面的两条检查命令核对配置和 hook 信任状态，再用平时使用的客户端运行一个简短任务，验证提醒能否送达。如果客户端仍沿用旧配置，可以在新会话中验证。

自动接入会提醒回合结束、等待回答和等待审批。DSH 还会报告回合失败。一轮处理结束时，整个任务可能仍在进行。调用方确认任务完成后，可以发送 `done`。

## 从其他工具发送提醒

可以在脚本末尾或 Agent 的生命周期回调中调用命令行发送器。

```sh
bin/agent-ping done --source "构建脚本" --message "构建完成。"
bin/agent-ping question --source "本地 Agent" --message "请选择下一步。" --app com.apple.Terminal
bin/agent-ping error --source "CI" --message "请检查失败的运行记录。" --url https://example.com/runs/42
```

- `--url` 指定点击「确定」后打开的任务链接；`--app` 接受 macOS 应用的 bundle identifier。同时提供时优先打开链接。
- `--id` 对相同事件 ID 去重。`--dry-run` 只输出事件 JSON，不入队、不弹窗。
- 运行 `bin/agent-ping done --help` 查看参数。也可以用 `bin/agent-ping demo --prototype --timeout 30` 直接测试限时浮窗，无需打包应用。

## 关闭提醒

```sh
scripts/install-integrations --uninstall
scripts/install-integrations --check
```

然后从菜单栏退出 Agent Ping。移动项目目录或删除 DSH 桌面配置前，请先撤销接入。Hook 指向原项目目录，卸载脚本也需要读取 DSH 桌面配置。只退出应用时，下一条接入事件仍会启动它。

队列和配置备份位于 `~/Library/Application Support/AgentPing`，撤销接入后仍会保留。自动接入使用通用提醒文案并记录事件元数据。脚本主动传入的正文和链接可能保存在本地队列中。

## 开发

先运行 `scripts/build`，再运行 `python3 -m unittest discover -s tests -v` 和 `node --test tests/dsh-plugin.test.mjs`。Node.js 测试需要 Node.js 18 或更新版本。窗口与接入的检查方法见[验证步骤](docs/validation.md)。

## 许可证

[MIT](LICENSE)
