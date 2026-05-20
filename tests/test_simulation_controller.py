"""Tests for SimulationController."""

import pytest

from afsim_mcp.models import SimulationStatus
from afsim_mcp.scenario_manager import ScenarioManager
from afsim_mcp.simulation_controller import SimulationController


@pytest.fixture
def sc(tmp_path):
    sm = ScenarioManager(scenarios_dir=str(tmp_path / "scenarios"))
    controller = SimulationController(sm, output_dir=str(tmp_path / "output"))
    scenario = sm.create_scenario("run_test")
    return controller, sm, scenario


def test_dry_run_completes(sc):
    controller, sm, scenario = sc
    run = controller.run_simulation(scenario.scenario_id, dry_run=True)
    assert run.status == SimulationStatus.COMPLETED
    assert run.run_id


def test_run_no_binary(sc):
    """Without binary configured, defaults to dry-run behaviour (COMPLETED)."""
    controller, sm, scenario = sc
    run = controller.run_simulation(scenario.scenario_id)
    assert run.status == SimulationStatus.COMPLETED


def test_run_invalid_binary(sc, tmp_path):
    controller, sm, scenario = sc
    controller.set_afsim_binary("/nonexistent/afsim_binary")
    run = controller.run_simulation(scenario.scenario_id, dry_run=False)
    assert run.status == SimulationStatus.FAILED
    assert "not found" in run.error_message.lower()


def test_stop_non_running(sc):
    controller, sm, scenario = sc
    run = controller.run_simulation(scenario.scenario_id, dry_run=True)
    # Already COMPLETED; stopping should not crash
    result = controller.stop_simulation(run.run_id)
    assert result.status in (SimulationStatus.COMPLETED, SimulationStatus.STOPPED)


def test_get_run_status(sc):
    controller, sm, scenario = sc
    run = controller.run_simulation(scenario.scenario_id, dry_run=True)
    status = controller.get_run_status(run.run_id)
    assert status["run_id"] == run.run_id
    assert status["status"] == SimulationStatus.COMPLETED


def test_list_runs(sc):
    controller, sm, scenario = sc
    controller.run_simulation(scenario.scenario_id, dry_run=True)
    controller.run_simulation(scenario.scenario_id, dry_run=True)
    runs = controller.list_runs()
    assert len(runs) == 2


def test_get_unknown_run(sc):
    controller, _, _ = sc
    with pytest.raises(KeyError):
        controller.get_run_status("does-not-exist")


def test_set_and_get_binary(sc):
    controller, _, _ = sc
    controller.set_afsim_binary("/opt/afsim/bin/wsf_warlock")
    assert controller.get_afsim_binary() == "/opt/afsim/bin/wsf_warlock"
