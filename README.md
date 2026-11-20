# Agent Ping

[简体中文](README.zh-CN.md)

Agent Ping is a macOS menu bar app that shows a persistent alert when a local agent finishes a turn, asks a question, or requests approval. It includes integrations for Codex and DeepSeek Harness (DSH) Desktop. Other tools can send alerts through the command line.

Alerts can appear over full-screen apps without taking keyboard focus. Click the confirmation button to open the task link or return to the source app. Handle questions and approvals in the source app. The current app interface is in Simplified Chinese.

## Quick start

Requires macOS 13 or later, Python 3.9 or later, and Xcode Command Line Tools. Run these commands from a terminal:

```sh
git clone https://github.com/puliandc/agent-ping-macos.git
cd agent-ping-macos
scripts/build
bin/agent-ping start
bin/agent-ping demo --delay 8
```

The build creates a locally signed app at `dist/AgentPing.app`. The demo sends a test alert after eight seconds, giving you time to switch apps. Use `bin/agent-ping status` to see whether the menu bar app is running and how many alerts are pending.

## Connect Codex and DSH

The installer configures both integrations together. It requires the `codex` command on your PATH and an initialized DSH Desktop profile at `~/.dsh/profiles/desktop`. The manual commands below work independently of these integrations.

```sh
scripts/install-integrations
scripts/install-integrations --check
scripts/check-codex-hooks
```

1. Run the installer to add the handlers. It backs up the configuration files and preserves existing hooks and Codex `notify` settings.
2. Open **Settings → Hooks** in Codex or run **`/hooks`** in the CLI. Review and trust the Agent Ping handlers for `Stop`, `PermissionRequest`, and `PreToolUse`.
3. Check the configuration and hook trust with the two check commands. Then run a short task in your usual client to verify delivery. If a client still uses the old configuration, try a new session.

The integrations alert on turn completion, questions, and approval requests. DSH also reports failed turns. A turn can end while the broader task is still in progress. Use `done` when the caller can confirm that its task is complete.

## Send alerts from other tools

Call the sender at the end of a script or from an agent lifecycle callback:

```sh
bin/agent-ping done --source "Build" --message "Build completed."
bin/agent-ping question --source "Local agent" --message "Choose the next step." --app com.apple.Terminal
bin/agent-ping error --source "CI" --message "Review the failed run." --url https://example.com/runs/42
```

- `--url` opens a task link on confirmation. `--app` uses a macOS bundle identifier to select an app. The link takes precedence when both are supplied.
- `--id` deduplicates alerts with the same event ID. `--dry-run` prints the JSON event without queuing it or showing an alert.
- Run `bin/agent-ping done --help` for the available options. For a bounded test without app packaging, run `bin/agent-ping demo --prototype --timeout 30`.

## Turn off alerts

```sh
scripts/install-integrations --uninstall
scripts/install-integrations --check
```

Then quit Agent Ping from the menu bar. Do this before moving the checkout or deleting the DSH Desktop profile. The hooks point to the original checkout, and the uninstaller reads that profile. Quitting the app by itself leaves the integrations active, so the next event can start it again.

Agent Ping stores its queue and configuration backups under `~/Library/Application Support/AgentPing`. Uninstalling the integrations keeps those files. The integrations write generic alert text and event metadata. Text and links sent explicitly by your own scripts can be stored in the local queue.

## Development

Run `scripts/build`, then `python3 -m unittest discover -s tests -v` and `node --test tests/dsh-plugin.test.mjs`. The Node.js tests require Node.js 18 or later. See [validation steps](docs/validation.md) for display and integration checks.

## License

[MIT](LICENSE)
