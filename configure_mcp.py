import json
import os
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.stderr.write("afsim-mcp requires Python 3.10+.\n")
    sys.exit(1)

root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

try:
    from core.server import MCPServer
except Exception as exc:
    sys.stderr.write(f"afsim-mcp failed to start: {exc}\n")
    sys.stderr.write("Make sure dependencies are installed and PYTHONPATH is correct.\n")
    sys.exit(1)


def prompt_path(title, optional=True, default_value=None, help_text=None):
    while True:
        suffix = "（可留空）" if optional else ""
        default_hint = f"默认：{default_value}" if default_value else ""
        help_hint = f"\n{help_text}" if help_text else ""
        text = f"{title}{suffix}{' ' if default_hint else ''}{default_hint}{help_hint}\n> "
        value = input(text).strip()
        if not value:
            if default_value:
                return str(default_value)
            return None
        path = Path(value)
        if path.exists():
            return str(path)
        print(f"路径不存在：{path}")


def prompt_platform():
    options = [
        "通用（多数客户端）",
        "Trae",
        "Cursor",
        "Claude Desktop",
        "VS Code",
        "OpenCode",
        "OpenClaw",
        "其他",
    ]
    print("\n请选择你的 MCP 客户端平台：")
    for index, name in enumerate(options, start=1):
        print(f"{index}) {name}")
    while True:
        value = input("> ").strip()
        if not value:
            return options[0]
        if value.isdigit():
            pick = int(value)
            if 1 <= pick <= len(options):
                return options[pick - 1]
        print("请输入序号（1-8），或直接回车使用通用模板。")


def build_config_json(platform_name, command, args, env):
    if platform_name == "OpenCode":
        payload = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "afsim": {
                    "type": "local",
                    "command": [command, *args],
                    "enabled": True,
                    "environment": env,
                }
            },
        }
        return platform_name, payload
    payload = {
        "mcpServers": {
            "afsim": {
                "command": command,
                "args": args,
                "env": env,
            }
        }
    }
    return platform_name, payload


def main():
    default_state_dir = Path.home() / ".afsim_mcp"
    state_dir = prompt_path(
        "配置文件存放目录",
        optional=True,
        default_value=default_state_dir,
        help_text="用于保存本机配置与状态，建议放在用户目录下",
    )
    if state_dir:
        os.environ["AFSIM_MCP_STATE_DIR"] = state_dir
    server = MCPServer()
    config = server.read_config()
    if config:
        print("\n检测到已有配置，将在你输入新值后更新：")
        for key, value in config.items():
            print(f"{key}: {value}")
    afsim_root = prompt_path(
        "请输入 AFSIM 根目录",
        optional=True,
        default_value=config.get("afsim_root"),
        help_text="示例：D:\\AFSIM，直接回车保留旧值",
    )
    project_root = prompt_path(
        "请输入 AFSIM 项目目录",
        optional=True,
        default_value=config.get("project_root"),
        help_text="你自己的工程目录，直接回车保留旧值",
    )
    demos_root = prompt_path(
        "请输入 AFSIM demos 目录",
        optional=True,
        default_value=config.get("demos_root"),
        help_text="官方示例目录，直接回车保留旧值",
    )
    afsim_bin = prompt_path(
        "请输入 AFSIM bin 目录",
        optional=True,
        default_value=config.get("afsim_bin"),
        help_text="mission.exe 等可执行文件所在目录，直接回车保留旧值",
    )
    updates = {
        "afsim_root": afsim_root,
        "project_root": project_root,
        "demos_root": demos_root,
        "afsim_bin": afsim_bin,
    }
    for key, value in updates.items():
        if value:
            config[key] = value
    server.write_config(config)
    resolved = {
        "afsim_root": str(server.resolve_afsim_root()) if server.resolve_afsim_root() else None,
        "project_root": str(server.resolve_project_root()) if server.resolve_project_root() else None,
        "demos_root": str(server.resolve_demos_root()) if server.resolve_demos_root() else None,
        "afsim_bin": str(server.resolve_bin_path()) if server.resolve_bin_path() else None,
        "state_dir": str(server.state_dir),
    }
    print("\n配置完成：")
    print(server.config_path)
    print("\n解析结果：")
    for key, value in resolved.items():
        print(f"{key}: {value}")
    state_dir_str = str(server.state_dir)
    server_path = (Path(__file__).resolve().parent / "transport" / "stdio.py").resolve()
    server_path_str = str(server_path)
    python_path_str = sys.executable
    platform = prompt_platform()
    platform_name, payload = build_config_json(
        platform,
        python_path_str,
        [server_path_str],
        {"AFSIM_MCP_STATE_DIR": state_dir_str},
    )
    print("\n通用连接信息（填入你的 MCP 客户端配置即可）：")
    print(f'command: "{python_path_str}"')
    print(f'args: ["{server_path_str}"]')
    print(f'env: {{"AFSIM_MCP_STATE_DIR": "{state_dir_str}"}}')
    print(f"\n{platform_name} 配置示例：")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\n如果你的客户端配置文件键名不同，请保留 command/args/env 三项并按客户端要求嵌入。")


if __name__ == "__main__":
    main()
