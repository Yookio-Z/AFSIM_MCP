"""Tests for EntityManager."""

import pytest

from afsim_mcp.entity_manager import EntityManager
from afsim_mcp.scenario_manager import ScenarioManager


@pytest.fixture
def em(tmp_path):
    sm = ScenarioManager(scenarios_dir=str(tmp_path / "scenarios"))
    return EntityManager(sm), sm


def make_scenario(sm, name="test"):
    return sm.create_scenario(name)


def test_create_platform(em):
    mgr, sm = em
    s = make_scenario(sm)
    result = mgr.create_platform(
        s.scenario_id, "alpha", "wsf_air_vehicle", latitude=35.0, longitude=-80.0, altitude_m=10000
    )
    assert result["name"] == "alpha"
    assert result["platform_type"] == "wsf_air_vehicle"
    assert result["position"]["latitude"] == 35.0


def test_create_duplicate_platform(em):
    mgr, sm = em
    s = make_scenario(sm)
    mgr.create_platform(s.scenario_id, "alpha")
    with pytest.raises(ValueError, match="already exists"):
        mgr.create_platform(s.scenario_id, "alpha")


def test_delete_platform(em):
    mgr, sm = em
    s = make_scenario(sm)
    mgr.create_platform(s.scenario_id, "todelete")
    assert mgr.delete_platform(s.scenario_id, "todelete") is True
    assert mgr.delete_platform(s.scenario_id, "todelete") is False


def test_modify_platform(em):
    mgr, sm = em
    s = make_scenario(sm)
    mgr.create_platform(s.scenario_id, "mover_test", latitude=0.0, longitude=0.0)
    result = mgr.modify_platform(
        s.scenario_id, "mover_test", latitude=45.0, longitude=90.0, altitude_m=500
    )
    assert result["position"]["latitude"] == 45.0
    assert result["position"]["longitude"] == 90.0
    assert result["position"]["altitude_m"] == 500


def test_list_platforms(em):
    mgr, sm = em
    s = make_scenario(sm)
    mgr.create_platform(s.scenario_id, "p1")
    mgr.create_platform(s.scenario_id, "p2")
    platforms = mgr.list_platforms(s.scenario_id)
    assert len(platforms) == 2
    names = {p["name"] for p in platforms}
    assert names == {"p1", "p2"}


def test_add_mover(em):
    mgr, sm = em
    s = make_scenario(sm)
    mgr.create_platform(s.scenario_id, "craft")
    result = mgr.add_mover(s.scenario_id, "craft", mover_type="wsf_air_mover")
    assert result["component_type"] == "wsf_air_mover"


def test_add_sensor(em):
    mgr, sm = em
    s = make_scenario(sm)
    mgr.create_platform(s.scenario_id, "craft")
    result = mgr.add_sensor(s.scenario_id, "craft", sensor_type="wsf_radar_sensor")
    assert result["component_type"] == "wsf_radar_sensor"


def test_add_weapon(em):
    mgr, sm = em
    s = make_scenario(sm)
    mgr.create_platform(s.scenario_id, "craft")
    result = mgr.add_weapon(s.scenario_id, "craft", weapon_type="wsf_missile")
    assert result["component_type"] == "wsf_missile"


def test_remove_component(em):
    mgr, sm = em
    s = make_scenario(sm)
    mgr.create_platform(s.scenario_id, "craft")
    mgr.add_mover(s.scenario_id, "craft", mover_name="my_mover")
    assert mgr.remove_component(s.scenario_id, "craft", "my_mover") is True
    assert mgr.remove_component(s.scenario_id, "craft", "my_mover") is False


def test_list_components(em):
    mgr, sm = em
    s = make_scenario(sm)
    mgr.create_platform(s.scenario_id, "craft")
    mgr.add_mover(s.scenario_id, "craft", mover_name="m1")
    mgr.add_sensor(s.scenario_id, "craft", sensor_name="s1")
    comps = mgr.list_components(s.scenario_id, "craft")
    assert len(comps) == 2
    types = {c["name"] for c in comps}
    assert types == {"m1", "s1"}


def test_get_nonexistent_platform(em):
    mgr, sm = em
    s = make_scenario(sm)
    with pytest.raises(KeyError, match="not found"):
        mgr.list_components(s.scenario_id, "ghost_platform")
