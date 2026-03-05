# AnyMate-CC

将外部程序注入 Claude Code Agent Teams，使其成为团队成员。

AnyMate-CC 是一个 [MCP](https://modelcontextprotocol.io/) 服务器，能够启动持久化的子进程后端（Python REPL、Shell 等），并将它们作为 Claude Code 多智能体系统中的正式队友接入。消息通过 Claude Code 原生的文件信箱协议传递，无需额外的通信通道。

## 工作原理

```
Claude Code（团队负责人）
    │
    ├── SendMessage → 将 JSON 消息写入队友信箱
    │
    ▼
AnyMate-CC（MCP 服务器）
    │
    ├── MessageBridge 轮询信箱文件，获取未读消息
    ├── 将消息文本通过 stdin 转发给子进程
    ├── 子进程执行任务，输出结果，打印哨兵标记
    ├── Bridge 收集哨兵标记之前的所有输出
    └── 将回复写回发送者的信箱 JSON
```

AnyMate-CC 借助 Claude Code 现有的团队基础设施运作：

1. **注入团队配置** — `spawn_teammate` 向 `~/.claude/teams/{team}/config.json` 中添加成员记录，让 Claude Code 将外部进程识别为队友。
2. **信箱轮询** — `MessageBridge` 持续轮询每个队友的信箱文件（`inboxes/{name}.json`），读取未读消息并标记为已读。
3. **哨兵分隔的 I/O** — 每个后端用一个读取-执行循环包裹子进程。输入以 `__ANYMATE__:` 为前缀，输出以唯一的哨兵字符串结尾，确保多行输出的可靠捕获。
4. **回复投递** — 捕获到的输出被写入发送者的信箱，格式为标准的 Claude Code 消息，并附带一条空闲通知。

## 后端

| 后端 | 标识 | 说明 |
|------|------|------|
| **Python REPL** | `python-repl` | 持久化 Python 会话。支持 `eval`（表达式）和 `exec`（语句），状态跨消息保留。 |
| **Shell** | `shell` | 持久化 bash 会话。通过 `eval` 运行任意命令，适用于 CLI 工具、文件操作、git 等场景。 |

后端采用插件式设计 — 实现 `anymate.backends.base` 中的 `Backend` 和 `BridgeSession` 即可添加自定义后端。

## 安装

需要 Python 3.12+。唯一的运行时依赖是 `filelock`。

```bash
# 从源码安装
pip install -e .

# 或者直接设置 PYTHONPATH
export PYTHONPATH=/path/to/anymate-cc/src
```

### MCP 配置

添加到项目级 `.mcp.json` 或全局配置 `~/.claude/claude_code_config.json`：

```json
{
  "mcpServers": {
    "anymate": {
      "command": "python3",
      "args": ["-m", "anymate.server"],
      "env": {
        "PYTHONPATH": "/path/to/anymate-cc/src"
      }
    }
  }
}
```

## 使用方式

配置完成后，AnyMate-CC 向 Claude Code 暴露四个 MCP 工具：

### `spawn_teammate`

在已有团队中生成一个外部进程队友。

```
参数：
  team_name    （必填）Claude Code 团队名称
  name         （必填）队友名称（如 "py-repl"）
  backend_type （可选）"python-repl"（默认）或 "shell"
  cwd          （可选）子进程的工作目录
  prompt       （可选）初始上下文描述
```

团队必须事先存在（先用 Claude Code 的 `TeamCreate` 工具创建）。

### `stop_teammate`

停止运行中的队友并从团队配置中移除。

### `check_teammate`

检查队友的状态（进程是否存活、后端状态等）。

### `list_teammates`

列出团队中所有由 AnyMate 管理的队友。

### 使用示例

```
你：    "创建一个叫 'data-analysis' 的团队"
Claude：[调用 TeamCreate]

你：    "生成一个 Python REPL 队友，叫 'py'"
Claude：[调用 spawn_teammate，team_name="data-analysis", name="py"]

你：    "让 py 计算前 10 个斐波那契数"
Claude：[通过 SendMessage 发送消息给 py]
        → py 收到消息，执行 Python 代码，返回结果
        → Claude 在信箱中看到回复
```

## 配置项

环境变量（均为可选）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ANYMATE_CLAUDE_DIR` | `~/.claude` | Claude Code 团队和信箱的根目录 |
| `ANYMATE_POLL_INTERVAL` | `1.0` | 信箱轮询间隔（秒） |
| `ANYMATE_PYTHON` | `python3` | python-repl 后端使用的 Python 可执行文件 |

## 项目结构

```
src/anymate/
├── server.py              # MCP 服务器（基于 stdio 的 JSON-RPC 2.0）
├── bridge.py              # 信箱与子进程之间的消息中继
├── config.py              # 基于环境变量的配置
├── models.py              # 数据模型（TeammateMember、InboxMessage 等）
├── backends/
│   ├── base.py            # Backend / BridgeSession 抽象接口
│   ├── python_repl.py     # Python REPL 后端
│   └── shell.py           # Shell（bash）后端
└── protocol/
    ├── paths.py           # 团队目录与信箱的路径解析
    ├── teams.py           # 团队配置读写（注入/移除成员）
    ├── messaging.py       # 信箱操作（读取、追加、回复）
    └── fileops.py         # 带文件锁的原子写入
```

## 开发

```bash
pip install -e ".[dev]"
pytest
```

## 设计理念

- **零重型依赖** — 不依赖 pydantic、fastmcp 或 aiohttp。MCP 服务器是一个精简的 JSON-RPC 2.0 实现（约 100 行），唯一运行时依赖是 `filelock`。
- **基于文件的 IPC** — 复用 Claude Code 原生的信箱 JSON 文件，而非另造通信协议。队友可以直接通过 Claude Code 的 `SendMessage` 机制收发消息。
- **哨兵协议** — 每个后端使用唯一的随机哨兵字符串分隔输出边界，无需特殊转义即可可靠捕获多行输出。
- **可插拔后端** — 添加新后端（如 Node.js REPL、R 会话）只需实现两个类：`Backend`（工厂）和 `BridgeSession`（生命周期与 I/O）。

## 许可证

MIT
