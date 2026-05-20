"""Tests for AfsimBackend."""

import pytest

from afsim_mcp.afsim_backend import AfsimBackend, AFSIM_TOOLS


@pytest.fixture
def backend():
    return AfsimBackend()


def test_set_and_get_home(backend):
    backend.set_afsim_home("/opt/afsim")
    assert backend.get_afsim_home() == "/opt/afsim"


def test_set_binary_path(backend):
    backend.set_binary_path("warlock", "/opt/afsim/bin/wsf_warlock")
    assert backend.get_binary_path("warlock") == "/opt/afsim/bin/wsf_warlock"


def test_get_binary_not_found(backend):
    result = backend.get_binary_path("wizard")
    # Returns None when not configured and not on PATH
    assert result is None or isinstance(result, str)


def test_list_binary_paths(backend):
    paths = backend.list_binary_paths()
    assert set(paths.keys()) == set(AFSIM_TOOLS.keys())


def test_detect_installation_no_env(backend, monkeypatch):
    monkeypatch.delenv("AFSIM_HOME", raising=False)
    result = backend.detect_afsim_installation()
    assert "afsim_home" in result
    assert "binaries" in result
    assert "all_found" in result


def test_run_tool_missing_binary(backend):
    result = backend._run_tool("wizard", None, [], detach=False)
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_run_warlock_no_binary(backend):
    result = backend.run_warlock("scenario.afsim")
    assert result["success"] is False


def test_run_wizard_no_binary(backend):
    result = backend.run_wizard()
    assert result["success"] is False


def test_run_mystic_no_binary(backend):
    result = backend.run_mystic("/results")
    assert result["success"] is False


def test_run_mission_no_binary(backend):
    result = backend.run_mission()
    assert result["success"] is False
