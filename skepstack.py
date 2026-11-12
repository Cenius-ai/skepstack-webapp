#!/usr/bin/env python3
"""SkepStack - an offline, append-only ledger of beehive inspections.

One file, standard library only, Python 3.9+. No install step:

    python3 skepstack.py log --hive H1 --date 2024-05-01 --mites 3 --queen queenright
    python3 skepstack.py list --hive H1
    python3 skepstack.py export --csv inspections.csv
    python3 skepstack.py import --csv inspections.csv

Design source of truth (terminal dark, calm-precise, monospace, compact):
THEME below holds the one accent (oklch(0.58 0.12 151) / #3a8e54) and the
neutral foreground ramp. See DESIGN.md.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

__version__ = "1.0.0"

# --- design tokens (the only place colour is decided) ----------------------
THEME = {
    "accent": "#3a8e54",  # oklch(0.58 0.12 151)
    "accent_ansi": "38;2;58;142;84",
    "accent_strong_ansi": "1;38;2;58;142;84",
    "strong_ansi": "1;38;2;226;230;228",
    "text_ansi": "38;2;226;230;228",
    "muted_ansi": "38;2;138;148;143",
    "border_ansi": "38;2;88;100;94",
}

USE_COLOR = False

# --- contract constants ----------------------------------------------------
DEFAULT_LEDGER = "./skepstack-ledger.jsonl"
LEDGER_ENV_VAR = "SKEPSTACK_LEDGER"
CSV_HEADER: Tuple[str, ...] = (
    "inspection_id",
    "hive_id",
    "inspected_on",
    "mite_count",
    "queen_status",
    "treatment_date",
    "notes",
)
REQUIRED_CSV_COLUMNS: Tuple[str, ...] = ("hive_id", "inspected_on", "mite_count", "queen_status")
FIELD_ORDER: Tuple[str, ...] = CSV_HEADER
QUEEN_STATUSES: Tuple[str, ...] = ("queenright", "queenless", "virgin", "unknown")
HIVE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WHOLE_NUMBER_PATTERN = re.compile(r"^\+?\d+$")
FORMULA_TRIGGERS: Tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")

NOTES_MAX = 500
NOTES_DISPLAY_MAX = 60
MITE_COLUMN_INDEX = 3

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2


class SkepStackError(Exception):
    """Base class: a ledger or CSV file could not be read or written."""


class LedgerError(SkepStackError):
    """The ledger file could not be read or appended to."""


class CsvError(SkepStackError):
    """The CSV file could not be read or written."""


class MissingColumnsError(CsvError):
    """The CSV header lacks at least one required column."""

    def __init__(self, columns: Sequence[str]) -> None:
        super().__init__("missing required column(s): " + ", ".join(columns))
        self.columns = list(columns)


MAX_PATH_LENGTH = 4096


def sanitize_path(raw: Optional[str]) -> Path:
    """Turn a user-supplied path into a canonical absolute Path, safely.

    Every file sink in SkepStack goes through this one gate:

    * a **relative** path is resolved against the working directory and must
      stay inside it, so `..` segments that climb out are refused and a typo or
      pasted path can never silently read or write somewhere else;
    * an **absolute** path is honoured -- a command-line user is naming a file on
      their own machine and already holds those permissions -- but it is still
      canonicalised (`.`, `..` and symlinks collapsed) before anything is opened;
    * NUL bytes, control characters and absurdly long paths are always refused.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise SkepStackError("path is required")
    if len(text) > MAX_PATH_LENGTH:
        raise SkepStackError("path is too long ({} characters)".format(len(text)))
    if any(character == "\x00" or ord(character) < 0x20 for character in text):
        raise SkepStackError("path contains a NUL or control character")

    candidate = Path(text).expanduser()
    root = Path(os.sep).resolve()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        working_directory = Path.cwd().resolve()
        resolved = (working_directory / candidate).resolve()
        if not resolved.is_relative_to(working_directory):
            raise SkepStackError(
                "relative path leaves the working directory ({}); "
                "pass an absolute path instead".format(resolved)
            )
    if not resolved.is_relative_to(root):
        raise SkepStackError("{} is not a usable file path".format(resolved))
    return resolved


# --- output helpers -------------------------------------------------------
def _reconfigure_stream(stream: Any) -> None:
    """Force UTF-8 so box drawing survives a C/POSIX locale."""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        # Detached or already-wrapped streams simply keep their encoding.
        return


def _should_use_color(stream: Any) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def paint(text: str, code: str) -> str:
    if not USE_COLOR or not code:
        return text
    return "\x1b[" + code + "m" + text + "\x1b[0m"


def emit_errors(messages: Sequence[str]) -> None:
    for message in messages:
        print(message, file=sys.stderr)


def ordered_errors(errors: Dict[str, str]) -> List[str]:
    return [errors[field] for field in FIELD_ORDER if field in errors]


# --- field parsing and the single shared validator (D3) -------------------
def _clean(value: Optional[str]) -> str:
    return "" if value is None else str(value).strip()


def parse_iso_date(raw: str) -> Optional[date]:
    """Accept exactly YYYY-MM-DD; anything else (2024-13-01, 2024-5-1) is invalid."""
    if not ISO_DATE_PATTERN.match(raw):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_mite_count(raw: str) -> Optional[int]:
    if not WHOLE_NUMBER_PATTERN.match(raw):
        return None
    return int(raw)


def validate_inspection(fields: Dict[str, Optional[str]]) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """The only writer-side gate: used by both `log` and `import`."""
    errors: Dict[str, str] = {}
    values: Dict[str, Any] = {}

    hive_id = _clean(fields.get("hive_id"))
    if not hive_id:
        errors["hive_id"] = "hive_id: required"
    elif not HIVE_ID_PATTERN.match(hive_id):
        errors["hive_id"] = "hive_id: use 1-32 letters, digits, hyphens or underscores"
    else:
        values["hive_id"] = hive_id

    inspected_on = _clean(fields.get("inspected_on"))
    if not inspected_on:
        errors["inspected_on"] = "inspected_on: required"
    elif parse_iso_date(inspected_on) is None:
        errors["inspected_on"] = "inspected_on: not a valid ISO date (YYYY-MM-DD)"
    else:
        values["inspected_on"] = inspected_on

    raw_mites = _clean(fields.get("mite_count"))
    if not raw_mites:
        errors["mite_count"] = "mite_count: required"
    else:
        mites = parse_mite_count(raw_mites)
        if mites is None:
            errors["mite_count"] = "mite_count: must be a whole number 0 or greater"
        else:
            values["mite_count"] = mites

    raw_queen = _clean(fields.get("queen_status"))
    if not raw_queen:
        errors["queen_status"] = "queen_status: required"
    elif raw_queen.lower() not in QUEEN_STATUSES:
        errors["queen_status"] = "queen_status: must be one of queenright, queenless, virgin, unknown"
    else:
        values["queen_status"] = raw_queen.lower()

    treatment_date = _clean(fields.get("treatment_date"))
    if treatment_date:
        if parse_iso_date(treatment_date) is None:
            errors["treatment_date"] = "treatment_date: not a valid ISO date (YYYY-MM-DD)"
        else:
            values["treatment_date"] = treatment_date
    else:
        values["treatment_date"] = ""

    notes = fields.get("notes")
    notes = "" if notes is None else str(notes)
    if len(notes) > NOTES_MAX:
        errors["notes"] = "notes: must be 500 characters or fewer"
    else:
        values["notes"] = notes if notes.strip() else ""

    return errors, values


def normalise_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Tolerate hand-edited ledger lines so reading never crashes."""
    mites = raw.get("mite_count")
    if isinstance(mites, bool) or not isinstance(mites, int):
        mites = _clean(mites if isinstance(mites, str) else "")

    def text(key: str) -> str:
        value = raw.get(key)
        return "" if value is None else str(value)

    return {
        "inspection_id": text("inspection_id"),
        "hive_id": text("hive_id"),
        "inspected_on": text("inspected_on"),
        "mite_count": mites,
        "queen_status": text("queen_status").lower(),
        "treatment_date": text("treatment_date"),
        "notes": text("notes"),
    }


# --- ledger file (append only, D2) ---------------------------------------
def ledger_argument(cli_value: Optional[str]) -> str:
    """The ledger location exactly as the user named it: flag, env var, or default."""
    raw = cli_value or os.environ.get(LEDGER_ENV_VAR) or DEFAULT_LEDGER
    return str(raw).strip()


def resolve_ledger_path(cli_value: Optional[str]) -> Path:
    """The canonical, validated Path the ledger is actually read from and written to."""
    try:
        return sanitize_path(ledger_argument(cli_value))
    except SkepStackError as exc:
        raise LedgerError(str(exc)) from exc


def read_ledger(path: Path) -> List[Dict[str, Any]]:
    """Stream the ledger line by line; line order is ledger order."""
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    print("warning: {}: line {} is not valid JSON ({}); skipped".format(path, number, exc.msg), file=sys.stderr)
                    continue
                if not isinstance(parsed, dict):
                    print("warning: {}: line {} is not a JSON object; skipped".format(path, number), file=sys.stderr)
                    continue
                records.append(normalise_record(parsed))
    except OSError as exc:
        raise LedgerError("cannot read {}: {}".format(path, exc.strerror or exc)) from exc
    return records


def append_records(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    """Append one newline-terminated JSON line per record, flushed and fsync'd."""
    if not records:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise LedgerError("cannot write {}: {}".format(path, exc.strerror or exc)) from exc


def mint_inspection_id(existing: Set[str]) -> str:
    """insp-<UTC yyyymmddThhmmssZ>-<8 hex>, unique against ids already in play."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    while True:
        candidate = "insp-{}-{}".format(stamp, uuid.uuid4().hex[:8])
        if candidate not in existing:
            return candidate


def sort_newest_first(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Newest inspected_on first; same-day ties broken by most recently written."""
    indexed = list(enumerate(records))
    indexed.sort(key=lambda pair: (pair[1]["inspected_on"], pair[0]), reverse=True)
    return [record for _, record in indexed]


# --- CSV cell escaping (formula guard, still lossless) --------------------
def csv_escape(value: str) -> str:
    """Neutralise spreadsheet formulas; csv_unescape() reverses it exactly."""
    if not value:
        return value
    if value[0] in FORMULA_TRIGGERS or value[0] == "'":
        return "'" + value
    return value


def csv_unescape(cell: str) -> str:
    if len(cell) > 1 and cell[0] == "'" and (cell[1] in FORMULA_TRIGGERS or cell[1] == "'"):
        return cell[1:]
    return cell


def write_csv(handle: Any, records: Sequence[Dict[str, Any]]) -> None:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for record in records:
        row = []
        for field in CSV_HEADER:
            value = record.get(field, "")
            row.append(value if isinstance(value, int) else csv_escape("" if value is None else str(value)))
        writer.writerow(row)


def parse_csv_stream(handle: Any, label: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """Map cells by header name, so column order never matters."""
    reader = csv.reader(handle)
    try:
        header_row = next(reader)
    except StopIteration:
        return [], []
    except csv.Error as exc:
        raise CsvError("{} is not readable CSV: {}".format(label, exc)) from exc

    header = [cell.strip().lstrip("\ufeff") for cell in header_row]
    positions: Dict[str, int] = {}
    for index, name in enumerate(header):
        if name and name not in positions:
            positions[name] = index

    rows: List[Dict[str, str]] = []
    try:
        for raw in reader:
            if not raw or all(not cell.strip() for cell in raw):
                continue
            rows.append(
                {name: (raw[index] if index < len(raw) else "") for name, index in positions.items()}
            )
    except csv.Error as exc:
        raise CsvError("{} is not readable CSV: {}".format(label, exc)) from exc
    return rows, [name for name in header if name]


def csv_path(target: str) -> Path:
    """sanitize_path() for a CSV file, reported as a CSV problem."""
    try:
        return sanitize_path(target)
    except SkepStackError as exc:
        raise CsvError(str(exc)) from exc


def read_csv_input(target: str) -> Tuple[List[Dict[str, str]], List[str]]:
    if target == "-":
        text = sys.stdin.read()
        return parse_csv_stream(io.StringIO(text.lstrip("\ufeff")), "<stdin>")
    path = csv_path(target)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return parse_csv_stream(handle, str(path))
    except OSError as exc:
        raise CsvError("cannot read {}: {}".format(path, exc.strerror or exc)) from exc


def write_csv_file(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    """Write the CSV to a path already produced by csv_path()."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            write_csv(handle, records)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise CsvError("cannot write {}: {}".format(path, exc.strerror or exc)) from exc


# --- table rendering (aligned terminal columns, compact density) ----------
def _cell_text(record: Dict[str, Any], field: str) -> str:
    value = record.get(field, "")
    text = "" if value is None else str(value)
    return text if text else "-"


def _display_notes(notes: str) -> Tuple[str, bool]:
    if len(notes) <= NOTES_DISPLAY_MAX:
        return notes or "-", False
    return notes[: NOTES_DISPLAY_MAX - 1] + "\u2026", True


def render_table(records: Sequence[Dict[str, Any]]) -> str:
    headers = ["inspection_id", "hive_id", "inspected_on", "mites", "queen", "treatment", "notes"]
    body: List[List[str]] = []
    truncated = False
    for record in records:
        notes, cut = _display_notes(record.get("notes") or "")
        truncated = truncated or cut
        body.append(
            [
                _cell_text(record, "inspection_id"),
                _cell_text(record, "hive_id"),
                _cell_text(record, "inspected_on"),
                _cell_text(record, "mite_count"),
                _cell_text(record, "queen_status"),
                _cell_text(record, "treatment_date"),
                notes,
            ]
        )

    widths = [len(header) for header in headers]
    for row in body:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def rule(left: str, middle: str, right: str) -> str:
        segments = ["\u2500" * (width + 2) for width in widths]
        return paint(left + middle.join(segments) + right, THEME["border_ansi"])

    def line(cells: Sequence[str], header: bool = False) -> str:
        parts = []
        for index, cell in enumerate(cells):
            padded = cell.rjust(widths[index]) if index == MITE_COLUMN_INDEX else cell.ljust(widths[index])
            if header:
                rendered = paint(padded, THEME["strong_ansi"])
            elif index == 4 and cell == "queenright":
                rendered = paint(padded, THEME["accent_strong_ansi"])
            elif index == 4:
                rendered = paint(padded, THEME["text_ansi"])
            else:
                rendered = padded
            parts.append(" " + rendered + " ")
        return paint("\u2502", THEME["border_ansi"]) + paint("\u2502", THEME["border_ansi"]).join(parts) + paint("\u2502", THEME["border_ansi"])

    lines = [rule("\u250c", "\u252c", "\u2510"), line(headers, header=True), rule("\u251c", "\u253c", "\u2524")]
    lines.extend(line(row) for row in body)
    lines.append(rule("\u2514", "\u2534", "\u2518"))
    if truncated:
        lines.append(
            paint(
                "notes longer than {} characters are shortened here; export --csv keeps the full text".format(NOTES_DISPLAY_MAX),
                THEME["muted_ansi"],
            )
        )
    return "\n".join(lines)


def empty_ledger_hint() -> str:
    return "\n".join(
        [
            "No inspections yet.",
            "Log your first inspection with:",
            "  skepstack log --hive H1 --date 2024-05-01 --mites 0 --queen queenright",
            "Running it straight from this file works too:",
            "  python3 skepstack.py log --hive H1 --date 2024-05-01 --mites 0 --queen queenright",
        ]
    )


# --- command API (one implementation, shared by the CLI and scripts/smoke.py)
class ImportOutcome(NamedTuple):
    """The result of one CSV import."""

    imported: int
    skipped: int
    messages: List[str]


def ledger_summary(ledger: Path, label: str) -> str:
    """One honest line about the ledger, shown under the help of a bare invocation."""
    try:
        records = read_ledger(ledger)
    except SkepStackError as exc:
        return "ledger: {} (unreadable: {})".format(label, exc)
    if not records:
        return "ledger: {} - no inspections yet; log one with: skepstack log --hive H1 --date 2024-05-01 --mites 0 --queen queenright".format(label)
    hives = sorted({record["hive_id"] for record in records if record["hive_id"]})
    return "ledger: {} - {} inspection{} across {} hive{}; run: skepstack list".format(
        label,
        len(records),
        "" if len(records) == 1 else "s",
        len(hives),
        "" if len(hives) == 1 else "s",
    )


def log_inspection(ledger: Path, fields: Dict[str, Optional[str]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    """Validate one inspection and append it: (record, field errors)."""
    errors, values = validate_inspection(fields)
    if errors:
        return None, errors

    existing = read_ledger(ledger)
    known_ids = {record["inspection_id"] for record in existing if record["inspection_id"]}
    record: Dict[str, Any] = {"inspection_id": mint_inspection_id(known_ids)}
    record.update(values)
    append_records(ledger, [{field: record[field] for field in FIELD_ORDER}])
    return record, {}


def list_inspections(ledger: Path, hive: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(every inspection in the ledger, the newest-first selection for `hive`)."""
    everything = read_ledger(ledger)
    ordered = sort_newest_first(everything)
    if hive is None:
        return everything, ordered
    return everything, [record for record in ordered if record["hive_id"] == hive]


def list_title(count: int, hive: Optional[str]) -> str:
    parts = ["SkepStack"]
    if hive is not None:
        parts.append("hive {}".format(hive))
    parts.append("{} inspection{}".format(count, "" if count == 1 else "s"))
    parts.append("newest first")
    return "  ".join(parts)


def export_inspections(ledger: Path, target: str) -> int:
    """Write every inspection to `target` ('-' means stdout); returns the row count."""
    records = read_ledger(ledger)
    if target == "-":
        write_csv(sys.stdout, records)
        sys.stdout.flush()
    else:
        write_csv_file(csv_path(target), records)
    return len(records)


def _row_fields(row: Dict[str, str]) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for name in ("hive_id", "inspected_on", "mite_count", "queen_status", "treatment_date"):
        fields[name] = csv_unescape(row.get(name) or "").strip()
    fields["notes"] = csv_unescape(row.get("notes") or "")
    return fields


def import_inspections(ledger: Path, source: str) -> ImportOutcome:
    """Append every valid row of `source`; skip and report the rest by row number."""
    rows, header = read_csv_input(source)
    missing = [column for column in REQUIRED_CSV_COLUMNS if column not in header]
    if missing:
        raise MissingColumnsError(missing)

    reserved: Set[str] = {record["inspection_id"] for record in read_ledger(ledger) if record["inspection_id"]}
    accepted: List[Dict[str, Any]] = []
    messages: List[str] = []

    for offset, row in enumerate(rows):
        row_number = offset + 2
        errors, values = validate_inspection(_row_fields(row))
        if errors:
            messages.extend("row {}: {}".format(row_number, message) for message in ordered_errors(errors))
            continue

        given_id = csv_unescape(row.get("inspection_id") or "").strip()
        if given_id and given_id in reserved:
            messages.append("row {}: inspection_id {} is already in the ledger; skipped".format(row_number, given_id))
            continue

        inspection_id = given_id or mint_inspection_id(reserved)
        reserved.add(inspection_id)
        record: Dict[str, Any] = {"inspection_id": inspection_id}
        record.update(values)
        accepted.append({field: record[field] for field in FIELD_ORDER})

    if accepted:
        append_records(ledger, accepted)
    return ImportOutcome(imported=len(accepted), skipped=len(rows) - len(accepted), messages=messages)


# --- commands (thin wrappers: parse, call the API, report) -----------------
def command_log(args: argparse.Namespace, ledger: Path) -> int:
    fields = {
        "hive_id": args.hive,
        "inspected_on": args.date,
        "mite_count": args.mites,
        "queen_status": args.queen,
        "treatment_date": args.treatment_date,
        "notes": args.notes,
    }
    try:
        record, errors = log_inspection(ledger, fields)
    except LedgerError as exc:
        print("ledger: {}".format(exc), file=sys.stderr)
        return EXIT_USAGE

    if errors:
        emit_errors(ordered_errors(errors))
        return EXIT_USAGE
    if record is None:
        print("ledger: the inspection was not written", file=sys.stderr)
        return EXIT_USAGE

    print("Logged {} for hive {} on {}".format(record["inspection_id"], record["hive_id"], record["inspected_on"]))
    return EXIT_OK


def _validated_hive_filter(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if raw is None:
        return None, None
    cleaned = raw.strip()
    if not cleaned:
        return None, "hive_id: required"
    if not HIVE_ID_PATTERN.match(cleaned):
        return None, "hive_id: use 1-32 letters, digits, hyphens or underscores"
    return cleaned, None


def command_list(args: argparse.Namespace, ledger: Path) -> int:
    hive_filter, error = _validated_hive_filter(args.hive)
    if error:
        print(error, file=sys.stderr)
        return EXIT_USAGE

    try:
        everything, ordered = list_inspections(ledger, hive_filter)
    except LedgerError as exc:
        print("ledger: {}".format(exc), file=sys.stderr)
        return EXIT_USAGE

    if not everything:
        print(empty_ledger_hint())
        return EXIT_OK
    if hive_filter is not None and not ordered:
        print("No inspections for hive {}.".format(hive_filter))
        return EXIT_OK

    print(paint(list_title(len(ordered), hive_filter), THEME["muted_ansi"]))
    print(render_table(ordered))
    return EXIT_OK


def _require_csv_target(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    target = (raw or "").strip()
    if not target:
        return None, "csv: required (use --csv out.csv, or --csv - for stdout)"
    return target, None


def command_export(args: argparse.Namespace, ledger: Path) -> int:
    target, error = _require_csv_target(args.csv)
    if error:
        print(error, file=sys.stderr)
        return EXIT_USAGE

    try:
        count = export_inspections(ledger, target)
    except LedgerError as exc:
        print("ledger: {}".format(exc), file=sys.stderr)
        return EXIT_USAGE
    except CsvError as exc:
        print("csv: {}".format(exc), file=sys.stderr)
        return EXIT_USAGE

    if target == "-":
        print("{} inspections exported to <stdout>".format(count), file=sys.stderr)
    else:
        print("{} inspections exported to {}".format(count, target))
    return EXIT_OK


def command_import(args: argparse.Namespace, ledger: Path) -> int:
    target, error = _require_csv_target(args.csv)
    if error:
        print(error, file=sys.stderr)
        return EXIT_USAGE

    try:
        outcome = import_inspections(ledger, target)
    except MissingColumnsError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except CsvError as exc:
        print("csv: {}".format(exc), file=sys.stderr)
        return EXIT_USAGE
    except LedgerError as exc:
        print("ledger: {}".format(exc), file=sys.stderr)
        return EXIT_USAGE

    for message in outcome.messages:
        print(message, file=sys.stderr)
    print("{} inspections imported".format(outcome.imported))
    if outcome.skipped:
        print("{} row(s) skipped; see the messages above".format(outcome.skipped), file=sys.stderr)
        return EXIT_PARTIAL
    return EXIT_OK


# --- argument surface -----------------------------------------------------
EXAMPLES = """examples:
  skepstack log --hive H1 --date 2024-05-01 --mites 3 --queen queenright --notes "calm, 2 supers"
  skepstack log --hive H1 --date 2024-05-08 --mites 7 --queen queenless \\
      --treatment-date 2024-05-08 --notes "oxalic acid dribble"
  skepstack list
  skepstack list --hive H1
  skepstack export --csv inspections.csv
  skepstack import --csv inspections.csv

Running without installing:
  python3 skepstack.py list --hive H1

exit codes:
  0  success
  1  completed, but some imported rows were skipped
  2  usage or validation error (nothing was written)
"""

COMMON_LEDGER_HELP = (
    "ledger file to use (default: $" + LEDGER_ENV_VAR + " or " + DEFAULT_LEDGER + ")"
)


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--ledger", metavar="PATH", default=argparse.SUPPRESS, help=COMMON_LEDGER_HELP)
    shared.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS, help="disable ANSI colour")

    parser = argparse.ArgumentParser(
        prog="skepstack",
        description="SkepStack - an append-only ledger of beehive inspections (mite counts, queen status, treatments).",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ledger", metavar="PATH", default=None, help=COMMON_LEDGER_HELP)
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colour even on a terminal")
    parser.add_argument("--version", action="version", version="SkepStack {}".format(__version__))

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", title="commands")

    log_parser = subparsers.add_parser(
        "log",
        parents=[shared],
        help="append one inspection to the ledger",
        description="Append one validated inspection to the ledger. Nothing is written unless every field passes.",
        epilog="example:\n  skepstack log --hive H1 --date 2024-05-01 --mites 3 --queen queenright --notes \"calm, 2 supers\"\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    log_parser.add_argument("--hive", metavar="ID", help="hive id: 1-32 letters, digits, hyphens or underscores (required)")
    log_parser.add_argument("--date", metavar="YYYY-MM-DD", help="inspection date, ISO (required)")
    log_parser.add_argument("--mites", metavar="N", help="mite count: whole number 0 or greater (required)")
    log_parser.add_argument(
        "--queen",
        metavar="STATUS",
        help="queen status: queenright | queenless | virgin | unknown (required, case-insensitive)",
    )
    log_parser.add_argument("--treatment-date", dest="treatment_date", metavar="YYYY-MM-DD", help="treatment date, ISO (optional)")
    log_parser.add_argument("--notes", metavar="TEXT", help="free-text notes, up to 500 characters (optional)")
    log_parser.set_defaults(handler=command_log)

    list_parser = subparsers.add_parser(
        "list",
        parents=[shared],
        help="show inspections as a table, newest first",
        description="Print every inspection as an aligned table, newest inspected_on first (same-day ties: most recently written first).",
        epilog="examples:\n  skepstack list\n  skepstack list --hive H1\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.add_argument("--hive", metavar="ID", help="only show inspections recorded against this hive")
    list_parser.set_defaults(handler=command_list)

    export_parser = subparsers.add_parser(
        "export",
        parents=[shared],
        help="write the whole ledger as CSV",
        description="Write every inspection to a CSV whose header is exactly: " + ",".join(CSV_HEADER) + ".",
        epilog="examples:\n  skepstack export --csv inspections.csv\n  skepstack export --csv - | head -3\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export_parser.add_argument("--csv", metavar="PATH", help="destination CSV file ('-' writes to stdout)")
    export_parser.set_defaults(handler=command_export)

    import_parser = subparsers.add_parser(
        "import",
        parents=[shared],
        help="append rows from a CSV into the ledger",
        description=(
            "Merge a spreadsheet into the ledger. The header must contain hive_id, inspected_on, mite_count and "
            "queen_status; rows that fail validation are skipped and reported with their spreadsheet row number."
        ),
        epilog="examples:\n  skepstack import --csv inspections.csv\n  skepstack import --csv - < inspections.csv\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    import_parser.add_argument("--csv", metavar="PATH", help="source CSV file ('-' reads from stdin)")
    import_parser.set_defaults(handler=command_import)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    global USE_COLOR

    _reconfigure_stream(sys.stdout)
    _reconfigure_stream(sys.stderr)

    parser = build_parser()
    args = parser.parse_args(argv)

    USE_COLOR = _should_use_color(sys.stdout) and not getattr(args, "no_color", False)

    try:
        ledger = resolve_ledger_path(getattr(args, "ledger", None))
    except SkepStackError as exc:
        print("ledger: {}".format(exc), file=sys.stderr)
        return EXIT_USAGE

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        print()
        print(paint(ledger_summary(ledger, ledger_argument(getattr(args, "ledger", None))), THEME["muted_ansi"]))
        return EXIT_OK

    try:
        return handler(args, ledger)
    except KeyboardInterrupt:
        print("skepstack: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
