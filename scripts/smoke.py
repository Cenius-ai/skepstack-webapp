#!/usr/bin/env python3
"""End-to-end smoke test for SkepStack.

Calls the same command API the CLI commands call -- validate-and-append, list,
export, import -- against a temporary directory that is removed on exit, so the
working tree is left untouched. There is no shell and no child process here: each
step is a typed function call with plain string arguments, never an assembled
command list. `demo.sh` covers the "real process in a real shell" half.

    python3 scripts/smoke.py

Exit code 0 means every step matched; 1 means a check failed.
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path
from typing import List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import skepstack  # noqa: E402  - imported after the path fix-up

SAMPLE = PROJECT_ROOT / "samples" / "sample_inspections.csv"
FIELDS = ["inspection_id", "hive_id", "inspected_on", "mite_count", "queen_status", "treatment_date", "notes"]


class SmokeFailure(Exception):
    """A smoke-check assertion failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def read_sample_rows() -> List[dict]:
    with SAMPLE.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_csv_file(path: Path) -> List[List[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def check_ledger_shape(path: Path, expected_rows: int) -> List[dict]:
    stored = skepstack.read_ledger(path)
    require(len(stored) == expected_rows, "expected {} records, found {}".format(expected_rows, len(stored)))
    for record in stored:
        require(
            list(record.keys()) == FIELDS,
            "record does not hold exactly the seven fields: {}".format(list(record.keys())),
        )
    return stored


def log_sample_rows(ledger: Path, rows: Sequence[dict]) -> None:
    """Log each sample row through the same validator and writer `log` uses."""
    for row in rows:
        fields = {
            "hive_id": row["hive_id"],
            "inspected_on": row["inspected_on"],
            "mite_count": row["mite_count"],
            "queen_status": row["queen_status"],
            "treatment_date": row.get("treatment_date") or "",
            "notes": row.get("notes") or "",
        }
        record, errors = skepstack.log_inspection(ledger, fields)
        require(not errors, "the sample row was rejected: {}".format(sorted(errors)))
        require(record is not None, "the sample row was not written")
        print(
            "logged {} for hive {} on {}".format(
                record["inspection_id"], record["hive_id"], record["inspected_on"]
            )
        )


def main() -> int:
    require(SAMPLE.exists(), "missing sample file: {}".format(SAMPLE))
    sample_rows = read_sample_rows()
    require(len(sample_rows) >= 2, "the sample needs at least two rows")

    with tempfile.TemporaryDirectory(prefix="skepstack-smoke-") as temporary:
        workdir = Path(temporary)
        first, second = sample_rows[0], sample_rows[1]
        ledger_a = workdir / "ledger-a.jsonl"

        print("== 1. log two inspections from the sample ==")
        log_sample_rows(ledger_a, [first, second])
        check_ledger_shape(ledger_a, 2)

        print("\n== 2. list them, newest first ==")
        everything, ordered_a = skepstack.list_inspections(ledger_a)
        require(len(everything) == 2, "list saw {} inspections, expected 2".format(len(everything)))
        listing_a = skepstack.render_table(ordered_a)
        print(skepstack.list_title(len(ordered_a), None))
        print(listing_a)
        dates = [record["inspected_on"] for record in ordered_a]
        require(dates == sorted(dates, reverse=True), "list is not newest first: {}".format(dates))
        require(
            all(record["inspection_id"] in listing_a for record in ordered_a),
            "the listing is missing an inspection id",
        )

        print("\n== 3. export the ledger to CSV ==")
        export_a = workdir / "export-a.csv"
        exported = skepstack.export_inspections(ledger_a, str(export_a))
        require(exported == 2, "export wrote {} rows, expected 2".format(exported))
        rows_a = read_csv_file(export_a)
        require(rows_a[0] == FIELDS, "export header is not the fixed seven columns: {}".format(rows_a[0]))
        require(len(rows_a) == 3, "export should hold a header plus two rows, found {}".format(len(rows_a)))
        print("exported {} inspections to {}".format(exported, export_a.name))

        print("\n== 4. import that CSV into a second, empty ledger ==")
        ledger_b = workdir / "ledger-b.jsonl"
        outcome_b = skepstack.import_inspections(ledger_b, str(export_a))
        for message in outcome_b.messages:
            print("  " + message)
        print("{} inspections imported".format(outcome_b.imported))
        require(outcome_b.imported == 2, "import brought in {} rows, expected 2".format(outcome_b.imported))
        require(outcome_b.skipped == 0, "import skipped {} rows, expected none".format(outcome_b.skipped))
        records_b = check_ledger_shape(ledger_b, 2)

        print("\n== 5. list the second ledger and compare with the first ==")
        _, ordered_b = skepstack.list_inspections(ledger_b)
        listing_b = skepstack.render_table(ordered_b)
        print(listing_b)
        require(
            listing_a == listing_b,
            "the two listings differ:\n--- ledger-a ---\n{}\n--- ledger-b ---\n{}".format(listing_a, listing_b),
        )

        print("\n== 6. export the second ledger and compare field for field ==")
        export_b = workdir / "export-b.csv"
        skepstack.export_inspections(ledger_b, str(export_b))
        require(
            export_a.read_text(encoding="utf-8") == export_b.read_text(encoding="utf-8"),
            "export-a.csv and export-b.csv are not identical",
        )
        for row_a, row_b in zip(read_csv_file(export_a), read_csv_file(export_b)):
            for name, cell_a, cell_b in zip(FIELDS, row_a, row_b):
                require(cell_a == cell_b, "field {} differs: {!r} != {!r}".format(name, cell_a, cell_b))
        require(
            [record["inspection_id"] for record in skepstack.read_ledger(ledger_a)]
            == [record["inspection_id"] for record in records_b],
            "inspection ids changed across the round trip",
        )

        print("\n== 7. import the whole sample into a third ledger ==")
        ledger_c = workdir / "ledger-c.jsonl"
        outcome_c = skepstack.import_inspections(ledger_c, str(SAMPLE))
        for message in outcome_c.messages:
            print("  " + message)
        print("{} inspections imported".format(outcome_c.imported))
        require(
            outcome_c.imported == len(sample_rows),
            "the sample imported {} of {} rows".format(outcome_c.imported, len(sample_rows)),
        )
        require(outcome_c.skipped == 0, "the sample skipped {} rows".format(outcome_c.skipped))
        check_ledger_shape(ledger_c, len(sample_rows))

        export_c = workdir / "export-c.csv"
        skepstack.export_inspections(ledger_c, str(export_c))
        exported_rows = read_csv_file(export_c)
        require(
            len(exported_rows) == len(sample_rows) + 1,
            "the exported sample holds {} lines, expected {}".format(len(exported_rows), len(sample_rows) + 1),
        )
        for row, source in zip(exported_rows[1:], sample_rows):
            require(row[1] == source["hive_id"], "hive_id lost: {!r}".format(row[1]))
            require(row[2] == source["inspected_on"], "inspected_on lost: {!r}".format(row[2]))
            require(row[3] == source["mite_count"], "mite_count lost: {!r}".format(row[3]))
            require(row[4] == source["queen_status"], "queen_status lost: {!r}".format(row[4]))
            require(row[5] == source["treatment_date"], "treatment_date lost: {!r}".format(row[5]))
            require(row[6] == source["notes"], "notes lost: {!r}".format(row[6]))

        print("")
        print("SMOKE OK: log, list, export, import and the field-for-field round trip all match.")
        print("temporary directory {} removed".format(temporary))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SmokeFailure as failure:
        print("SMOKE FAILED: {}".format(failure), file=sys.stderr)
        sys.exit(1)
