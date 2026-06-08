# ClaudePulse

[English](README.md) | [简体中文](README.zh-CN.md)

一个轻量级的 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 状态监视器，始终置顶。  
一眼就能看到 Claude 在做什么——运行工具、等待批准、空闲还是出错了。

支持 **多个 Claude Code 会话同时监控**，带标签页切换。

![platform](https://img.shields.io/badge/platform-Windows-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![qt](https://img.shields.io/badge/Qt-PySide6-green)

## 双形态设计

**紧凑圆**（鼠标在别处时显示）：

```
         ╭──────────╮
        ╱            ╲
       │  ●  运行中    │
       │  myproject   │
        ╲            ╱
         ╰──────────╯
    120×120 圆形 · 始终置顶
```

**完整窗口**（鼠标悬停到圆上时展开）：

```
┌──────────────────────────────────────────┐
│ ClaudePulse                    ─  ×      │
├────────┬─────────────────────────────────┤
│ ● Proj │ ●  运行中                       │
│ ● App  │ Bash                            │
│ ● API  │ myproject-feature               │
└────────┴─────────────────────────────────┘
```

鼠标移到圆上 → mask 展开动画（100ms）变为完整窗口。鼠标移开 → mask 收缩回圆形。两个窗口中心对齐过渡，文字在屏幕上的位置保持不变。

### 半圆吸附停靠

当完整窗口贴住屏幕边缘（左 / 右 / 上）时，紧凑圆会自动变成**半圆形**吸附在对应边缘：

| 边缘 | 形状 | 尺寸 | 显示内容 |
|------|------|------|----------|
| 左 | ◗ 右半圆可见 | 60×120 | 仅状态 |
| 右 | ◖ 左半圆可见 | 60×120 | 仅状态 |
| 上 | ◔ 下半圆可见 | 120×60 | 状态 + 名称 |

将完整窗口拖到任意屏幕边缘贴住，鼠标移开即可看到。支持多显示器。

## 状态指示

| 状态 | 颜色 | 含义 |
|------|------|------|
| ● 空闲 | 绿色 | 等待用户输入 |
| ● 运行中 | 蓝色 | 正在执行工具 |
| ● 等待批准 | 橙色 | 权限请求弹窗中 |
| ● 错误 | 红色 | 工具执行失败 |
| ● 启动中 | 紫色 | 会话启动中（3 秒后自动变空闲） |
| ● 已结束 | 灰色 | 会话已结束（30 秒后自动移除） |

紧凑圆和完整窗口在状态变更时**都会闪烁 3 次**（全背景或边框模式，可在设置中切换）。

## 功能特性

- **始终置顶** — 永远在其他窗口之上
- **双形态** — 鼠标不在时显示 120×120 紧凑圆，悬停时展开为完整窗口
- **半圆吸附** — 自动贴附屏幕左/右/上边缘，变为半圆形
- **平滑 mask 动画** — 100ms 展开 / 收缩，中心对齐
- **多会话标签页** — 每个 Claude Code 会话在左侧显示为一个标签
- **状态变更自动切换** — 某会话状态变化时自动跳到该标签
- **双端闪动** — 紧凑圆和完整窗口均支持闪烁；全背景 / 边框两种模式
- **透明度可调** — 通过托盘 → 设置调整（默认 75%）
- **系统托盘** — 启动即显示托盘图标，颜色跟随当前状态；右击打开设置
- **原生窗口缩放** — 拖拽完整窗口四边或四角调整大小
- **拖拽排序标签** — 上下拖动标签交换位置
- **自适应高度** — 会话增多窗口自动拉高，上限 600px
- **文字跑马灯** — 紧凑圆内超长会话名水平滚动播放
- **点击标题** — "ClaudePulse" 点击可打开 GitHub 仓库
- **单实例运行** — 重复启动不会打开第二个窗口
- **多显示器** — 正确检测并吸附到任意屏幕
- **全部记忆** — 窗口位置、大小、左右比例、透明度、闪烁设置均持久化

## 工作原理

```
Claude Code hooks ──▶ update-status.js ──▶ ~/.claude/status/sessions/{id}.json
                                                      │
ClaudePulse ──▶ 每 500ms 轮询 ◀───────────────────────┘
```

Hook 脚本监听 7 个 Claude Code 生命周期事件（`SessionStart`、`UserPromptSubmit`、`PreToolUse`、`Stop`、`PermissionRequest`、`PostToolUseFailure`、`SessionEnd`），将每个会话的状态写入 JSON 文件。GUI 轮询这些文件并渲染。

## 安装

### 一键安装

下载解压后**双击 `install.bat`** 即可。

或命令行：

```bash
git clone https://github.com/Pluszzz/ClaudePulse.git
cd ClaudePulse
install.bat
```

安装脚本会自动：
1. 检测 Node.js 环境
2. 从 GitHub Releases 下载 `ClaudePulse.exe`（约 47 MB，仅需一次）
3. 部署 Hook 脚本并配置 `settings.json`
4. 让你选择要配置自启动的终端（CMD / PowerShell）
5. 完成 — 打开**新的终端窗口**，输入 `claude`

### 手动安装

如果你更习惯手动配置：

```bash
# 从 Releases 下载 exe 放到 ~/.claude/hooks/
mkdir -p ~/.claude/hooks
cp src/update-status.js ~/.claude/hooks/update-status.js
```

然后在 `~/.claude/settings.json` 中添加 hooks 配置，并在终端配置文件中设置自启动指向 `~/.claude/hooks/ClaudePulse.exe`。也可直接运行：

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
├── install.bat              ← 一键安装脚本
├── ClaudePulse.spec         ← PyInstaller 构建配置
├── LICENSE
├── README.md
├── README.zh-CN.md
└── .gitignore
```

## 许可证

MIT © Pluszzz
