"""Tests for NLGenerator."""

import pytest

from afsim_mcp.nl_generator import NLGenerator, _extract_duration, _infer_mover
from afsim_mcp.scenario_manager import ScenarioManager


@pytest.fixture
def nlg(tmp_path):
    sm = ScenarioManager(scenarios_dir=str(tmp_path / "scenarios"))
    return NLGenerator(sm), sm


def test_generate_simple_prompt(nlg):
    gen, sm = nlg
    result = gen.generate_scenario("Create a scenario with 2 fighters over 1 hour")
    assert result["scenario_id"]
    assert result["platform_count"] >= 2
    assert result["duration_s"] == 3600.0
    assert "afsim_preview" in result
    assert result["warnings"] == []


def test_generate_with_ship(nlg):
    gen, sm = nlg
    result = gen.generate_scenario("1 ship patrolling for 30 minutes")
    assert result["platform_count"] >= 1
    assert result["duration_s"] == 30 * 60


def test_generate_with_sensors_and_weapons(nlg):
    gen, sm = nlg
    result = gen.generate_scenario("3 uav with radar and missile for 2 hours")
    assert result["platform_count"] == 3
    # Preview should include radar sensor and missile weapon
    preview = result["afsim_preview"]
    assert "wsf_radar_sensor" in preview
    assert "wsf_missile" in preview


def test_generate_no_platform_keywords(nlg):
    gen, sm = nlg
    result = gen.generate_scenario("just a generic scenario")
    assert len(result["warnings"]) > 0
    assert result["platform_count"] >= 1


def test_refine_duration(nlg):
    gen, sm = nlg
    init = gen.generate_scenario("1 fighter for 1 hour")
    sid = init["scenario_id"]
    result = gen.refine_scenario(sid, "extend to 3 hours")
    assert any("Duration" in c for c in result["changes"])
    scenario = sm.get_scenario(sid)
    assert scenario.duration_s == 3 * 3600


def test_refine_add_platforms(nlg):
    gen, sm = nlg
    init = gen.generate_scenario("1 fighter over 1 hour")
    sid = init["scenario_id"]
    before = init["platform_count"]
    result = gen.refine_scenario(sid, "add 2 more fighters")
    assert result["platform_count"] > before


def test_refine_no_match(nlg):
    gen, sm = nlg
    init = gen.generate_scenario("1 ship for 1 hour")
    sid = init["scenario_id"]
    result = gen.refine_scenario(sid, "this prompt has no recognised actions")
    assert any("No changes" in c for c in result["changes"])


def test_extract_duration_hours():
    assert _extract_duration("run for 2 hours") == 7200.0


def test_extract_duration_minutes():
    assert _extract_duration("30 minutes") == 30 * 60


def test_extract_duration_seconds():
    assert _extract_duration("60 seconds") == 60.0


def test_extract_duration_default():
    assert _extract_duration("no time info here") == 3600.0


def test_infer_mover_aircraft():
    assert _infer_mover("fighter", "") == "wsf_air_mover"


def test_infer_mover_ship():
    assert _infer_mover("ship", "") == "wsf_surface_mover"


def test_infer_mover_submarine():
    assert _infer_mover("submarine", "") == "wsf_subsurface_mover"
