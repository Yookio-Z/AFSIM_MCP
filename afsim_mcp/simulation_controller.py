"""Simulation control for AFSIM MCP server."""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .models import SimulationRun, SimulationStatus
from .scenario_manager import ScenarioManager

logger = logging.getLogger(__name__)


class SimulationController:
    """Controls AFSIM simulation execution."""

    def __init__(
        self,
        scenario_manager: ScenarioManager,
        afsim_binary: str = "",
        output_dir: str = "simulation_output",
    ) -> None:
        self._sm = scenario_manager
        self._afsim_binary = afsim_binary
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, SimulationRun] = {}

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_afsim_binary(self, binary_path: str) -> None:
        """Set the path to the AFSIM binary."""
        self._afsim_binary = binary_path
        logger.info("AFSIM binary set to '%s'", binary_path)

    def get_afsim_binary(self) -> str:
        """Return the currently configured AFSIM binary path."""
        return self._afsim_binary

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run_simulation(
        self,
        scenario_id: str,
        extra_args: list[str] | None = None,
        dry_run: bool = False,
    ) -> SimulationRun:
        """Start an AFSIM simulation.

        If ``dry_run`` is True (or no binary is configured), the run is
        recorded as COMPLETED immediately without invoking a subprocess.
        This is useful for testing and demo purposes.
        """
        scenario = self._sm.get_scenario(scenario_id)

        # Save the scenario to disk so AFSIM can read it
        scenario_file = self._sm.save_scenario(scenario_id)

        run = SimulationRun(
            scenario_name=scenario.name,
            scenario_file=scenario_file,
            status=SimulationStatus.IDLE,
            output_dir=str(self._output_dir / scenario.name),
        )
        self._runs[run.run_id] = run
        Path(run.output_dir).mkdir(parents=True, exist_ok=True)

        if dry_run or not self._afsim_binary:
            logger.info("Dry-run: skipping AFSIM execution for scenario '%s'", scenario.name)
            run.status = SimulationStatus.COMPLETED
            run.start_time = _now()
            run.end_time = _now()
            return run

        if not Path(self._afsim_binary).exists():
            run.status = SimulationStatus.FAILED
            run.error_message = f"AFSIM binary not found: {self._afsim_binary}"
            logger.error(run.error_message)
            return run

        cmd = [self._afsim_binary, scenario_file] + (extra_args or [])
        log_file = str(Path(run.output_dir) / "simulation.log")
        run.log_file = log_file

        try:
            with open(log_file, "w", encoding="utf-8") as lf:
                proc = subprocess.Popen(
                    cmd,
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    cwd=run.output_dir,
                )
            run.pid = proc.pid
            run.status = SimulationStatus.RUNNING
            run.start_time = _now()
            logger.info(
                "Started simulation run '%s' (pid=%d) for scenario '%s'",
                run.run_id,
                proc.pid,
                scenario.name,
            )
        except Exception as exc:
            run.status = SimulationStatus.FAILED
            run.error_message = str(exc)
            logger.exception("Failed to start simulation: %s", exc)

        return run

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def stop_simulation(self, run_id: str) -> SimulationRun:
        """Stop a running simulation."""
        run = self._get_run(run_id)
        if run.status != SimulationStatus.RUNNING:
            logger.warning("Run '%s' is not running (status=%s)", run_id, run.status)
            return run

        if run.pid is not None:
            try:
                os.kill(run.pid, 15)  # SIGTERM
                run.status = SimulationStatus.STOPPED
                run.end_time = _now()
                logger.info("Stopped simulation run '%s' (pid=%d)", run_id, run.pid)
            except ProcessLookupError:
                run.status = SimulationStatus.COMPLETED
                run.end_time = _now()
                logger.warning("Process %d already finished", run.pid)
        else:
            run.status = SimulationStatus.STOPPED
            run.end_time = _now()
        return run

    # ------------------------------------------------------------------
    # Status / Query
    # ------------------------------------------------------------------

    def get_run_status(self, run_id: str) -> dict[str, object]:
        """Return the current status of a simulation run."""
        run = self._get_run(run_id)
        # Poll the process if it was started externally
        self._refresh_status(run)
        return self._run_info(run)

    def list_runs(self) -> list[dict[str, object]]:
        """List all known simulation runs."""
        return [self._run_info(r) for r in self._runs.values()]

    def get_run(self, run_id: str) -> SimulationRun:
        """Return the SimulationRun object."""
        return self._get_run(run_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_run(self, run_id: str) -> SimulationRun:
        if run_id not in self._runs:
            raise KeyError(f"Simulation run '{run_id}' not found.")
        return self._runs[run_id]

    @staticmethod
    def _refresh_status(run: SimulationRun) -> None:
        """Check whether the OS process is still alive."""
        if run.status != SimulationStatus.RUNNING or run.pid is None:
            return
        try:
            os.kill(run.pid, 0)  # Does not kill; raises if process gone
        except ProcessLookupError:
            run.status = SimulationStatus.COMPLETED
            run.end_time = _now()

    @staticmethod
    def _run_info(run: SimulationRun) -> dict[str, object]:
        return {
            "run_id": run.run_id,
            "scenario_name": run.scenario_name,
            "scenario_file": run.scenario_file,
            "status": run.status,
            "start_time": run.start_time,
            "end_time": run.end_time,
            "pid": run.pid,
            "output_dir": run.output_dir,
            "log_file": run.log_file,
            "error_message": run.error_message,
            "result_files": run.result_files,
        }


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
