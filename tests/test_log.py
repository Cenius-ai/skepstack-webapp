"""`log`: the shared validator, the seven-field record, and append-only writes."""

from __future__ import annotations

import json
from pathlib import Path


def test_log_writes_one_record_with_exactly_the_seven_fields(run, ledger: Path, records):
    result = run(
        "log",
        "--hive",
        "H1",
        "--date",
        "2024-05-01",
        "--mites",
        "3",
        "--queen",
        "queenright",
        "--notes",
        "calm, 2 supers",
    )
    assert result.returncode == 0
    assert result.stdout.startswith("Logged insp-")
    assert "for hive H1 on 2024-05-01" in result.stdout

    stored = records(ledger)
    assert len(stored) == 1
    record = stored[0]
    assert list(record) == [
        "inspection_id",
        "hive_id",
        "inspected_on",
        "mite_count",
        "queen_status",
        "treatment_date",
        "notes",
    ]
    assert record["inspection_id"].startswith("insp-")
    assert record["hive_id"] == "H1"
    assert record["inspected_on"] == "2024-05-01"
    assert record["mite_count"] == 3
    assert record["queen_status"] == "queenright"
    assert record["treatment_date"] == ""
    assert record["notes"] == "calm, 2 supers"


def test_ledger_file_is_created_on_the_first_successful_save(run, ledger: Path, records):
    assert not ledger.exists()
    assert run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "0", "--queen", "unknown").returncode == 0
    assert ledger.exists()
    assert len(records(ledger)) == 1
    assert ledger.read_text(encoding="utf-8").endswith("\n")


def test_earlier_lines_are_byte_for_byte_unchanged_when_more_are_logged(run, ledger: Path, records):
    for date in ("2024-05-01", "2024-05-02"):
        assert run("log", "--hive", "H1", "--date", date, "--mites", "1", "--queen", "queenright").returncode == 0
    first_two = ledger.read_text(encoding="utf-8")

    assert run("log", "--hive", "H1", "--date", "2024-05-03", "--mites", "2", "--queen", "queenless").returncode == 0
    after = ledger.read_text(encoding="utf-8")

    assert after.startswith(first_two)
    stored = records(ledger)
    assert [record["inspected_on"] for record in stored] == ["2024-05-01", "2024-05-02", "2024-05-03"]


def test_inspection_ids_are_unique_across_rapid_writes(run, ledger: Path, records):
    for _ in range(8):
        assert run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright").returncode == 0
    ids = [record["inspection_id"] for record in records(ledger)]
    assert len(ids) == len(set(ids)) == 8
    assert all(record_id.startswith("insp-") for record_id in ids)


def test_invalid_date_writes_nothing(run, ledger: Path):
    result = run("log", "--hive", "H1", "--date", "2024-13-01", "--mites", "1", "--queen", "queenright")
    assert result.returncode == 2
    assert "inspected_on: not a valid ISO date (YYYY-MM-DD)" in result.stderr
    assert not ledger.exists()


def test_non_iso_date_shape_is_rejected(run, ledger: Path):
    result = run("log", "--hive", "H1", "--date", "2024-5-1", "--mites", "1", "--queen", "queenright")
    assert result.returncode == 2
    assert "inspected_on:" in result.stderr
    assert not ledger.exists()


def test_negative_mite_count_leaves_the_ledger_untouched(run, log, ledger: Path, records):
    assert log(date="2024-05-01").returncode == 0
    assert log(date="2024-05-02").returncode == 0
    before = ledger.read_text(encoding="utf-8")

    result = log(mites="-2")
    assert result.returncode == 2
    assert "mite_count: must be a whole number 0 or greater" in result.stderr
    assert ledger.read_text(encoding="utf-8") == before
    assert len(records(ledger)) == 2


def test_non_numeric_mite_count_is_rejected(run, ledger: Path):
    result = run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "three", "--queen", "queenright")
    assert result.returncode == 2
    assert "mite_count: must be a whole number 0 or greater" in result.stderr
    assert not ledger.exists()


def test_omitted_hive_reports_a_field_error_not_a_usage_dump(run, ledger: Path):
    result = run("log", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright")
    assert result.returncode == 2
    assert "hive_id: required" in result.stderr
    assert "usage:" not in result.stderr
    assert not ledger.exists()


def test_malformed_hive_id_is_rejected(run, ledger: Path):
    result = run("log", "--hive", "h 1!", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright")
    assert result.returncode == 2
    assert "hive_id: use 1-32 letters, digits, hyphens or underscores" in result.stderr
    assert not ledger.exists()


def test_invalid_queen_status_is_rejected(run, ledger: Path):
    result = run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "maybe")
    assert result.returncode == 2
    assert "queen_status: must be one of queenright, queenless, virgin, unknown" in result.stderr
    assert not ledger.exists()


def test_one_error_line_per_bad_field_and_no_write(run, ledger: Path):
    result = run("log", "--hive", "", "--date", "2024-13-01", "--mites", "-2", "--queen", "maybe")
    assert result.returncode == 2
    error_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(error_lines) == 4
    assert error_lines[0] == "hive_id: required"
    assert error_lines[1].startswith("inspected_on:")
    assert error_lines[2].startswith("mite_count:")
    assert error_lines[3].startswith("queen_status:")
    assert not ledger.exists()


def test_queen_status_is_case_insensitive_and_stored_lowercase(run, ledger: Path, records):
    assert run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "QueenLess").returncode == 0
    assert records(ledger)[0]["queen_status"] == "queenless"


def test_notes_with_punctuation_are_stored_verbatim(run, ledger: Path, records):
    notes = "calm bees, 2 supers; saw 1 drone cell"
    assert run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright", "--notes", notes).returncode == 0
    assert records(ledger)[0]["notes"] == notes


def test_treatment_date_is_stored_and_optional(run, log, ledger: Path, records):
    assert log(date="2024-05-01").returncode == 0
    assert log(date="2024-05-02", treatment="2024-05-03").returncode == 0
    stored = records(ledger)
    assert stored[0]["treatment_date"] == ""
    assert stored[1]["treatment_date"] == "2024-05-03"


def test_invalid_treatment_date_is_rejected(run, ledger: Path):
    result = run(
        "log",
        "--hive",
        "H1",
        "--date",
        "2024-05-01",
        "--mites",
        "1",
        "--queen",
        "queenright",
        "--treatment-date",
        "2024-02-30",
    )
    assert result.returncode == 2
    assert "treatment_date: not a valid ISO date (YYYY-MM-DD)" in result.stderr
    assert not ledger.exists()


def test_notes_longer_than_500_characters_are_rejected(run, ledger: Path):
    result = run(
        "log",
        "--hive",
        "H1",
        "--date",
        "2024-05-01",
        "--mites",
        "1",
        "--queen",
        "queenright",
        "--notes",
        "x" * 501,
    )
    assert result.returncode == 2
    assert "notes: must be 500 characters or fewer" in result.stderr
    assert not ledger.exists()


def test_ledger_line_is_a_single_json_object_per_line(run, ledger: Path):
    assert run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright").returncode == 0
    assert run("log", "--hive", "H1", "--date", "2024-05-02", "--mites", "2", "--queen", "queenright").returncode == 0
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        assert isinstance(json.loads(line), dict)
