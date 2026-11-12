"""`export` and `import`: the fixed header, the skip-and-report gate and the round trip."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List

HEADER = ["inspection_id", "hive_id", "inspected_on", "mite_count", "queen_status", "treatment_date", "notes"]


def read_csv(path: Path) -> List[List[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def write_csv(path: Path, rows: List[List[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)
    return path


def test_export_writes_the_fixed_header_and_every_row(run, log, workdir: Path):
    for date in ("2024-05-01", "2024-05-20", "2024-06-02"):
        assert log(date=date).returncode == 0

    result = run("export", "--csv", "out.csv")
    assert result.returncode == 0
    assert "3 inspections exported to out.csv" in result.stdout

    text = (workdir / "out.csv").read_text(encoding="utf-8")
    assert text.startswith(",".join(HEADER) + "\n")
    rows = read_csv(workdir / "out.csv")
    assert rows[0] == HEADER
    assert len(rows) == 4


def test_export_of_an_empty_ledger_is_header_only(run, workdir: Path):
    result = run("--ledger", "nothing.jsonl", "export", "--csv", "empty.csv")
    assert result.returncode == 0
    assert "0 inspections exported" in result.stdout
    assert (workdir / "empty.csv").read_text(encoding="utf-8") == ",".join(HEADER) + "\n"
    assert read_csv(workdir / "empty.csv") == [HEADER]


def test_export_quotes_commas_and_double_quotes(run, log, workdir: Path):
    notes = 'calm, but "edgy" at the entrance'
    assert log(notes=notes).returncode == 0
    assert run("export", "--csv", "out.csv").returncode == 0

    rows = read_csv(workdir / "out.csv")
    assert rows[1][6] == notes
    assert '"' in (workdir / "out.csv").read_text(encoding="utf-8")


def test_export_to_an_unwritable_path_names_path_and_reason(run):
    result = run("export", "--csv", "/proc/nope/out.csv")
    assert result.returncode == 2
    assert "/proc/nope/out.csv" in result.stderr
    assert result.stdout == ""


def test_export_to_stdout_keeps_the_report_on_stderr(run, log):
    assert log().returncode == 0
    result = run("export", "--csv", "-")
    assert result.returncode == 0
    assert result.stdout.startswith(",".join(HEADER))
    assert "1 inspections exported" in result.stderr


def test_export_without_a_target_is_a_usage_error(run):
    result = run("export")
    assert result.returncode == 2
    assert "csv: required" in result.stderr


def test_import_refuses_a_file_missing_a_required_column(run, workdir: Path, ledger: Path):
    write_csv(workdir / "bad.csv", [["hive_id", "inspected_on", "mite_count"], ["H1", "2024-05-01", "3"]])
    result = run("import", "--csv", "bad.csv")
    assert result.returncode == 2
    assert "missing required column(s): queen_status" in result.stderr
    assert not ledger.exists()


def test_import_refuses_before_writing_when_several_columns_are_missing(run, workdir: Path, ledger: Path):
    write_csv(workdir / "worse.csv", [["hive_id", "notes"], ["H1", "hi"]])
    result = run("import", "--csv", "worse.csv")
    assert result.returncode == 2
    assert "missing required column(s): inspected_on, mite_count, queen_status" in result.stderr
    assert not ledger.exists()


def test_import_skips_bad_rows_reports_their_numbers_and_exits_one(run, workdir: Path, ledger: Path, records):
    write_csv(
        workdir / "rows.csv",
        [
            HEADER,
            ["", "H1", "2024-05-01", "3", "queenright", "", "first"],
            ["", "H1", "2024-05-20", "4", "queenless", "2024-05-21", "second"],
            ["", "H9", "2024-13-01", "2", "unknown", "", "bad date"],
        ],
    )
    result = run("import", "--csv", "rows.csv")
    assert result.returncode == 1
    assert "2 inspections imported" in result.stdout
    assert "row 4: inspected_on: not a valid ISO date (YYYY-MM-DD)" in result.stderr

    stored = records(ledger)
    assert len(stored) == 2
    assert all(record["hive_id"] == "H1" for record in stored)

    listed = run("list")
    assert "H9" not in listed.stdout


def test_import_mints_ids_when_the_column_is_absent(run, workdir: Path, ledger: Path, records):
    write_csv(
        workdir / "no_id.csv",
        [
            ["hive_id", "inspected_on", "mite_count", "queen_status"],
            ["H1", "2024-05-01", "3", "queenright"],
            ["H2", "2024-05-02", "0", "virgin"],
        ],
    )
    result = run("import", "--csv", "no_id.csv")
    assert result.returncode == 0
    assert "2 inspections imported" in result.stdout
    ids = [record["inspection_id"] for record in records(ledger)]
    assert len(set(ids)) == 2
    assert all(record_id.startswith("insp-") for record_id in ids)


def test_import_of_a_header_only_file_reports_zero_and_writes_nothing(run, workdir: Path, ledger: Path):
    write_csv(workdir / "empty.csv", [HEADER])
    result = run("import", "--csv", "empty.csv")
    assert result.returncode == 0
    assert "0 inspections imported" in result.stdout
    assert not ledger.exists()


def test_round_trip_preserves_every_field(run, log, workdir: Path, records):
    notes = ['calm, 2 supers; saw 1 "drone" cell', "", "no notes here"]
    assert log(date="2024-05-01", treatment="2024-05-02", notes=notes[0]).returncode == 0
    assert log(date="2024-05-09", mites="7", queen="queenless").returncode == 0
    assert log(date="2024-06-02", mites="0", queen="Virgin", notes=notes[2]).returncode == 0
    original = records(workdir / "skepstack-ledger.jsonl")

    assert run("export", "--csv", "first.csv").returncode == 0
    assert run("--ledger", "copy.jsonl", "import", "--csv", "first.csv").returncode == 0
    assert run("--ledger", "copy.jsonl", "export", "--csv", "second.csv").returncode == 0

    first = read_csv(workdir / "first.csv")
    second = read_csv(workdir / "second.csv")
    assert first == second
    assert records(workdir / "copy.jsonl") == original

    for row in first[1:]:
        assert len(row) == 7
    assert first[1][6] == notes[0]


def test_import_is_order_independent_and_handles_crlf_and_bom(run, workdir: Path, records):
    body = (
        "\ufeffnotes,queen_status,mite_count,inspected_on,hive_id\r\n"
        '"from a spreadsheet, with a comma",queenright,5,2024-05-01,H3\r\n'
        ",unknown,2,2024-05-02,H4\r\n"
        "\r\n"
    )
    (workdir / "spreadsheet.csv").write_text(body, encoding="utf-8")

    result = run("--ledger", "ledger.jsonl", "import", "--csv", "spreadsheet.csv")
    assert result.returncode == 0
    assert "2 inspections imported" in result.stdout

    stored = records(workdir / "ledger.jsonl")
    assert stored[0]["hive_id"] == "H3"
    assert stored[0]["notes"] == "from a spreadsheet, with a comma"
    assert stored[1]["hive_id"] == "H4"
    assert stored[1]["notes"] == ""


def test_import_from_stdin(run, workdir: Path, records):
    payload = "\n".join(
        [
            ",".join(HEADER),
            ",H1,2024-05-01,3,queenright,,",
        ]
    ) + "\n"
    result = run("--ledger", "piped.jsonl", "import", "--csv", "-", stdin=payload)
    assert result.returncode == 0
    assert "1 inspections imported" in result.stdout
    assert records(workdir / "piped.jsonl")[0]["hive_id"] == "H1"


def test_exported_formulas_are_neutralised_and_still_round_trip(run, log, workdir: Path, records):
    risky = "=SUM(A1:A2)"
    assert log(notes=risky).returncode == 0
    assert run("export", "--csv", "guarded.csv").returncode == 0

    cells = read_csv(workdir / "guarded.csv")
    assert cells[1][6] == "'" + risky

    assert run("--ledger", "copy.jsonl", "import", "--csv", "guarded.csv").returncode == 0
    assert records(workdir / "copy.jsonl")[0]["notes"] == risky

    assert run("--ledger", "copy.jsonl", "export", "--csv", "again.csv").returncode == 0
    assert read_csv(workdir / "again.csv") == cells


def test_import_skips_rows_already_in_the_ledger(run, workdir: Path, records):
    rows = [HEADER, ["insp-fixed-0001", "H1", "2024-05-01", "3", "queenright", "", "first"]]
    write_csv(workdir / "once.csv", rows)
    assert run("import", "--csv", "once.csv").returncode == 0
    assert len(records(workdir / "skepstack-ledger.jsonl")) == 1

    repeat = run("import", "--csv", "once.csv")
    assert repeat.returncode == 1
    assert "row 2: inspection_id insp-fixed-0001 is already in the ledger; skipped" in repeat.stderr
    assert "0 inspections imported" in repeat.stdout
    assert len(records(workdir / "skepstack-ledger.jsonl")) == 1


def test_import_of_a_missing_file_is_a_usage_error(run):
    result = run("import", "--csv", "nope.csv")
    assert result.returncode == 2
    assert "cannot read" in result.stderr


def test_imported_rows_survive_a_reload(run, workdir: Path, records):
    assert run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright").returncode == 0
    assert run("export", "--csv", "one.csv").returncode == 0
    assert run("--ledger", "fresh.jsonl", "import", "--csv", "one.csv").returncode == 0
    assert len(records(workdir / "fresh.jsonl")) == 1
    assert len(records(workdir / "fresh.jsonl")) == 1
