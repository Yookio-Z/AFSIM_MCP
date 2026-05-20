import json
import os
import uuid
from pathlib import Path
from subprocess import DEVNULL, Popen, TimeoutExpired, run


class RuntimeService:
    def __init__(self, host):
        self.host = host

    def set_afsim_bin(self, args):
        path = Path(args["path"])
        if not path.exists():
            return self.host.wrap({"error": "path not found"})
        config = self.host.read_config()
        config["afsim_bin"] = str(path)
        self.host.write_config(config)
        return self.host.wrap({"afsim_bin": str(path)})

    def get_afsim_bin(self):
        config = self.host.read_config()
        return self.host.wrap({"afsim_bin": config.get("afsim_bin")})

    def set_paths_config(self, args):
        config = self.host.read_config()
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
                return self.host.wrap({"error": "path not found", "key": key, "path": str(path)})
            config[key] = str(path)
        self.host.write_config(config)
        return self.host.wrap({"config": config})

    def get_paths_config(self, args):
        config = self.host.read_config()
        resolved_afsim_root = self.host.resolve_afsim_root()
        resolved_project_root = self.host.resolve_project_root()
        resolved_demos_root = self.host.resolve_demos_root()
        resolved_bin = self.resolve_bin_path()
        return self.host.wrap(
            {
                "config_path": str(self.host.config_path),
                "config": config,
                "resolved": {
                    "afsim_root": str(resolved_afsim_root) if resolved_afsim_root else None,
                    "project_root": str(resolved_project_root) if resolved_project_root else None,
                    "demos_root": str(resolved_demos_root) if resolved_demos_root else None,
                    "afsim_bin": str(resolved_bin) if resolved_bin else None,
                    "state_dir": str(self.host.state_dir),
                },
            }
        )

    def run_wizard(self, args):
        wizard_path = self.resolve_wizard_path()
        if not wizard_path:
            raise self.host.JsonRpcError(-32002, "wizard executable not found", {"tool": "run_wizard"})
        cmd = [str(wizard_path)]
        if args.get("console", True):
            cmd.append("-console")
        raw_args = args.get("args") or []
        if isinstance(raw_args, list):
            cmd.extend([str(value) for value in raw_args])
        else:
            cmd.append(str(raw_args))
        working_dir = args.get("working_dir")
        if working_dir:
            self.host.assert_path_allowed(Path(working_dir), write=True, purpose="run_wizard(working_dir)")
        timeout_sec = args.get("timeout_sec")
        background = bool(args.get("background", False))
        max_output_chars = args.get("max_output_chars")
        return self.run_process(
            cmd,
            working_dir,
            timeout_sec=float(timeout_sec) if timeout_sec else None,
            background=background,
            max_output_chars=int(max_output_chars) if max_output_chars else 20000,
        )

    def run_mission(self, args):
        exe = self.resolve_exe("mission")
        if not exe:
            raise self.host.JsonRpcError(-32002, "mission executable not found", {"tool": "run_mission"})
        scenario = self.host.require_str(args, "scenario")
        scenario_path = Path(scenario)
        self.host.assert_path_allowed(scenario_path, write=False, purpose="run_mission(scenario)")
        working_dir = args.get("working_dir")
        if working_dir:
            self.host.assert_path_allowed(Path(working_dir), write=True, purpose="run_mission(working_dir)")
        else:
            working_dir = str(scenario_path.parent)
            self.host.assert_path_allowed(Path(working_dir), write=True, purpose="run_mission(default_working_dir)")
        timeout_sec = args.get("timeout_sec")
        background = bool(args.get("background", False))
        max_output_chars = args.get("max_output_chars")
        return self.run_process(
            [str(exe), str(scenario_path)],
            working_dir,
            timeout_sec=float(timeout_sec) if timeout_sec else None,
            background=background,
            max_output_chars=int(max_output_chars) if max_output_chars else 20000,
        )

    def run_mission_with_args(self, args):
        exe = self.resolve_exe("mission")
        if not exe:
            raise self.host.JsonRpcError(-32002, "mission executable not found", {"tool": "run_mission_with_args"})
        scenario = self.host.require_str(args, "scenario")
        scenario_path = Path(scenario)
        self.host.assert_path_allowed(scenario_path, write=False, purpose="run_mission_with_args(scenario)")
        raw_args = args.get("args") or []
        cmd = [str(exe), str(scenario_path)]
        if isinstance(raw_args, list):
            cmd.extend([str(value) for value in raw_args])
        else:
            cmd.append(str(raw_args))
        working_dir = args.get("working_dir")
        if working_dir:
            self.host.assert_path_allowed(Path(working_dir), write=True, purpose="run_mission_with_args(working_dir)")
        else:
            working_dir = str(scenario_path.parent)
            self.host.assert_path_allowed(Path(working_dir), write=True, purpose="run_mission_with_args(default_working_dir)")
        timeout_sec = args.get("timeout_sec")
        background = bool(args.get("background", False))
        max_output_chars = args.get("max_output_chars")
        return self.run_process(
            cmd,
            working_dir,
            timeout_sec=float(timeout_sec) if timeout_sec else None,
            background=background,
            max_output_chars=int(max_output_chars) if max_output_chars else 20000,
        )

    def run_warlock(self, args):
        return self.run_tool_executable("warlock", args, tool_name="run_warlock")

    def run_mystic(self, args):
        exe = self.resolve_exe("mystic")
        if not exe:
            raise self.host.JsonRpcError(-32002, "mystic executable not found", {"tool": "run_mystic"})
        cmd = [str(exe)]
        recording = args.get("recording")
        if recording:
            rec_path = Path(str(recording))
            self.host.assert_path_allowed(rec_path, write=False, purpose="run_mystic(recording)")
            cmd.append(str(rec_path))
        working_dir = args.get("working_dir")
        if working_dir:
            self.host.assert_path_allowed(Path(working_dir), write=True, purpose="run_mystic(working_dir)")
        timeout_sec = args.get("timeout_sec")
        background = bool(args.get("background", False))
        max_output_chars = args.get("max_output_chars")
        return self.run_process(
            cmd,
            working_dir,
            timeout_sec=float(timeout_sec) if timeout_sec else None,
            background=background,
            max_output_chars=int(max_output_chars) if max_output_chars else 20000,
        )

    def run_engage(self, args):
        return self.run_tool_executable("engage", args, tool_name="run_engage")

    def run_sensor_plot(self, args):
        return self.run_tool_executable("sensor_plot", args, tool_name="run_sensor_plot")

    def batch_run_mission(self, args):
        exe = self.resolve_exe("mission")
        if not exe:
            raise self.host.JsonRpcError(-32002, "mission executable not found", {"tool": "batch_run_mission"})
        scenarios = args.get("scenarios") or []
        if not isinstance(scenarios, list) or not all(isinstance(item, str) for item in scenarios):
            raise self.host.JsonRpcError(-32602, "Invalid params", {"reason": "scenarios must be an array of strings"})
        working_dir = args.get("working_dir")
        if working_dir:
            self.host.assert_path_allowed(Path(working_dir), write=True, purpose="batch_run_mission(working_dir)")
        results = []
        for scenario in scenarios:
            self.host.assert_path_allowed(Path(scenario), write=False, purpose="batch_run_mission(scenario)")
            result = run([str(exe), str(scenario)], capture_output=True, text=True, cwd=working_dir if working_dir else None)
            results.append(
                {
                    "scenario": str(scenario),
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
        return self.host.wrap({"results": results})

    def run_mission_and_open_mystic(self, args):
        scenario = self.host.require_str(args, "scenario")
        scenario_path = Path(scenario)
        self.host.assert_path_allowed(scenario_path, write=False, purpose="run_mission_and_open_mystic(scenario)")
        working_dir = args.get("working_dir")
        open_mystic = args.get("open_mystic")
        if open_mystic is None:
            open_mystic = True
        working_root = Path(working_dir) if working_dir else scenario_path.parent
        self.host.assert_path_allowed(working_root, write=True, purpose="run_mission_and_open_mystic(working_dir)")
        timeout_sec = args.get("timeout_sec")
        max_output_chars = args.get("max_output_chars")
        mission_result = self.run_mission(
            {
                "scenario": str(scenario_path),
                "working_dir": str(working_root),
                "timeout_sec": timeout_sec,
                "max_output_chars": max_output_chars,
            }
        )
        latest_aer = self.find_latest_aer(working_root)
        mystic_result = None
        if open_mystic and latest_aer:
            mystic_result = self.run_mystic({"recording": str(latest_aer), "working_dir": str(latest_aer.parent)})
        return self.host.wrap(
            {
                "mission": json.loads(mission_result["content"][0]["text"]),
                "latest_aer": str(latest_aer) if latest_aer else None,
                "mystic": json.loads(mystic_result["content"][0]["text"]) if mystic_result else None,
            }
        )

    def open_latest_aer_in_mystic(self, args):
        directory = Path(self.host.require_str(args, "directory"))
        self.host.assert_path_allowed(directory, write=False, purpose="open_latest_aer_in_mystic(directory)")
        latest_aer = self.find_latest_aer(directory)
        if not latest_aer:
            return self.host.wrap({"error": "no aer files found"})
        mystic_result = self.run_mystic({"recording": str(latest_aer), "working_dir": str(latest_aer.parent)})
        return self.host.wrap({"latest_aer": str(latest_aer), "mystic": json.loads(mystic_result["content"][0]["text"])})

    def get_process_status(self, args):
        process_id = self.host.require_str(args, "process_id")
        item = self.host._processes.get(process_id)
        record_path = self.host.processes_dir / f"{process_id}.json"
        if not item:
            if record_path.exists():
                record = self.host.read_json(record_path)
                record.setdefault("note", "process not in memory (server may have restarted)")
                return self.host.wrap(record)
            raise self.host.JsonRpcError(-32602, "Unknown process_id", {"process_id": process_id})
        proc = item["popen"]
        rc = proc.poll()
        record = item["record"]
        if rc is None:
            record["status"] = "running"
            record["returncode"] = None
        else:
            record["status"] = "completed" if rc == 0 else "failed"
            record["returncode"] = rc
            record["end_time"] = self.host.now()
            try:
                item["stdout_fh"].close()
            except Exception:
                pass
            try:
                item["stderr_fh"].close()
            except Exception:
                pass
            self.host._processes.pop(process_id, None)
        self.host.write_json(record_path, record)
        return self.host.wrap(record)

    def stop_process(self, args):
        process_id = self.host.require_str(args, "process_id")
        item = self.host._processes.get(process_id)
        if not item:
            raise self.host.JsonRpcError(-32602, "Unknown process_id", {"process_id": process_id})
        proc = item["popen"]
        stopped = False
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            stopped = True
        finally:
            try:
                item["stdout_fh"].close()
            except Exception:
                pass
            try:
                item["stderr_fh"].close()
            except Exception:
                pass
            self.host._processes.pop(process_id, None)
        record_path = self.host.processes_dir / f"{process_id}.json"
        if record_path.exists():
            record = self.host.read_json(record_path)
            record["status"] = "stopped"
            record["end_time"] = self.host.now()
            self.host.write_json(record_path, record)
        return self.host.wrap({"process_id": process_id, "stopped": stopped})

    def run_process(self, cmd, working_dir, *, timeout_sec=None, max_output_chars=20000, background=False, env=None):
        if background:
            record = self.start_background_process(cmd, working_dir, env=env)
            return self.host.wrap(record)
        try:
            result = run(
                cmd,
                capture_output=True,
                text=True,
                cwd=working_dir if working_dir else None,
                timeout=timeout_sec if timeout_sec else None,
                env=env,
            )
        except TimeoutExpired:
            raise self.host.JsonRpcError(
                -32001,
                "Process timeout",
                {"cmd": [str(value) for value in cmd], "working_dir": working_dir, "timeout_sec": timeout_sec},
            )
        return self.host.wrap(
            {
                "returncode": result.returncode,
                "stdout": self.host.truncate_text(result.stdout, int(max_output_chars) if max_output_chars else 0),
                "stderr": self.host.truncate_text(result.stderr, int(max_output_chars) if max_output_chars else 0),
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
        config = self.host.read_config()
        cfg_bin = config.get("afsim_bin")
        if cfg_bin:
            path = Path(cfg_bin)
            if path.exists():
                return path
        afsim_root = self.host.resolve_afsim_root()
        if afsim_root:
            candidate = afsim_root / "bin"
            if candidate.exists():
                return candidate
        repo_bin = self.host.base_dir.parent / "bin"
        if repo_bin.exists():
            return repo_bin
        return None

    def get_demos_root(self):
        return self.host.resolve_demos_root()

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

    def start_background_process(self, cmd, working_dir, *, env=None):
        process_id = str(uuid.uuid4())
        stdout_path = self.host.processes_dir / f"{process_id}.stdout.txt"
        stderr_path = self.host.processes_dir / f"{process_id}.stderr.txt"
        stdout_fh = stdout_path.open("w", encoding="utf-8", errors="ignore")
        stderr_fh = stderr_path.open("w", encoding="utf-8", errors="ignore")
        try:
            proc = Popen(
                cmd,
                cwd=working_dir if working_dir else None,
                stdout=stdout_fh,
                stderr=stderr_fh,
                stdin=DEVNULL,
                text=True,
                env=env,
            )
        except Exception:
            stdout_fh.close()
            stderr_fh.close()
            raise
        record = {
            "process_id": process_id,
            "pid": proc.pid,
            "cmd": [str(value) for value in cmd],
            "working_dir": str(working_dir) if working_dir else None,
            "start_time": self.host.now(),
            "end_time": None,
            "status": "running",
            "returncode": None,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
        self.host._processes[process_id] = {
            "popen": proc,
            "stdout_fh": stdout_fh,
            "stderr_fh": stderr_fh,
            "record": record,
        }
        self.host.write_json(self.host.processes_dir / f"{process_id}.json", record)
        return record

    def find_latest_aer(self, base_dir):
        candidates = list(Path(base_dir).rglob("*.aer"))
        if not candidates:
            return None
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[0]

    def run_tool_executable(self, base_name, args, *, tool_name):
        exe = self.resolve_exe(base_name)
        if not exe:
            raise self.host.JsonRpcError(-32002, f"{base_name} executable not found", {"tool": tool_name})
        cmd = [str(exe)]
        raw_args = args.get("args") or []
        if isinstance(raw_args, list):
            cmd.extend([str(value) for value in raw_args])
        else:
            cmd.append(str(raw_args))
        working_dir = args.get("working_dir")
        if working_dir:
            self.host.assert_path_allowed(Path(working_dir), write=True, purpose=f"{tool_name}(working_dir)")
        timeout_sec = args.get("timeout_sec")
        background = bool(args.get("background", False))
        max_output_chars = args.get("max_output_chars")
        return self.run_process(
            cmd,
            working_dir,
            timeout_sec=float(timeout_sec) if timeout_sec else None,
            background=background,
            max_output_chars=int(max_output_chars) if max_output_chars else 20000,
        )