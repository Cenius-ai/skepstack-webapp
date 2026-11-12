"""The command surface: help, version, global --ledger, unknown flags, exit codes."""

from __future__ import annotations

from pathlib import Path


def test_help_lists_every_command_and_exits_zero(run):
    result = run("--help")
    assert result.returncode == 0
    for command in ("log", "list", "import", "export"):
        assert command in result.stdout
    assert "--ledger" in result.stdout
    assert "exit codes" in result.stdout


def test_version_exits_zero(run):
    result = run("--version")
    assert result.returncode == 0
    assert "SkepStack" in result.stdout


def test_bare_invocation_prints_help_and_exits_zero(run):
    result = run()
    assert result.returncode == 0
    assert "usage: skepstack" in result.stdout


def test_unknown_option_prints_usage_to_stderr_and_exits_two(run):
    result = run("log", "--nonsense")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "usage: skepstack" in result.stderr


def test_each_subcommand_has_help(run):
    for command in ("log", "list", "import", "export"):
        result = run(command, "--help")
        assert result.returncode == 0, command
        assert "usage: skepstack " + command in result.stdout


def test_global_ledger_option_before_and_after_the_command(run, records, workdir: Path):
    before = run("--ledger", "before.jsonl", "log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright")
    after = run("log", "--ledger", "after.jsonl", "--hive", "H2", "--date", "2024-05-02", "--mites", "2", "--queen", "queenless")
    assert before.returncode == 0 and after.returncode == 0

    assert len(records(workdir / "before.jsonl")) == 1
    assert len(records(workdir / "after.jsonl")) == 1
    assert not (workdir / "skepstack-ledger.jsonl").exists()

    listed = run("--ledger", "before.jsonl", "list")
    assert listed.returncode == 0
    assert "H1" in listed.stdout
    assert "H2" not in listed.stdout


def test_ledger_env_var_is_used_when_no_flag_is_given(run, workdir: Path, monkeypatch):
    monkeypatch.setenv("SKEPSTACK_LEDGER", "from-env.jsonl")
    result = run("log", "--hive", "H9", "--date", "2024-05-01", "--mites", "0", "--queen", "unknown")
    assert result.returncode == 0
    assert (workdir / "from-env.jsonl").exists()
    assert not (workdir / "skepstack-ledger.jsonl").exists()


def test_success_output_goes_to_stdout_and_errors_to_stderr(run):
    ok = run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "3", "--queen", "queenright")
    assert ok.returncode == 0
    assert ok.stdout.startswith("Logged insp-")
    assert ok.stderr == ""

    bad = run("log", "--hive", "H1", "--date", "2024-05-01", "--mites", "3", "--queen", "maybe")
    assert bad.returncode == 2
    assert bad.stdout == ""
    assert "queen_status:" in bad.stderr


def test_bare_invocation_reports_the_ledger_it_would_read(run, log):
    assert log(date="2024-05-01").returncode == 0
    result = run()
    assert result.returncode == 0
    assert "usage: skepstack" in result.stdout
    assert "ledger: ./skepstack-ledger.jsonl - 1 inspection across 1 hive" in result.stdout
    assert "run: skepstack list" in result.stdout


def test_bare_invocation_without_a_ledger_invites_the_first_log(run):
    result = run()
    assert result.returncode == 0
    assert "no inspections yet" in result.stdout


def test_relative_ledger_path_inside_the_working_directory_is_fine(run, workdir, records):
    result = run("--ledger", "sub/dir/ledger.jsonl", "log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright")
    assert result.returncode == 0
    assert len(records(workdir / "sub" / "dir" / "ledger.jsonl")) == 1


def test_relative_ledger_path_cannot_escape_the_working_directory(run, workdir):
    result = run("--ledger", "../escape.jsonl", "log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright")
    assert result.returncode == 2
    assert "relative path leaves the working directory" in result.stderr
    assert not (workdir.parent / "escape.jsonl").exists()


def test_absolute_ledger_path_is_honoured(run, workdir):
    ledger = workdir.parent / (workdir.name + "-absolute.jsonl")
    result = run("--ledger", str(ledger), "log", "--hive", "H1", "--date", "2024-05-01", "--mites", "1", "--queen", "queenright")
    assert result.returncode == 0
    assert ledger.exists()
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1


def test_relative_csv_path_cannot_escape_the_working_directory(run, log, workdir):
    assert log().returncode == 0
    result = run("export", "--csv", "../out.csv")
    assert result.returncode == 2
    assert "relative path leaves the working directory" in result.stderr
    assert not (workdir.parent / "out.csv").exists()

    importing = run("import", "--csv", "../rows.csv")
    assert importing.returncode == 2
    assert "relative path leaves the working directory" in importing.stderr
