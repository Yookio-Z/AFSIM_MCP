# AFSIM MCP

本项目是一个本地 MCP 服务器，用于把 AFSIM 能力接入支持 MCP 的客户端（如 Cursor、Claude Desktop、VS Code、Trae、OpenCode 等）。  
通过脚本交互配置后，直接复制生成的配置到你的客户端即可使用。

## 前置条件

- Windows
- Python 3.10+
- 已安装 AFSIM（本机可运行）

## 一键配置

在项目目录执行：

```bash
python configure_mcp.py
```

脚本会按提示询问并写入本地配置，同时输出客户端所需的 MCP 配置片段。

### 配置项说明

- AFSIM 根目录：AFSIM 安装目录
- AFSIM 项目目录：你的工程目录
- AFSIM demos 目录：官方示例目录
- AFSIM bin 目录：mission.exe 等可执行文件所在目录
- 配置文件存放目录：默认 `C:\Users\你的用户名\.afsim_mcp`

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
        "AFSIM_MCP_STATE_DIR": "C:\\Users\\你的用户名\\.afsim_mcp"
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
        "AFSIM_MCP_STATE_DIR": "C:\\Users\\你的用户名\\.afsim_mcp"
      }
    }
  }
}
```

脚本会自动使用当前 Python 的绝对路径和项目的绝对路径，因此对其他电脑同样通用。

## 常见问题

### 客户端显示 failed/disabled

优先在终端直接运行：

```bash
python <AFSIM_MCP路径>\transport\stdio.py
```

如果此命令报错，说明 Python 路径或依赖问题需要先解决。

### 需要手动启动服务吗

不需要。客户端会自动拉起本地 MCP 进程。  
若客户端找不到 python，可使用脚本生成的绝对路径配置。
