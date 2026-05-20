import csv
import json
import os
import uuid
from pathlib import Path
from subprocess import run


class ResultsService:
    def __init__(self, host):
        self.host = host

    def run_simulation(self, args):
        scenario_id = args["scenario_id"]
        run_id = str(uuid.uuid4())
        run_config = args.get("run_config") if isinstance(args.get("run_config"), dict) else {}
        scenario_path = self.resolve_runtime_scenario_path(args, run_config)
        run_data = {
            "id": run_id,
            "scenario_id": scenario_id,
            "status": "created",
            "start_time": self.host.now(),
            "end_time": None,
            "outputs": {},
            "run_config": run_config,
            "scenario_path": str(scenario_path) if scenario_path else None,
            "working_dir": None,
            "process_id": None,
        }
        if scenario_path:
            self.host.assert_path_allowed(scenario_path, write=False, purpose="run_simulation(scenario)")
            working_dir = self.resolve_working_dir(args, run_config, scenario_path)
            self.host.assert_path_allowed(working_dir, write=True, purpose="run_simulation(working_dir)")
            run_data["working_dir"] = str(working_dir)
            mission_exe = self.host.resolve_exe("mission")
            if mission_exe:
                cmd = [str(mission_exe), str(scenario_path)]
                extra_args = self.normalize_cmd_args(run_config.get("args"))
                cmd.extend(extra_args)
                timeout_sec = self.get_numeric_option(args, run_config, "timeout_sec")
                max_output_chars = int(self.get_numeric_option(args, run_config, "max_output_chars", default=20000) or 20000)
                background = bool(args.get("background", run_config.get("background", False)))
                result_payload = json.loads(
                    self.host.run_process(
                        cmd,
                        str(working_dir),
                        timeout_sec=float(timeout_sec) if timeout_sec else None,
                        max_output_chars=max_output_chars,
                        background=background,
                    )["content"][0]["text"]
                )
                run_data["outputs"] = result_payload
                if background:
                    run_data["status"] = "running"
                    run_data["process_id"] = result_payload.get("process_id")
                else:
                    returncode = result_payload.get("returncode")
                    run_data["status"] = "completed" if returncode == 0 else "failed"
                    run_data["end_time"] = self.host.now()
                self.host.write_json(self.host.run_path(run_id), run_data)
                return self.host.wrap(
                    {
                        "run_id": run_id,
                        "status": run_data["status"],
                        "scenario_path": run_data["scenario_path"],
                        "working_dir": run_data["working_dir"],
                        "process_id": run_data.get("process_id"),
                    }
                )

        cmd_template = os.environ.get("AFSIM_RUN_CMD")
        if cmd_template and scenario_path:
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
            run_data["end_time"] = self.host.now()
        else:
            run_data["status"] = "pending_backend"
        self.host.write_json(self.host.run_path(run_id), run_data)
        return self.host.wrap(
            {
                "run_id": run_id,
                "status": run_data["status"],
                "scenario_path": run_data["scenario_path"],
                "working_dir": run_data["working_dir"],
            }
        )

    def stop_simulation(self, args):
        run_data = self.host.read_json(self.host.run_path(args["run_id"]))
        process_id = run_data.get("process_id")
        if not process_id:
            return self.host.wrap({"run_id": run_data.get("id"), "stopped": False, "reason": "no_active_process"})
        stop_payload = json.loads(self.host.stop_process({"process_id": process_id})["content"][0]["text"])
        run_data["status"] = "stopped" if stop_payload.get("stopped") else run_data.get("status")
        run_data["end_time"] = self.host.now()
        self.host.write_json(self.host.run_path(run_data["id"]), run_data)
        return self.host.wrap({"run_id": run_data.get("id"), "process_id": process_id, "stopped": bool(stop_payload.get("stopped"))})

    def get_simulation_status(self, args):
        run_data = self.host.read_json(self.host.run_path(args["run_id"]))
        process_id = run_data.get("process_id")
        if process_id and run_data.get("status") in ("created", "running"):
            process_payload = json.loads(self.host.get_process_status({"process_id": process_id})["content"][0]["text"])
            status = process_payload.get("status") or run_data.get("status")
            if status != run_data.get("status"):
                run_data["status"] = status
            if process_payload.get("returncode") is not None:
                run_data.setdefault("outputs", {})["returncode"] = process_payload.get("returncode")
            if process_payload.get("stdout_path"):
                run_data.setdefault("outputs", {})["stdout_path"] = process_payload.get("stdout_path")
            if process_payload.get("stderr_path"):
                run_data.setdefault("outputs", {})["stderr_path"] = process_payload.get("stderr_path")
            run_data["end_time"] = process_payload.get("end_time") or run_data.get("end_time")
            self.host.write_json(self.host.run_path(run_data["id"]), run_data)
        return self.host.wrap(
            {
                "run_id": run_data["id"],
                "status": run_data["status"],
                "start_time": run_data["start_time"],
                "end_time": run_data["end_time"],
                "process_id": process_id,
                "scenario_path": run_data.get("scenario_path"),
                "working_dir": run_data.get("working_dir"),
            }
        )

    def list_results(self, args):
        scenario_id = args["scenario_id"]
        runs = self.get_runs(scenario_id)
        return self.host.wrap({"runs": runs})

    def export_results(self, args):
        scenario_id = args["scenario_id"]
        fmt = args["format"]
        runs_data = self.get_runs(scenario_id)
        if "path" in args and args["path"]:
            out_path = Path(args["path"])
        else:
            out_path = self.host.results_dir / f"{scenario_id}.{fmt}"
        self.host.assert_path_allowed(out_path, write=True, purpose="export_results")
        if fmt == "json":
            self.host.write_json(out_path, runs_data)
        elif fmt == "csv":
            with out_path.open("w", newline="", encoding="utf-8") as file_handle:
                writer = csv.DictWriter(
                    file_handle, fieldnames=["run_id", "status", "start_time", "end_time"]
                )
                writer.writeheader()
                writer.writerows(runs_data)
        else:
            return self.host.wrap({"error": "format must be csv or json"})
        return self.host.wrap({"file_path": str(out_path)})

    def query_results(self, args):
        scenario_id = args["scenario_id"]
        query = args["query"]
        matches = []
        for data in self.get_run_records(scenario_id):
            text = json.dumps(data, ensure_ascii=False)
            if query in text:
                matches.append({"run_id": data.get("id"), "status": data.get("status")})
        return self.host.wrap({"matches": matches})

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
        for path in self.host.runs_dir.glob("*.json"):
            data = self.host.read_json(path)
            if data.get("scenario_id") == scenario_id:
                records.append(data)
        return records

    def resolve_runtime_scenario_path(self, args, run_config):
        candidates = []
        for value in (
            args.get("scenario"),
            args.get("scenario_path"),
            run_config.get("scenario"),
            run_config.get("scenario_path"),
        ):
            if value:
                candidates.append(Path(str(value)))

        scenario_id = str(args.get("scenario_id") or "").strip()
        if scenario_id:
            candidates.extend(
                [
                    self.host.state_dir / "scenarios" / scenario_id / f"{scenario_id}.txt",
                    self.host.state_dir / "scenarios" / scenario_id / "scenarios" / f"{scenario_id}.txt",
                ]
            )
            project_root = self.host.resolve_project_root()
            if project_root:
                candidates.extend(
                    [
                        Path(project_root) / scenario_id / f"{scenario_id}.txt",
                        Path(project_root) / scenario_id / "scenarios" / f"{scenario_id}.txt",
                    ]
                )

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def resolve_working_dir(self, args, run_config, scenario_path):
        working_dir = args.get("working_dir") or run_config.get("working_dir")
        if working_dir:
            return Path(str(working_dir))
        return Path(scenario_path).parent

    def normalize_cmd_args(self, raw_args):
        if raw_args is None:
            return []
        if isinstance(raw_args, list):
            return [str(value) for value in raw_args]
        return [str(raw_args)]

    def get_numeric_option(self, args, run_config, key, default=None):
        value = args.get(key)
        if value is None:
            value = run_config.get(key, default)
        return value