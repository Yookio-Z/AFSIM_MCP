"""Tests for ScenarioManager."""

import json
import os
import tempfile

import pytest

from afsim_mcp.scenario_manager import ScenarioManager


@pytest.fixture
def tmp_sm(tmp_path):
    return ScenarioManager(scenarios_dir=str(tmp_path / "scenarios"))


def test_create_scenario(tmp_sm):
    s = tmp_sm.create_scenario("test_scenario", description="A test", duration_s=1800)
    assert s.name == "test_scenario"
    assert s.description == "A test"
    assert s.duration_s == 1800
    assert s.scenario_id


def test_create_scenario_empty_name(tmp_sm):
    with pytest.raises(ValueError, match="empty"):
        tmp_sm.create_scenario("")


def test_list_scenarios(tmp_sm):
    tmp_sm.create_scenario("alpha")
    tmp_sm.create_scenario("beta")
    listing = tmp_sm.list_scenarios()
    names = {s["name"] for s in listing}
    assert names == {"alpha", "beta"}


def test_delete_scenario(tmp_sm):
    s = tmp_sm.create_scenario("to_delete")
    assert tmp_sm.delete_scenario(s.scenario_id)
    assert not tmp_sm.delete_scenario(s.scenario_id)  # already gone
    assert len(tmp_sm.list_scenarios()) == 0


def test_get_scenario_not_found(tmp_sm):
    with pytest.raises(KeyError):
        tmp_sm.get_scenario("nonexistent-id")


def test_save_and_load_afsim(tmp_sm, tmp_path):
    s = tmp_sm.create_scenario("save_test", duration_s=600)
    saved = tmp_sm.save_scenario(s.scenario_id)
    assert os.path.exists(saved)
    content = open(saved).read()
    assert "simulation_duration" in content
    assert "save_test" in content

    # Load back
    s2 = tmp_sm.load_scenario_file(saved)
    assert s2.name == "save_test"
    assert s2.file_path == saved


def test_save_and_load_json(tmp_sm, tmp_path):
    from afsim_mcp.models import Platform, Position

    s = tmp_sm.create_scenario("json_test", duration_s=300)
    s.platforms.append(
        Platform(name="p1", position=Position(latitude=10, longitude=20, altitude_m=500))
    )
    saved = tmp_sm.save_scenario_json(s.scenario_id)
    assert os.path.exists(saved)

    s2 = tmp_sm.load_scenario_json(saved)
    assert s2.name == "json_test"
    assert len(s2.platforms) == 1
    assert s2.platforms[0].name == "p1"


def test_validate_scenario_valid(tmp_sm):
    s = tmp_sm.create_scenario("valid_s", duration_s=3600, time_step_s=1.0)
    result = tmp_sm.validate_scenario(s.scenario_id)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_scenario_invalid_duration(tmp_sm):
    s = tmp_sm.create_scenario("bad_dur")
    s.duration_s = -1
    result = tmp_sm.validate_scenario(s.scenario_id)
    assert result["valid"] is False
    assert any("duration" in e.lower() for e in result["errors"])


def test_validate_scenario_duplicate_platforms(tmp_sm):
    from afsim_mcp.models import Platform

    s = tmp_sm.create_scenario("dup_test")
    s.platforms = [Platform(name="p1"), Platform(name="p1")]
    result = tmp_sm.validate_scenario(s.scenario_id)
    assert result["valid"] is False
    assert any("duplicate" in e.lower() for e in result["errors"])


def test_load_nonexistent_file(tmp_sm):
    with pytest.raises(FileNotFoundError):
        tmp_sm.load_scenario_file("/nonexistent/path/file.afsim")


def test_list_scenario_files(tmp_sm):
    s = tmp_sm.create_scenario("file_list_test")
    tmp_sm.save_scenario(s.scenario_id)
    tmp_sm.save_scenario_json(s.scenario_id)
    files = tmp_sm.list_scenario_files()
    assert any(f.endswith(".afsim") for f in files)
    assert any(f.endswith(".json") for f in files)
