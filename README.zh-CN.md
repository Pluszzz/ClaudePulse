# ClaudePulse

[English](README.md) | [简体中文](README.zh-CN.md)

一个轻量级的 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 状态监视器，始终置顶。  
一眼就能看到 Claude 在做什么——运行工具、等待批准、空闲还是出错了。

支持 **多个 Claude Code 会话同时监控**，带标签页切换。

![platform](https://img.shields.io/badge/platform-Windows-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![qt](https://img.shields.io/badge/Qt-PySide6-green)

## 界面展示

```
┌──────────────────────────────────────────┐
│ ClaudePulse                    ─  ×      │
├────────┬─────────────────────────────────┤
│ ● Proj │ ● 运行中                        │
│ ● App  │ Bash                            │
│ ● API  │ D:\CodeWork\...                  │
│        │                           [齿轮] │
└────────┴─────────────────────────────────┘
```

| 状态 | 颜色 | 含义 |
|------|------|------|
| ● 空闲 | 绿色 | 等待用户输入 |
| ● 运行中 | 蓝色 | 正在执行工具 |
| ● 等待批准 | 橙色 | 权限请求弹窗中 |
| ● 错误 | 红色 | 工具执行失败 |
| ● 启动中 | 紫色 | 会话启动中（3 秒后自动变空闲） |
| ● 已结束 | 灰色 | 会话已结束（30 秒后自动移除） |

状态变更时窗口边框会 **闪烁 3 次**，并自动切换到对应会话的标签页。

## 功能特性

- **始终置顶** — 永远在其他窗口之上
- **多会话标签页** — 每个 Claude Code 会话在左侧显示为一个标签
- **状态变更自动切换** — 某会话状态变化时自动跳到该标签
- **原生窗口缩放** — 拖拽窗口四边或四角即可调整大小
- **可拖拽分隔条** — 左右面板比例自由调整
- **拖拽排序标签** — 上下拖动标签交换位置
- **自适应高度** — 会话增多窗口自动拉高，上限 600px 后标签栏可滚轮滚动
- **透明度可调** — 通过设置菜单调整（默认 75%）
- **系统托盘** — 启动即显示托盘图标，颜色跟随当前会话状态
- **闪烁方式可选** — 支持全背景闪烁和边框闪烁，边框宽度可调（2-20px）
- **点击标题跳转** — "ClaudePulse" 文字点击可打开 GitHub 仓库
- **单实例运行** — 重复启动不会打开第二个窗口
- **全部记忆** — 窗口位置、大小、左右比例、透明度、闪烁设置均持久化

## 工作原理

```
Claude Code hooks ──▶ update-status.js ──▶ ~/.claude/status/sessions/{id}.json
                                                      │
ClaudePulse 窗口 ──▶ 每 500ms 轮询 ◀──────────────────┘
```

Hook 脚本监听 7 个 Claude Code 生命周期事件（`SessionStart`、`UserPromptSubmit`、`PreToolUse`、`Stop`、`PermissionRequest`、`PostToolUseFailure`、`SessionEnd`），将每个会话的状态写入 JSON 文件。GUI 轮询这些文件并渲染。

## 安装

### 一键安装

```bash
git clone https://github.com/Pluszzz/ClaudePulse.git
cd ClaudePulse
python install.py
```

安装脚本会自动：
1. 检测 Python / Node.js 环境
2. 从 GitHub Releases 下载 `ClaudePulse.exe`（约 47 MB，仅需一次）
3. 部署 Hook 脚本并配置 `settings.json`
4. 让你选择要配置自启动的终端（Git Bash / CMD / PowerShell / 全部）
5. 启动 ClaudePulse 做冒烟测试

完成后打开**新的终端窗口**，输入 `claude` 即可自动启动 ClaudePulse。

### 手动安装

如果你更习惯手动配置：

```bash
# 从 Releases 下载 exe 放到 ~/.claude/hooks/
mkdir -p ~/.claude/hooks
cp src/update-status.js ~/.claude/hooks/update-status.js
```

然后在 `~/.claude/settings.json` 中添加 hooks 配置（参考 `install.py` 输出），并在终端配置文件中设置自启动指向 `~/.claude/hooks/ClaudePulse.exe`。也可直接运行：

```bash
~/.claude/hooks/ClaudePulse.exe
```

### 开发者模式（从源码运行）

```bash
pip install PySide6
python src/main.py
```

## 从源码构建

```bash
pip install pyinstaller PySide6
pyinstaller --onefile --windowed --name "ClaudePulse" src/main.py
```

输出：`dist/ClaudePulse.exe`

## 依赖

**普通用户：**
- Node.js — 仅用于 Hook 脚本
- **无需其他依赖** — exe 自包含

**开发者：**
- Python 3.10+
- PySide6 — Qt GUI 框架
- PyInstaller — 构建 exe

## 项目结构

```
ClaudePulse/
├── src/
│   ├── main.py              ← Qt GUI 入口
│   ├── session_manager.py   ← 数据层（读取会话 JSON）
│   └── update-status.js     ← Claude Code Hook 脚本
├── install.py               ← 一键安装脚本
├── ClaudePulse.spec         ← PyInstaller 构建配置
├── LICENSE
├── README.md
├── README.zh-CN.md
└── .gitignore
```

## 许可证

MIT © Pluszzz
