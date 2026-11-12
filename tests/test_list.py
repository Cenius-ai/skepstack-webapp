"""`list`: newest-first ordering, the --hive filter, the empty states and the error state."""

from __future__ import annotations

EMPTY_HINT = "No inspections yet."
EXAMPLE = "skepstack log --hive H1 --date 2024-05-01 --mites 0 --queen queenright"


def test_newest_first_with_every_field_visible(run, log):
    assert log(hive="H1", date="2024-05-01").returncode == 0
    assert log(hive="H2", date="2024-05-20").returncode == 0
    assert log(hive="H1", date="2024-06-02").returncode == 0

    result = run("list")
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    data_rows = [line for line in lines if line.startswith("\u2502 insp-")]
    assert len(data_rows) == 3

    dates = [row.split("\u2502")[3].strip() for row in data_rows]
    assert dates == ["2024-06-02", "2024-05-20", "2024-05-01"]

    header = lines[2]
    for column in ("inspection_id", "hive_id", "inspected_on", "mites", "queen", "treatment", "notes"):
        assert column in header


def test_same_day_ties_break_by_most_recently_written(run, log):
    assert log(date="2024-05-01", hive="H1", notes="first write").returncode == 0
    assert log(date="2024-05-01", hive="H2", notes="second write").returncode == 0

    result = run("list")
    assert result.stdout.index("second write") < result.stdout.index("first write")


def test_hive_filter_shows_only_that_hive(run, log):
    assert log(hive="H1", date="2024-05-01").returncode == 0
    assert log(hive="H2", date="2024-05-20").returncode == 0
    assert log(hive="H1", date="2024-06-02").returncode == 0

    result = run("list", "--hive", "H1")
    assert result.returncode == 0
    data_rows = [line for line in result.stdout.splitlines() if line.startswith("\u2502 insp-")]
    assert len(data_rows) == 2
    assert "H2" not in result.stdout
    assert data_rows[0].index("2024-06-02") > 0


def test_row_shows_mite_count_status_treatment_and_notes(run, log):
    assert log(date="2024-05-07", mites="7", queen="queenless", treatment="2024-05-03", notes="treated with oxalic").returncode == 0
    result = run("list")
    assert result.returncode == 0
    row = next(line for line in result.stdout.splitlines() if line.startswith("\u2502 insp-"))
    assert " 7 " in row
    assert "queenless" in row
    assert "2024-05-03" in row
    assert "treated with oxalic" in row
    assert "H1" in row


def test_absent_treatment_date_and_notes_render_as_dash(run, log):
    assert log(date="2024-05-01").returncode == 0
    result = run("list")
    cells = [cell.strip() for cell in result.stdout.splitlines()[-2].split("\u2502")]
    assert cells[-3] == "-"
    assert cells[-2] == "-"


def test_empty_ledger_invites_the_first_inspection(run):
    result = run("list")
    assert result.returncode == 0
    assert EMPTY_HINT in result.stdout
    assert EXAMPLE in result.stdout
    assert "python3 skepstack.py log --hive H1 --date 2024-05-01 --mites 0 --queen queenright" in result.stdout


def test_filter_matching_nothing_exits_zero(run, log):
    assert log(hive="H1").returncode == 0
    result = run("list", "--hive", "H2")
    assert result.returncode == 0
    assert "No inspections for hive H2." in result.stdout


def test_invalid_hive_filter_exits_two(run):
    result = run("list", "--hive", "h 1!")
    assert result.returncode == 2
    assert "hive_id: use 1-32 letters, digits, hyphens or underscores" in result.stderr
    assert result.stdout == ""


def test_empty_hive_filter_exits_two(run):
    result = run("list", "--hive", "   ")
    assert result.returncode == 2
    assert "hive_id: required" in result.stderr


def test_list_streams_to_stdout_so_it_pipes(run, log):
    assert log(date="2024-05-01").returncode == 0
    result = run("list")
    assert result.stderr == ""
    assert result.stdout.strip() != ""


def test_long_notes_are_shortened_and_flagged(run, log):
    notes = "a very long observation " * 8
    assert log(date="2024-05-01", notes=notes).returncode == 0
    result = run("list")
    assert result.returncode == 0
    assert "notes longer than 60 characters are shortened" in result.stdout
    assert "\u2026" in result.stdout
