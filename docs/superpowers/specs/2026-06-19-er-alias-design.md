# `er` 启动别名设计

## 目标

为现有 CLI 增加一个更短的启动命令 `er`，用于替代较长的
`electronic-recognition --port 8892`。

## 现状

- 当前 CLI 入口定义在 `pyproject.toml` 的 `project.scripts` 中：
  `electronic-recognition = "electronic_recognition.cli:main"`
- 当前启动逻辑位于 `src/electronic_recognition/cli.py`
- 默认端口已经是 `8892`，因此无参启动即可满足当前默认需求

## 方案

在 `pyproject.toml` 中新增一个脚本别名：

```toml
[project.scripts]
electronic-recognition = "electronic_recognition.cli:main"
er = "electronic_recognition.cli:main"
```

该别名与现有命令共用同一套 CLI 解析逻辑，不新增额外脚本文件，
也不修改服务启动行为。

## 用户使用方式

安装或重新执行开发模式安装后，可直接使用：

```powershell
er
```

如需覆盖默认端口，仍可继续传参：

```powershell
er --port 9000
```

## 文档调整

更新 `README.md` 的“启动”部分：

- 主示例改为 `er`
- 补充说明默认端口为 `8892`
- 如有需要，保留原命令作为兼容写法说明

## 风险与兼容性

- 风险较低，仅增加一个新的包入口
- 不影响已有 `electronic-recognition` 使用方式
- 用户需要重新安装一次项目，才能在本地获得新的 `er` 命令

## 验证

- 检查 `pyproject.toml` 中新脚本入口已定义
- 重新安装项目后执行 `er --help`
- 执行 `er`，确认服务启动在默认端口 `8892`
