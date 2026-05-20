"""Tests for ResultsHandler."""

import csv
import json
import os

import pytest

from afsim_mcp.results_handler import ResultsHandler


@pytest.fixture
def rh(tmp_path):
    return ResultsHandler(results_dir=str(tmp_path)), tmp_path


def write_csv(path, rows, headers):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_list_result_files_empty(rh):
    handler, tmp_path = rh
    files = handler.list_result_files(directory=str(tmp_path))
    assert files == []


def test_list_result_files_finds_csv(rh):
    handler, tmp_path = rh
    csv_file = tmp_path / "results.csv"
    write_csv(csv_file, [{"time": 0, "x": 1}], ["time", "x"])
    files = handler.list_result_files(directory=str(tmp_path))
    assert len(files) == 1
    assert files[0]["format"] == "csv"


def test_list_result_files_finds_evt_aer(rh):
    handler, tmp_path = rh
    (tmp_path / "data.evt").write_text("event 1\nevent 2\n")
    (tmp_path / "data.aer").write_text("archive line\n")
    files = handler.list_result_files(directory=str(tmp_path))
    assert len(files) == 2


def test_query_csv(rh):
    handler, tmp_path = rh
    csv_file = tmp_path / "tracks.csv"
    rows = [{"time": i, "x": i * 10, "y": i * 5} for i in range(10)]
    write_csv(csv_file, rows, ["time", "x", "y"])

    result = handler.query_csv(str(csv_file), max_rows=5)
    assert result["row_count"] == 5
    assert "time" in result["columns"]


def test_query_csv_column_filter(rh):
    handler, tmp_path = rh
    csv_file = tmp_path / "tracks.csv"
    rows = [{"time": i, "x": i * 10, "y": i * 5} for i in range(5)]
    write_csv(csv_file, rows, ["time", "x", "y"])

    result = handler.query_csv(str(csv_file), columns=["time", "x"])
    assert result["columns"] == ["time", "x"]
    assert "y" not in result["rows"][0]


def test_query_csv_nonexistent(rh):
    handler, _ = rh
    with pytest.raises(FileNotFoundError):
        handler.query_csv("/no/such/file.csv")


def test_query_csv_wrong_extension(rh):
    handler, tmp_path = rh
    f = tmp_path / "data.evt"
    f.write_text("not csv")
    with pytest.raises(ValueError, match=".csv"):
        handler.query_csv(str(f))


def test_query_evt(rh):
    handler, tmp_path = rh
    evt_file = tmp_path / "events.evt"
    evt_file.write_text("event 0\nevent 1\nevent 2\n")
    result = handler.query_evt(str(evt_file), max_lines=2)
    assert result["line_count"] == 2
    assert result["lines"] == ["event 0", "event 1"]


def test_query_aer(rh):
    handler, tmp_path = rh
    aer_file = tmp_path / "archive.aer"
    aer_file.write_text("line A\nline B\n")
    result = handler.query_aer(str(aer_file))
    assert result["line_count"] == 2


def test_export_csv_to_json(rh):
    handler, tmp_path = rh
    csv_file = tmp_path / "export_test.csv"
    write_csv(csv_file, [{"a": 1, "b": 2}], ["a", "b"])
    out = handler.export_to_json(str(csv_file))
    assert out.endswith(".json")
    data = json.loads(open(out).read())
    assert data[0]["a"] == "1"  # CSV values are strings


def test_export_evt_to_json(rh):
    handler, tmp_path = rh
    evt_file = tmp_path / "events.evt"
    evt_file.write_text("e1\ne2\n")
    out = handler.export_to_json(str(evt_file))
    data = json.loads(open(out).read())
    assert len(data) == 2
    assert data[0]["content"] == "e1"


def test_get_result_summary(rh):
    handler, tmp_path = rh
    (tmp_path / "a.csv").write_text("a,b\n1,2\n")
    (tmp_path / "b.evt").write_text("event\n")
    summary = handler.get_result_summary(str(tmp_path))
    assert summary["total_files"] == 2
    assert summary["by_format"]["csv"] == 1
    assert summary["by_format"]["evt"] == 1
