import AppKit
import Foundation
import Darwin

struct Ping: Codable {
    let id: String
    let kind: String
    let source: String
    let title: String
    let message: String
    let url: String?
    let appBundleId: String?
    let createdAt: String

    func validate() throws {
        guard ["done", "question", "error", "turn-complete"].contains(kind),
              !id.isEmpty, id.count <= 200,
              !source.isEmpty, source.count <= 100,
              !title.isEmpty, title.count <= 160,
              message.count <= 8000 else {
            throw NSError(domain: "AgentPing", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "事件字段无效或过长"])
        }
        if let raw = url {
            guard let parsed = URL(string: raw),
                  raw.count <= 4096,
                  ["https", "http", "codex", "lark", "feishu"].contains(parsed.scheme?.lowercased() ?? ""),
                  parsed.user == nil, parsed.password == nil,
                  (!["https", "http"].contains(parsed.scheme?.lowercased() ?? "") || parsed.host?.isEmpty == false) else {
                throw NSError(domain: "AgentPing", code: 2,
                              userInfo: [NSLocalizedDescriptionKey: "不支持的任务链接"])
            }
        }
        if let bundle = appBundleId {
            guard bundle.count <= 255,
                  bundle.range(of: "^[A-Za-z0-9][A-Za-z0-9-]*(\\.[A-Za-z0-9][A-Za-z0-9-]*)+$", options: .regularExpression) != nil else {
                throw NSError(domain: "AgentPing", code: 4,
                              userInfo: [NSLocalizedDescriptionKey: "来源应用标识无效"])
            }
        }
    }

    var accent: NSColor {
        switch kind {
        case "question": return .systemOrange
        case "error": return .systemRed
        default: return .systemGreen
        }
    }
}

func readPing(_ path: URL) throws -> Ping {
    let data = try Data(contentsOf: path)
    guard data.count <= 65536 else {
        throw NSError(domain: "AgentPing", code: 3,
                      userInfo: [NSLocalizedDescriptionKey: "事件文件超过 64 KiB"])
    }
    let ping = try JSONDecoder().decode(Ping.self, from: data)
    try ping.validate()
    return ping
}

func label(_ text: String, size: CGFloat, weight: NSFont.Weight = .regular) -> NSTextField {
    let result = NSTextField(wrappingLabelWithString: text)
    result.font = .systemFont(ofSize: size, weight: weight)
    result.textColor = .labelColor
    result.setContentCompressionResistancePriority(.required, for: .vertical)
    return result
}

final class PingPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem?
    var panels: [PingPanel] = []
    var statusLabels: [NSTextField] = []
    var confirmButtons: [NSButton] = []
    var current: (Ping, URL?)?
    var timer: Timer?
    var pendingMenu: NSMenuItem?
    let oneShot: URL?
    let timeout: Double
    let queueRoot: URL
    let instanceLock: Int32
    var snoozedUntil: Date?

    init(oneShot: URL?, timeout: Double, queueRoot: URL, instanceLock: Int32 = -1) {
        self.oneShot = oneShot
        self.timeout = timeout
        self.queueRoot = queueRoot
        self.instanceLock = instanceLock
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        if let path = oneShot {
            do { show(try readPing(path), file: nil) }
            catch { fail(error) }
            if timeout > 0 {
                DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                    NSApp.terminate(nil)
                }
            }
        } else {
            setupMenu()
            drain()
            timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
                self?.drain()
            }
        }
    }

    func setupMenu() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem?.button?.image = NSImage(systemSymbolName: "bell.badge", accessibilityDescription: "AgentPing 任务提醒")
        let menu = NSMenu()
        let heading = NSMenuItem(title: "AgentPing · 本地任务提醒", action: nil, keyEquivalent: "")
        menu.addItem(heading)
        let pending = NSMenuItem(title: "没有待处理提醒", action: #selector(restore), keyEquivalent: "")
        pending.target = self
        pendingMenu = pending
        menu.addItem(pending)
        menu.addItem(.separator())
        for (title, action) in [("测试：返回 Codex", #selector(testQuestion)), ("测试：返回 DSH", #selector(testDone))] {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
            item.target = self
            menu.addItem(item)
        }
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "退出 AgentPing", action: #selector(quitApp), keyEquivalent: "q")
        quit.target = self
        menu.addItem(quit)
        statusItem?.menu = menu
    }

    @objc func quitApp() { NSApp.terminate(nil) }
    @objc func restore() {
        snoozedUntil = nil
        if let (ping, file) = current { show(ping, file: file) }
    }
    @objc func testQuestion() { localTest(kind: "question") }
    @objc func testDone() { localTest(kind: "done") }

    func localTest(kind: String) {
        guard current == nil else { restore(); return }
        let isCodex = kind == "question"
        let ping = Ping(id: UUID().uuidString, kind: kind, source: isCodex ? "Codex" : "DSH",
                        title: isCodex ? "测试：返回 Codex" : "测试：返回 DSH",
                        message: "点击“确定”将来源应用带到前台。这是一条测试提醒，没有执行真实任务。",
                        url: nil, appBundleId: isCodex ? "com.openai.codex" : "com.deepseek.dsh",
                        createdAt: ISO8601DateFormatter().string(from: Date()))
        show(ping, file: nil)
    }

    func drain() {
        if let until = snoozedUntil, until <= Date() { restore() }
        guard current == nil else { return }
        let inbox = queueRoot.appendingPathComponent("inbox", isDirectory: true)
        let files: [URL]
        do {
            files = try FileManager.default.contentsOfDirectory(at: inbox, includingPropertiesForKeys: [.contentModificationDateKey])
                .filter { $0.pathExtension == "json" }.sorted {
                    let left = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                    let right = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                    return left == right ? $0.lastPathComponent < $1.lastPathComponent : left < right
                }
        } catch {
            fputs("AgentPing 队列读取失败：\(error.localizedDescription)\n", stderr)
            return
        }
        for path in files {
            do {
                let ping = try readPing(path)
                let receipt = queueRoot.appendingPathComponent("receipts/\(path.lastPathComponent)")
                if FileManager.default.fileExists(atPath: receipt.path) {
                    try FileManager.default.removeItem(at: path)
                    continue
                }
                show(ping, file: path)
                return
            } catch {
                fputs("AgentPing 忽略无效事件：\(path.lastPathComponent): \(error.localizedDescription)\n", stderr)
                let rejected = queueRoot.appendingPathComponent("rejected/\(path.lastPathComponent)")
                do { try FileManager.default.moveItem(at: path, to: rejected) }
                catch { fputs("AgentPing 无法移走无效事件：\(error.localizedDescription)\n", stderr) }
            }
        }
    }

    func closePanels() {
        panels.forEach { $0.orderOut(nil) }
        panels.removeAll()
        statusLabels.removeAll()
        confirmButtons.removeAll()
    }

    func show(_ ping: Ping, file: URL?) {
        closePanels()
        current = (ping, file)
        snoozedUntil = nil
        pendingMenu?.title = "待处理：\(ping.title)"
        for screen in NSScreen.screens {
            let frame = screen.visibleFrame
            let width = min(CGFloat(520), frame.width - 40)
            let panel = PingPanel(contentRect: NSRect(x: 0, y: 0, width: width, height: 320),
                                  styleMask: [.titled, .fullSizeContentView, .nonactivatingPanel],
                                  backing: .buffered, defer: false)
            panel.title = "AgentPing · \(ping.title)"
            panel.titleVisibility = .hidden
            panel.titlebarAppearsTransparent = true
            panel.isReleasedWhenClosed = false
            panel.hidesOnDeactivate = false
            panel.isFloatingPanel = true
            panel.level = .statusBar
            panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .canJoinAllApplications]
            panel.isMovableByWindowBackground = true
            panel.backgroundColor = .windowBackgroundColor
            panel.hasShadow = true
            panel.isOpaque = false
            let body = NSStackView()
            body.orientation = .vertical
            body.alignment = .leading
            body.spacing = 16
            body.edgeInsets = NSEdgeInsets(top: 30, left: 30, bottom: 26, right: 30)

            let source = label("\(ping.source)  ·  \(ping.kind == "question" ? "等待交互" : ping.kind == "error" ? "发生错误" : ping.kind == "turn-complete" ? "一轮结束" : "任务完成")", size: 13, weight: .medium)
            source.textColor = ping.accent
            body.addArrangedSubview(source)
            let title = label(ping.title, size: 27, weight: .semibold)
            title.maximumNumberOfLines = 2
            body.addArrangedSubview(title)
            let message = label(ping.message, size: 15)
            message.maximumNumberOfLines = 7
            message.lineBreakMode = .byTruncatingTail
            message.toolTip = ping.message
            body.addArrangedSubview(message)
            let hasTarget = ping.url != nil || ping.appBundleId != nil
            let note = label(hasTarget ? "点击“确定”返回任务；弹出时不切换应用。" : "提醒将保留到你确认；弹出时不切换应用。", size: 12)
            note.textColor = .secondaryLabelColor
            statusLabels.append(note)
            body.addArrangedSubview(note)
            let buttons = NSStackView()
            buttons.orientation = .horizontal
            buttons.spacing = 10
            if oneShot == nil {
                let later = NSButton(title: "1 分钟后提醒", target: self, action: #selector(snooze))
                later.bezelStyle = .rounded
                buttons.addArrangedSubview(later)
            }
            if hasTarget {
                let close = NSButton(title: "仅关闭", target: self, action: #selector(acknowledge))
                close.bezelStyle = .rounded
                buttons.addArrangedSubview(close)
            }
            let dismiss = NSButton(title: "确定", target: self, action: #selector(confirm))
            dismiss.bezelStyle = .rounded
            dismiss.bezelColor = ping.accent
            dismiss.setAccessibilityLabel(hasTarget ? "确定，返回来源任务" : "确定，关闭此条提醒")
            confirmButtons.append(dismiss)
            buttons.addArrangedSubview(dismiss)
            body.addArrangedSubview(buttons)
            body.translatesAutoresizingMaskIntoConstraints = false
            let container = NSView(frame: NSRect(x: 0, y: 0, width: width, height: 320))
            container.addSubview(body)
            NSLayoutConstraint.activate([
                body.leadingAnchor.constraint(equalTo: container.leadingAnchor),
                body.trailingAnchor.constraint(equalTo: container.trailingAnchor),
                body.topAnchor.constraint(equalTo: container.topAnchor),
                body.bottomAnchor.constraint(equalTo: container.bottomAnchor)
            ])
            panel.contentView = container
            let height = min(max(body.fittingSize.height, 280), frame.height - 40)
            panel.setContentSize(NSSize(width: width, height: height))
            panel.setFrameOrigin(NSPoint(x: frame.midX - width / 2, y: frame.midY - height / 2))
            panels.append(panel)
            panel.orderFrontRegardless()
        }
    }

    @objc func snooze() {
        closePanels()
        snoozedUntil = Date().addingTimeInterval(60)
    }

    func reportOpenFailure(_ message: String) {
        statusLabels.forEach { $0.stringValue = message; $0.textColor = .systemRed }
        confirmButtons.forEach { $0.isEnabled = true }
    }

    @objc func confirm() {
        guard let ping = current?.0 else { return }
        if let raw = ping.url, let url = URL(string: raw) {
            if NSWorkspace.shared.open(url) { acknowledge() }
            else { reportOpenFailure("无法打开任务链接；可重试或选择“仅关闭”。") }
            return
        }
        guard let bundle = ping.appBundleId else { acknowledge(); return }
        guard let appURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundle) else {
            reportOpenFailure("未找到来源应用：\(bundle)")
            return
        }
        confirmButtons.forEach { $0.isEnabled = false }
        let config = NSWorkspace.OpenConfiguration()
        config.activates = true
        NSWorkspace.shared.openApplication(at: appURL, configuration: config) { [weak self] app, error in
            DispatchQueue.main.async {
                guard let self = self, self.current?.0.id == ping.id else { return }
                if app != nil && error == nil { self.acknowledge() }
                else { self.reportOpenFailure("无法打开来源应用；可重试或选择“仅关闭”。") }
            }
        }
    }

    @objc func acknowledge() {
        if let path = current?.1 {
            let receipt = queueRoot.appendingPathComponent("receipts/\(path.lastPathComponent)")
            do {
                try Data().write(to: receipt, options: .atomic)
                try FileManager.default.removeItem(at: path)
            } catch {
                fputs("AgentPing 确认写入失败：\(error.localizedDescription)\n", stderr)
                return
            }
        }
        closePanels()
        current = nil
        pendingMenu?.title = "没有待处理提醒"
        if oneShot != nil { NSApp.terminate(nil) } else { drain() }
    }

    func fail(_ error: Error) {
        fputs("AgentPing: \(error.localizedDescription)\n", stderr)
        exit(1)
    }
}

let args = Array(CommandLine.arguments.dropFirst())
func option(_ key: String) -> String? {
    guard let i = args.firstIndex(of: key), i + 1 < args.count else { return nil }
    return args[i + 1]
}

if let file = option("--validate") {
    do {
        let ping = try readPing(URL(fileURLWithPath: file))
        print("valid: \(ping.kind) / \(ping.source)")
        exit(0)
    } catch {
        fputs("AgentPing: \(error.localizedDescription)\n", stderr)
        exit(1)
    }
}

let queueRoot = URL(fileURLWithPath: ProcessInfo.processInfo.environment["AGENTPING_DATA_DIR"]
    ?? (NSHomeDirectory() + "/Library/Application Support/AgentPing"), isDirectory: true)
var lockFD: Int32 = -1
if option("--event") == nil {
    do {
        for name in ["", "inbox", "receipts", "rejected"] {
            try FileManager.default.createDirectory(at: queueRoot.appendingPathComponent(name),
                withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        }
    } catch {
        fputs("AgentPing 数据目录创建失败：\(error.localizedDescription)\n", stderr)
        exit(1)
    }
    lockFD = open(queueRoot.appendingPathComponent("app.lock").path, O_CREAT | O_RDWR, 0o600)
    guard lockFD >= 0 else { fputs("AgentPing 无法创建实例锁\n", stderr); exit(1) }
    guard flock(lockFD, LOCK_EX | LOCK_NB) == 0 else { exit(0) }
}

let application = NSApplication.shared
let delegate = AppDelegate(oneShot: option("--event").map { URL(fileURLWithPath: $0) },
                           timeout: Double(option("--timeout") ?? "0") ?? 0,
                           queueRoot: queueRoot, instanceLock: lockFD)
application.delegate = delegate
application.run()
