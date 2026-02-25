import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from subprocess import run

try:
    from ..tools import build_tool_router, build_tool_specs
except ImportError:
    from tools import build_tool_router, build_tool_specs


class MCPServer:
    def __init__(self):
        self.base_dir = self.resolve_base_dir()
        self.state_dir = self.resolve_state_dir()
        self.scenarios_dir = self.state_dir / "scenarios"
        self.runs_dir = self.state_dir / "runs"
        self.results_dir = self.state_dir / "results"
        self.config_path = self.state_dir / "config.json"
        self.scenarios_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def resolve_base_dir(self):
        env_dir = os.environ.get("AFSIM_MCP_BASE_DIR")
        if env_dir:
            return Path(env_dir)
        file_path = Path(__file__).resolve()
        if len(file_path.parents) > 3 and file_path.parents[2].name == "src":
            return file_path.parents[3]
        return file_path.parents[1]

    def resolve_state_dir(self):
        env_dir = os.environ.get("AFSIM_MCP_STATE_DIR")
        if env_dir:
            return Path(env_dir)
        return self.base_dir / "mcp_state"

    def resolve_afsim_root(self):
        env_root = os.environ.get("AFSIM_ROOT")
        if env_root and Path(env_root).exists():
            return Path(env_root)
        config = self.read_config()
        cfg_root = config.get("afsim_root")
        if cfg_root and Path(cfg_root).exists():
            return Path(cfg_root)
        if self.base_dir.parent.exists():
            return self.base_dir.parent
        return None

    def resolve_project_root(self):
        env_root = os.environ.get("AFSIM_PROJECT_ROOT")
        if env_root and Path(env_root).exists():
            return Path(env_root)
        config = self.read_config()
        cfg_root = config.get("project_root")
        if cfg_root and Path(cfg_root).exists():
            return Path(cfg_root)
        afsim_root = self.resolve_afsim_root()
        if afsim_root:
            candidate = afsim_root / "project"
            if candidate.exists():
                return candidate
            return afsim_root
        return None

    def resolve_demos_root(self):
        env_root = os.environ.get("AFSIM_DEMOS_DIR")
        if env_root and Path(env_root).exists():
            return Path(env_root)
        config = self.read_config()
        cfg_root = config.get("demos_root")
        if cfg_root and Path(cfg_root).exists():
            return Path(cfg_root)
        afsim_root = self.resolve_afsim_root()
        if afsim_root:
            candidate = afsim_root / "demos"
            if candidate.exists():
                return candidate
        return None

    def tools_list(self):
        return build_tool_specs()

    def handle_request(self, request):
        method = request.get("method")
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "afsim-mcp", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        if method == "tools/list":
            return {"tools": self.tools_list()}
        if method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            return self.call_tool(name, arguments)
        return {"error": f"Unsupported method: {method}"}

    def call_tool(self, name, arguments):
        router = build_tool_router(self)
        handler = router.get(name)
        if handler:
            return handler(arguments)
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}]}

    def create_scenario(self, args):
        scenario_id = str(uuid.uuid4())
        name = args.get("name")
        if not name:
            return self.wrap({"error": "name is required"})
        scenario = {
            "id": scenario_id,
            "name": name,
            "template": args.get("base_template"),
            "entities": [],
            "rules": [],
            "metadata": {"created_at": self.now()},
        }
        self.write_json(self.scenario_path(scenario_id), scenario)
        return self.wrap({"scenario_id": scenario_id, "path": str(self.scenario_path(scenario_id))})

    def list_scenarios(self):
        items = []
        for path in sorted(self.scenarios_dir.glob("*.json")):
            data = self.read_json(path)
            items.append({"id": data.get("id"), "name": data.get("name"), "path": str(path)})
        return self.wrap({"scenarios": items})

    def load_scenario(self, args):
        path = args.get("path")
        scenario_id = args.get("scenario_id")
        if path:
            return self.wrap(self.read_json(Path(path)))
        if scenario_id:
            return self.wrap(self.read_json(self.scenario_path(scenario_id)))
        return self.wrap({"error": "path or scenario_id required"})

    def save_scenario(self, args):
        scenario_id = args.get("scenario_id")
        path = args.get("path")
        scenario = self.read_json(self.scenario_path(scenario_id))
        target = Path(path)
        self.write_json(target, scenario)
        return self.wrap({"path": str(target)})

    def create_entity(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        entity_id = str(uuid.uuid4())
        entity = {
            "id": entity_id,
            "type": args["type"],
            "name": args["name"],
            "components": [],
            "metadata": {},
        }
        scenario["entities"].append(entity)
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"entity_id": entity_id})

    def delete_entity(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        before = len(scenario["entities"])
        scenario["entities"] = [e for e in scenario["entities"] if e["id"] != args["entity_id"]]
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"removed": before - len(scenario["entities"])})

    def set_entity_param(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        updated = False
        for entity in scenario["entities"]:
            if entity["id"] == args["entity_id"]:
                params = args.get("params") or {}
                entity["metadata"].update(params)
                updated = True
                break
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"updated": updated})

    def add_component(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        component_id = str(uuid.uuid4())
        created = False
        for entity in scenario["entities"]:
            if entity["id"] == args["entity_id"]:
                entity["components"].append(
                    {
                        "id": component_id,
                        "type": args["component_type"],
                        "params": args.get("params") or {},
                    }
                )
                created = True
                break
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"component_id": component_id, "created": created})

    def update_component(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        updated = False
        for entity in scenario["entities"]:
            if entity["id"] == args["entity_id"]:
                for component in entity["components"]:
                    if component["id"] == args["component_id"]:
                        component["params"] = args.get("params") or {}
                        updated = True
                        break
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"updated": updated})

    def set_rule(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        rule = {"type": args["rule_type"], "params": args.get("params") or {}}
        scenario["rules"].append(rule)
        self.write_json(self.scenario_path(scenario["id"]), scenario)
        return self.wrap({"rules": len(scenario["rules"])})

    def validate_scenario(self, args):
        scenario = self.read_json(self.scenario_path(args["scenario_id"]))
        issues = []
        if not scenario["entities"]:
            issues.append("entities is empty")
        valid = len(issues) == 0
        return self.wrap({"valid": valid, "issues": issues})

    def read_scenario_text(self, args):
        path = Path(args["path"])
        text = self.read_text(path)
        return self.wrap({"path": str(path), "text": text})

    def write_scenario_text(self, args):
        path = Path(args["path"])
        text = args.get("text") or ""
        self.write_text(path, text)
        return self.wrap({"path": str(path)})

    def insert_scenario_block(self, args):
        path = Path(args["path"])
        anchor = args["anchor"]
        block = args["block"]
        position = args.get("position") or "after"
        occurrence = args.get("occurrence") or "first"
        text = self.read_text(path)
        idx = text.find(anchor) if occurrence == "first" else text.rfind(anchor)
        if idx == -1:
            return self.wrap({"error": "anchor not found"})
        if position == "before":
            new_text = text[:idx] + block + text[idx:]
        elif position == "replace":
            new_text = text[:idx] + block + text[idx + len(anchor) :]
        else:
            new_text = text[: idx + len(anchor)] + block + text[idx + len(anchor) :]
        self.write_text(path, new_text)
        return self.wrap({"path": str(path), "modified": True})

    def extract_includes(self, args):
        path = Path(args["path"])
        lines = self.read_text(path).splitlines()
        includes = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            if stripped.startswith("include") or stripped.startswith("include_once"):
                parts = stripped.split()
                if len(parts) >= 2:
                    includes.append(parts[1])
        return self.wrap({"path": str(path), "includes": includes})

    def search_definitions(self, args):
        kind = args["kind"]
        query = (args.get("query") or "").strip()
        max_results = int(args.get("max_results") or 200)
        roots = args.get("roots")
        default_root = self.resolve_afsim_root()
        if not default_root:
            default_root = self.base_dir.parent
        search_roots = [Path(p) for p in roots] if roots else [default_root]
        kind_map = {
            "signature": [
                "radar_signature",
                "infrared_signature",
                "visual_signature",
                "acoustic_signature",
                "laser_signature",
                "optical_signature",
                "signal_signature",
            ]
        }
        keys = kind_map.get(kind, [kind])
        results = []
        for root in search_roots:
            if not root.exists():
                continue
            for path in root.rglob("*.txt"):
                try:
                    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                except OSError:
                    continue
                for idx, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                        continue
                    for key in keys:
                        if stripped.startswith(f"{key} "):
                            parts = stripped.split()
                            if len(parts) < 2:
                                continue
                            name = parts[1]
                            if query and query not in stripped and query not in name:
                                continue
                            results.append(
                                {
                                    "name": name,
                                    "kind": key,
                                    "file": str(path),
                                    "line": idx,
                                }
                            )
                            if len(results) >= max_results:
                                return self.wrap({"matches": results})
        return self.wrap({"matches": results})

    def list_definition_kinds(self):
        return self.wrap(
            {
                "kinds": [
                    "platform_type",
                    "platform",
                    "weapon",
                    "sensor",
                    "processor",
                    "comm",
                    "router",
                    "aero",
                    "signature",
                    "weapon_effects",
                ]
            }
        )

    def generate_platform_type_template(self, args):
        name = args["name"]
        base_type = args.get("base_type") or "WSF_PLATFORM"
        icon = args.get("icon")
        mover_type = args.get("mover_type")
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"platform_type {name} {base_type}"]
        if icon:
            lines.append(f"   icon {icon}")
        if mover_type:
            lines.append(f"   mover {mover_type}")
            lines.append("   end_mover")
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_platform_type")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def generate_platform_instance_template(self, args):
        name = args["name"]
        platform_type = args["platform_type"]
        side = args.get("side")
        position = args.get("position")
        altitude = args.get("altitude")
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"platform {name} {platform_type}"]
        if side:
            lines.append(f"   side {side}")
        if position:
            if altitude:
                lines.append(f"   position {position} altitude {altitude}")
            else:
                lines.append(f"   position {position}")
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_platform")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def generate_sensor_template(self, args):
        name = args["name"]
        sensor_type = args["sensor_type"]
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"sensor {name} {sensor_type}"]
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_sensor")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def generate_weapon_template(self, args):
        name = args["name"]
        weapon_type = args["weapon_type"]
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"weapon {name} {weapon_type}"]
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_weapon")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def list_mover_types(self):
        return self.wrap(
            {
                "mover_types": [
                    "WSF_RIGID_BODY_SIX_DOF_MOVER",
                    "WSF_P6DOF_MOVER",
                    "WSF_GUIDED_MOVER",
                    "WSF_AIR_MOVER",
                    "WSF_GROUND_MOVER",
                    "WSF_NAVAL_MOVER",
                ]
            }
        )

    def generate_mover_template(self, args):
        mover_type = args["mover_type"]
        keyword = args.get("keyword") or "mover"
        body_lines = self.normalize_body_lines(args.get("body_lines"))
        lines = [f"{keyword} {mover_type}"]
        lines.extend([f"   {line}" for line in body_lines])
        lines.append("end_mover")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def list_project_structure_template(self):
        return self.wrap(
            {
                "directories": [
                    {"name": "output", "description": "运行时输出日志、事件与 AER 文件"},
                    {"name": "patterns", "description": "天线方向图等模式定义"},
                    {"name": "platforms", "description": "平台与平台类型定义"},
                    {"name": "processors", "description": "处理器与脚本定义"},
                    {"name": "scenarios", "description": "场景与平台配置"},
                    {"name": "sensors", "description": "传感器定义"},
                    {"name": "signatures", "description": "特征定义"},
                    {"name": "weapons", "description": "武器定义"},
                ],
                "notes": [
                    "目录层级没有强制要求",
                    "输入文件可以包含其他输入文件",
                    "可合并为单一文件但不推荐",
                ],
            }
        )

    def generate_project_structure_overview(self, args):
        project_name = args.get("project_name") or "projectName"
        lines = [f"{project_name}/"]
        entries = [
            ("output", "运行时输出日志、事件与 AER 文件"),
            ("patterns", "天线方向图等模式定义"),
            ("platforms", "平台与平台类型定义"),
            ("processors", "处理器与脚本定义"),
            ("scenarios", "场景与平台配置"),
            ("sensors", "传感器定义"),
            ("signatures", "特征定义"),
            ("weapons", "武器定义"),
        ]
        for name, desc in entries:
            lines.append(f"  {name}/  - {desc}")
        text = "\n".join(lines) + "\n"
        return self.wrap({"text": text})

    def init_project_structure(self, args):
        base_dir = args.get("base_dir")
        if not base_dir:
            root = self.resolve_project_root()
            if root:
                base_dir = str(root)
        if not base_dir:
            return self.wrap({"error": "base_dir is required"})
        project_name = args.get("project_name")
        target = Path(base_dir)
        if project_name:
            target = target / project_name
        target.mkdir(parents=True, exist_ok=True)
        directories = args.get("directories")
        if directories is None:
            directories = [
                "output",
                "patterns",
                "platforms",
                "processors",
                "scenarios",
                "sensors",
                "signatures",
                "weapons",
            ]
        created = []
        for name in directories:
            if not name:
                continue
            path = target / name
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))
        return self.wrap({"project_dir": str(target), "directories": created})

    def run_simulation(self, args):
        scenario_id = args["scenario_id"]
        run_id = str(uuid.uuid4())
        scenario_path = self.scenario_path(scenario_id)
        run_data = {
            "id": run_id,
            "scenario_id": scenario_id,
            "status": "created",
            "start_time": self.now(),
            "end_time": None,
            "outputs": {},
            "run_config": args.get("run_config") or {},
        }
        cmd_template = os.environ.get("AFSIM_RUN_CMD")
        if cmd_template:
            cmd = cmd_template.format(
                scenario_id=scenario_id,
                scenario_path=str(scenario_path),
                run_id=run_id,
            )
            result = run(cmd, shell=True, capture_output=True, text=True)
            run_data["outputs"] = {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            run_data["status"] = "completed" if result.returncode == 0 else "failed"
            run_data["end_time"] = self.now()
        else:
            run_data["status"] = "pending_backend"
        self.write_json(self.run_path(run_id), run_data)
        return self.wrap({"run_id": run_id, "status": run_data["status"]})

    def stop_simulation(self, args):
        return self.wrap({"stopped": False, "reason": "backend_not_connected"})

    def get_simulation_status(self, args):
        run_data = self.read_json(self.run_path(args["run_id"]))
        return self.wrap(
            {
                "run_id": run_data["id"],
                "status": run_data["status"],
                "start_time": run_data["start_time"],
                "end_time": run_data["end_time"],
            }
        )

    def list_results(self, args):
        scenario_id = args["scenario_id"]
        runs = self.get_runs(scenario_id)
        return self.wrap({"runs": runs})

    def export_results(self, args):
        scenario_id = args["scenario_id"]
        fmt = args["format"]
        runs_data = self.get_runs(scenario_id)
        if "path" in args and args["path"]:
            out_path = Path(args["path"])
        else:
            out_path = self.results_dir / f"{scenario_id}.{fmt}"
        if fmt == "json":
            self.write_json(out_path, runs_data)
        elif fmt == "csv":
            import csv

            with out_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["run_id", "status", "start_time", "end_time"]
                )
                writer.writeheader()
                writer.writerows(runs_data)
        else:
            return self.wrap({"error": "format must be csv or json"})
        return self.wrap({"file_path": str(out_path)})

    def query_results(self, args):
        scenario_id = args["scenario_id"]
        query = args["query"]
        matches = []
        for data in self.get_run_records(scenario_id):
            text = json.dumps(data, ensure_ascii=False)
            if query in text:
                matches.append({"run_id": data.get("id"), "status": data.get("status")})
        return self.wrap({"matches": matches})

    def set_afsim_bin(self, args):
        path = Path(args["path"])
        if not path.exists():
            return self.wrap({"error": "path not found"})
        config = self.read_config()
        config["afsim_bin"] = str(path)
        self.write_config(config)
        return self.wrap({"afsim_bin": str(path)})

    def get_afsim_bin(self):
        config = self.read_config()
        return self.wrap({"afsim_bin": config.get("afsim_bin")})

    def set_paths_config(self, args):
        config = self.read_config()
        updates = {
            "afsim_root": args.get("afsim_root"),
            "project_root": args.get("project_root"),
            "demos_root": args.get("demos_root"),
            "afsim_bin": args.get("afsim_bin"),
        }
        for key, value in updates.items():
            if not value:
                continue
            path = Path(value)
            if not path.exists():
                return self.wrap({"error": "path not found", "key": key, "path": str(path)})
            config[key] = str(path)
        self.write_config(config)
        return self.wrap({"config": config})

    def get_paths_config(self, args):
        config = self.read_config()
        resolved_afsim_root = self.resolve_afsim_root()
        resolved_project_root = self.resolve_project_root()
        resolved_demos_root = self.resolve_demos_root()
        resolved_bin = self.resolve_bin_path()
        return self.wrap(
            {
                "config_path": str(self.config_path),
                "config": config,
                "resolved": {
                    "afsim_root": str(resolved_afsim_root) if resolved_afsim_root else None,
                    "project_root": str(resolved_project_root) if resolved_project_root else None,
                    "demos_root": str(resolved_demos_root) if resolved_demos_root else None,
                    "afsim_bin": str(resolved_bin) if resolved_bin else None,
                    "state_dir": str(self.state_dir),
                },
            }
        )

    def run_wizard(self, args):
        wizard_path = self.resolve_wizard_path()
        if not wizard_path:
            return self.wrap({"error": "wizard path not configured"})
        cmd = [str(wizard_path)]
        if args.get("console", True):
            cmd.append("-console")
        raw_args = args.get("args") or []
        if isinstance(raw_args, list):
            cmd.extend([str(a) for a in raw_args])
        else:
            cmd.append(str(raw_args))
        working_dir = args.get("working_dir")
        result = run(
            cmd,
            capture_output=True,
            text=True,
            cwd=working_dir if working_dir else None,
        )
        return self.wrap(
            {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )

    def run_mission(self, args):
        exe = self.resolve_exe("mission")
        if not exe:
            return self.wrap({"error": "mission executable not found"})
        scenario = args.get("scenario")
        cmd = [str(exe), str(scenario)]
        return self.run_process(cmd, args.get("working_dir"))

    def run_mission_with_args(self, args):
        exe = self.resolve_exe("mission")
        if not exe:
            return self.wrap({"error": "mission executable not found"})
        scenario = args.get("scenario")
        raw_args = args.get("args") or []
        cmd = [str(exe), str(scenario)]
        if isinstance(raw_args, list):
            cmd.extend([str(a) for a in raw_args])
        else:
            cmd.append(str(raw_args))
        return self.run_process(cmd, args.get("working_dir"))

    def run_warlock(self, args):
        exe = self.resolve_exe("warlock")
        if not exe:
            return self.wrap({"error": "warlock executable not found"})
        cmd = [str(exe)]
        raw_args = args.get("args") or []
        if isinstance(raw_args, list):
            cmd.extend([str(a) for a in raw_args])
        else:
            cmd.append(str(raw_args))
        return self.run_process(cmd, args.get("working_dir"))

    def run_mystic(self, args):
        exe = self.resolve_exe("mystic")
        if not exe:
            return self.wrap({"error": "mystic executable not found"})
        cmd = [str(exe)]
        recording = args.get("recording")
        if recording:
            cmd.append(str(recording))
        return self.run_process(cmd, args.get("working_dir"))

    def run_engage(self, args):
        exe = self.resolve_exe("engage")
        if not exe:
            return self.wrap({"error": "engage executable not found"})
        cmd = [str(exe)]
        raw_args = args.get("args") or []
        if isinstance(raw_args, list):
            cmd.extend([str(a) for a in raw_args])
        else:
            cmd.append(str(raw_args))
        return self.run_process(cmd, args.get("working_dir"))

    def run_sensor_plot(self, args):
        exe = self.resolve_exe("sensor_plot")
        if not exe:
            return self.wrap({"error": "sensor_plot executable not found"})
        cmd = [str(exe)]
        raw_args = args.get("args") or []
        if isinstance(raw_args, list):
            cmd.extend([str(a) for a in raw_args])
        else:
            cmd.append(str(raw_args))
        return self.run_process(cmd, args.get("working_dir"))

    def batch_run_mission(self, args):
        exe = self.resolve_exe("mission")
        if not exe:
            return self.wrap({"error": "mission executable not found"})
        scenarios = args.get("scenarios") or []
        working_dir = args.get("working_dir")
        results = []
        for scenario in scenarios:
            result = run(
                [str(exe), str(scenario)],
                capture_output=True,
                text=True,
                cwd=working_dir if working_dir else None,
            )
            results.append(
                {
                    "scenario": str(scenario),
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
        return self.wrap({"results": results})

    def run_mission_and_open_mystic(self, args):
        scenario = args.get("scenario")
        working_dir = args.get("working_dir")
        open_mystic = args.get("open_mystic")
        if open_mystic is None:
            open_mystic = True
        scenario_path = Path(scenario)
        working_root = Path(working_dir) if working_dir else scenario_path.parent
        mission_result = self.run_mission({"scenario": scenario, "working_dir": str(working_root)})
        latest_aer = self.find_latest_aer(working_root)
        mystic_result = None
        if open_mystic and latest_aer:
            mystic_result = self.run_mystic(
                {"recording": str(latest_aer), "working_dir": str(latest_aer.parent)}
            )
        return self.wrap(
            {
                "mission": json.loads(mission_result["content"][0]["text"]),
                "latest_aer": str(latest_aer) if latest_aer else None,
                "mystic": json.loads(mystic_result["content"][0]["text"])
                if mystic_result
                else None,
            }
        )

    def open_latest_aer_in_mystic(self, args):
        directory = Path(args.get("directory"))
        latest_aer = self.find_latest_aer(directory)
        if not latest_aer:
            return self.wrap({"error": "no aer files found"})
        mystic_result = self.run_mystic(
            {"recording": str(latest_aer), "working_dir": str(latest_aer.parent)}
        )
        return self.wrap(
            {
                "latest_aer": str(latest_aer),
                "mystic": json.loads(mystic_result["content"][0]["text"]),
            }
        )

    def list_demos(self):
        demos = self.get_demos_root()
        if not demos:
            return self.wrap({"error": "demos folder not found"})
        folders = sorted([p.name for p in demos.iterdir() if p.is_dir()])
        return self.wrap({"demos": folders})

    def list_demo_scenarios(self, args):
        demos = self.get_demos_root()
        if not demos:
            return self.wrap({"error": "demos folder not found"})
        demo = args.get("demo")
        if not demo:
            return self.wrap({"error": "demo is required"})
        base = demos / demo
        if not base.exists():
            return self.wrap({"error": "demo not found"})
        scenarios = sorted([str(p) for p in base.rglob("*.txt")])
        return self.wrap({"scenarios": scenarios})

    def suggest_scenario_questions(self, args):
        prompt = args.get("prompt") or ""
        counts = self.parse_prompt_counts(prompt)
        defaults = {
            "aircraft_count": counts.get("aircraft", 2),
            "tank_count": counts.get("tank", 2),
            "side": "blue",
            "duration_min": 30,
            "center": {"lat": 21.325, "lon": -158.51},
        }
        questions = [
            {"key": "scenario_name", "question": "场景名称是什么？"},
            {"key": "mission_goal", "question": "作战目标是什么？"},
            {"key": "area_center", "question": "作战区域中心坐标（纬度/经度）是多少？"},
            {"key": "aircraft_type", "question": "飞机平台类型/型号是什么？"},
            {"key": "tank_type", "question": "坦克平台类型/型号是什么？"},
            {"key": "duration_min", "question": "仿真时长是多少分钟？"},
            {"key": "sides", "question": "各平台所属阵营？"},
        ]
        return self.wrap({"defaults": defaults, "questions": questions})

    def create_scenario_from_prompt(self, args):
        prompt = args.get("prompt") or ""
        output_path = args.get("output_path")
        if not output_path:
            return self.wrap({"error": "output_path is required"})
        output = Path(output_path)
        project_dir = args.get("project_dir")
        if project_dir and not output.is_absolute():
            output = Path(project_dir) / output
        if output.suffix == "":
            output = output.with_suffix(".txt")
        counts = self.parse_prompt_counts(prompt)
        aircraft_count = int(args.get("aircraft_count") or counts.get("aircraft") or 3)
        tank_count = int(args.get("tank_count") or counts.get("tank") or 3)
        side = args.get("side") or "blue"
        duration_min = float(args.get("duration_min") or 30)
        center = args.get("center") or {}
        lat = float(center.get("lat") or 21.325)
        lon = float(center.get("lon") or -158.51)
        text = self.generate_basic_scenario_text(
            aircraft_count=aircraft_count,
            tank_count=tank_count,
            side=side,
            duration_min=duration_min,
            center_lat=lat,
            center_lon=lon,
        )
        self.write_text(output, text)
        return self.wrap(
            {
                "path": str(output),
                "aircraft_count": aircraft_count,
                "tank_count": tank_count,
                "side": side,
                "duration_min": duration_min,
            }
        )

    def run_demo(self, args):
        demos = self.get_demos_root()
        if not demos:
            return self.wrap({"error": "demos folder not found"})
        demo = args.get("demo")
        scenario = args.get("scenario")
        if not demo or not scenario:
            return self.wrap({"error": "demo and scenario are required"})
        demo_dir = demos / demo
        if not demo_dir.exists():
            return self.wrap({"error": "demo not found"})
        scenario_path = Path(scenario)
        if not scenario_path.is_absolute():
            scenario_path = demo_dir / scenario
        mission_exe = self.resolve_exe("mission")
        if not mission_exe:
            return self.wrap({"error": "mission executable not found"})
        mission_result = self.run_process(
            [str(mission_exe), str(scenario_path)],
            str(demo_dir),
        )
        latest_aer = self.find_latest_aer(demo_dir)
        mystic_result = None
        if args.get("open_mystic") and latest_aer:
            mystic_result = self.run_mystic(
                {"recording": str(latest_aer), "working_dir": str(latest_aer.parent)}
            )
        return self.wrap(
            {
                "mission": json.loads(mission_result["content"][0]["text"]),
                "latest_aer": str(latest_aer) if latest_aer else None,
                "mystic": json.loads(mystic_result["content"][0]["text"])
                if mystic_result
                else None,
            }
        )

    def list_output_files(self, args):
        directory = Path(args.get("directory"))
        if not directory.exists():
            return self.wrap({"error": "directory not found"})
        extensions = args.get("extensions") or ["aer", "evt", "log"]
        exts = set([e.lower().lstrip(".") for e in extensions])
        files = []
        for path in directory.rglob("*"):
            if path.is_file():
                suffix = path.suffix.lower().lstrip(".")
                if suffix in exts:
                    files.append(
                        {
                            "path": str(path),
                            "size": path.stat().st_size,
                            "mtime": path.stat().st_mtime,
                        }
                    )
        files.sort(key=lambda x: x["mtime"], reverse=True)
        return self.wrap({"files": files})

    def find_latest_aer_tool(self, args):
        directory = Path(args.get("directory"))
        latest_aer = self.find_latest_aer(directory)
        return self.wrap({"path": str(latest_aer) if latest_aer else None})

    def summarize_evt(self, args):
        path = Path(args.get("path"))
        if not path.exists():
            return self.wrap({"error": "file not found"})
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        counts = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            parts = stripped.split()
            if not parts:
                continue
            key = parts[1] if parts[0].upper() == "EVENT" and len(parts) > 1 else parts[0]
            counts[key] = counts.get(key, 0) + 1
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return self.wrap(
            {
                "path": str(path),
                "line_count": len(lines),
                "event_counts": [{"event": k, "count": v} for k, v in top],
            }
        )

    def tail_text_file(self, args):
        path = Path(args.get("path"))
        if not path.exists():
            return self.wrap({"error": "file not found"})
        line_count = int(args.get("lines") or 50)
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        tail = lines[-line_count:] if line_count > 0 else []
        return self.wrap({"path": str(path), "lines": tail})

    def scenario_path(self, scenario_id):
        return self.scenarios_dir / f"{scenario_id}.json"

    def run_path(self, run_id):
        return self.runs_dir / f"{run_id}.json"

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_text(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")

    def read_text(self, path):
        return Path(path).read_text(encoding="utf-8", errors="ignore")

    def normalize_body_lines(self, lines):
        if not lines:
            return []
        normalized = []
        for line in lines:
            if line is None:
                continue
            text = str(line).strip()
            if text == "":
                continue
            normalized.append(text)
        return normalized

    def read_json(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def now(self):
        return datetime.now(timezone.utc).isoformat()

    def wrap(self, payload):
        return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}

    def run_process(self, cmd, working_dir):
        result = run(
            cmd,
            capture_output=True,
            text=True,
            cwd=working_dir if working_dir else None,
        )
        return self.wrap(
            {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )

    def resolve_exe(self, base_name):
        direct = os.environ.get(f"AFSIM_{base_name.upper()}_PATH")
        if direct and Path(direct).exists():
            return Path(direct)
        bin_path = self.resolve_bin_path()
        if bin_path:
            candidate = bin_path / f"{base_name}.exe"
            if candidate.exists():
                return candidate
            candidate = bin_path / base_name
            if candidate.exists():
                return candidate
        return None

    def resolve_bin_path(self):
        env_bin = os.environ.get("AFSIM_BIN")
        if env_bin:
            path = Path(env_bin)
            if path.exists():
                return path
        config = self.read_config()
        cfg_bin = config.get("afsim_bin")
        if cfg_bin:
            path = Path(cfg_bin)
            if path.exists():
                return path
        afsim_root = self.resolve_afsim_root()
        if afsim_root:
            candidate = afsim_root / "bin"
            if candidate.exists():
                return candidate
        repo_bin = self.base_dir.parent / "bin"
        if repo_bin.exists():
            return repo_bin
        return None

    def get_demos_root(self):
        return self.resolve_demos_root()

    def generate_basic_scenario_text(
        self, aircraft_count, tank_count, side, duration_min, center_lat, center_lon
    ):
        lines = []
        lines.append("realtime")
        lines.append(f"end_time {duration_min} min")
        lines.append("")
        for idx in range(aircraft_count):
            lat = center_lat + 0.01 * idx
            lon = center_lon + 0.01 * idx
            start_pos = self.format_lat_lon(lat, lon)
            end_pos = self.format_lat_lon(lat + 0.05, lon + 0.05)
            lines.append(f"platform aircraft_{idx+1} WSF_PLATFORM")
            lines.append("   spatial_domain air")
            lines.append(f"   side {side}")
            lines.append("   icon F-18")
            lines.append("   add mover WSF_AIR_MOVER")
            lines.append("   end_mover")
            lines.append("   route")
            lines.append(f"      position {start_pos} altitude 6000 ft speed 500 kts")
            lines.append(f"      position {end_pos} altitude 6000 ft speed 500 kts")
            lines.append("   end_route")
            lines.append("end_platform")
            lines.append("")
        for idx in range(tank_count):
            lat = center_lat - 0.02 * idx
            lon = center_lon - 0.02 * idx
            start_pos = self.format_lat_lon(lat, lon)
            end_pos = self.format_lat_lon(lat + 0.01, lon + 0.01)
            lines.append(f"platform tank_{idx+1} WSF_PLATFORM")
            lines.append(f"   side {side}")
            lines.append("   icon tank")
            lines.append("   mover WSF_GROUND_MOVER")
            lines.append("      on_ground")
            lines.append("      route")
            lines.append(f"         position {start_pos} altitude 1 m speed 20 km/hr")
            lines.append(f"         position {end_pos}")
            lines.append("         stop")
            lines.append("      end_route")
            lines.append("   end_mover")
            lines.append("end_platform")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def format_lat_lon(self, lat, lon):
        lat_suffix = "n" if lat >= 0 else "s"
        lon_suffix = "e" if lon >= 0 else "w"
        return f"{abs(lat):.3f}{lat_suffix} {abs(lon):.3f}{lon_suffix}"

    def parse_prompt_counts(self, prompt):
        text = prompt or ""
        counts = {}
        aircraft = self.extract_count(text, ["飞机", "aircraft", "飞机群"])
        tank = self.extract_count(text, ["坦克", "tank"])
        if aircraft:
            counts["aircraft"] = aircraft
        if tank:
            counts["tank"] = tank
        return counts

    def extract_count(self, text, keywords):
        for key in keywords:
            if key in text:
                num = self.find_nearest_number(text, key)
                if num:
                    return num
        return None

    def find_nearest_number(self, text, key):
        idx = text.find(key)
        if idx == -1:
            return None
        window = text[max(0, idx - 6) : idx + len(key) + 6]
        digits = "".join([c for c in window if c.isdigit()])
        if digits:
            return int(digits)
        cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        for k, v in cn_map.items():
            if k in window:
                return v
        return None

    def find_latest_aer(self, base_dir):
        candidates = list(base_dir.rglob("*.aer"))
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def read_config(self):
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def write_config(self, data):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def resolve_wizard_path(self):
        direct = os.environ.get("AFSIM_WIZARD_PATH")
        if direct and Path(direct).exists():
            return Path(direct)
        env_bin = os.environ.get("AFSIM_BIN")
        if env_bin:
            candidate = Path(env_bin) / "wizard.exe"
            if candidate.exists():
                return candidate
            candidate = Path(env_bin) / "wizard"
            if candidate.exists():
                return candidate
        bin_path = self.resolve_bin_path()
        if bin_path:
            candidate = bin_path / "wizard.exe"
            if candidate.exists():
                return candidate
            candidate = bin_path / "wizard"
            if candidate.exists():
                return candidate
        return None

    def get_runs(self, scenario_id):
        runs = []
        for data in self.get_run_records(scenario_id):
            runs.append(
                {
                    "run_id": data.get("id"),
                    "status": data.get("status"),
                    "start_time": data.get("start_time"),
                    "end_time": data.get("end_time"),
                }
            )
        return runs

    def get_run_records(self, scenario_id):
        records = []
        for path in self.runs_dir.glob("*.json"):
            data = self.read_json(path)
            if data.get("scenario_id") == scenario_id:
                records.append(data)
        return records
