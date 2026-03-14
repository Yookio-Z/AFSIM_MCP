# AFSIM MCP

本项目是一个本地 MCP 服务器，用于把 AFSIM 能力接入支持 MCP 的客户端（如 Cursor、Claude Desktop、VS Code、Trae、OpenCode 等）。

仓库只包含 MCP 服务源码与配置脚本，不附带测试工程、测试数据、示例生成产物或本地运行状态。实际使用时，请把 AFSIM 工程目录通过配置指向你自己的 `project_root`。

如需给大模型或团队成员提供统一项目背景与建模建议，可参考仓库中的 `memory.md`。
如需评估当前项目真实能力边界，可参考 `CAPABILITY_ASSESSMENT.md`；如需约束接入大模型的标准工作流，可参考 `MODEL_WORKFLOW_PROMPT.md`。

## 前置条件

- Windows
- Python 3.10+
- 已安装 AFSIM（本机可运行）

## 快速开始

在项目目录执行：

```bash
python configure_mcp.py
```

脚本会按提示询问并写入本地配置，同时输出客户端所需的 MCP 配置片段。

### 配置项说明

- AFSIM 根目录：AFSIM 安装目录
- AFSIM 项目目录：你的 AFSIM 工程目录
- AFSIM demos 目录：官方示例目录
- AFSIM bin 目录：`mission.exe` 等可执行文件所在目录
- 配置文件存放目录：默认 `C:\Users\你的用户名\.afsim_mcp`
- 运行时状态目录：默认 `project_root\mcp_state`；客户端通常只需要传入 `AFSIM_MCP_CONFIG_DIR` 用于定位配置文件，如需覆盖状态目录可额外设置 `AFSIM_MCP_STATE_DIR`

如果检测到已有配置，脚本会显示旧值；直接回车表示保留旧值。

## 客户端配置

脚本会输出两段内容：

1) 通用连接信息  
2) 你选择的平台对应的 JSON 配置示例

### 通用格式（适用于大多数客户端）

```json
{
  "mcpServers": {
    "afsim": {
      "command": "C:\\path\\to\\python.exe",
      "args": ["C:\\path\\to\\AFSIM_MCP\\transport\\stdio.py"],
      "env": {
        "AFSIM_MCP_CONFIG_DIR": "C:\\Users\\你的用户名\\.afsim_mcp"
      }
    }
  }
}
```

### OpenCode 格式

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "afsim": {
      "type": "local",
      "command": [
        "C:\\path\\to\\python.exe",
        "C:\\path\\to\\AFSIM_MCP\\transport\\stdio.py"
      ],
      "enabled": true,
      "environment": {
        "AFSIM_MCP_CONFIG_DIR": "C:\\Users\\你的用户名\\.afsim_mcp"
      }
    }
  }
}
```


