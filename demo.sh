#!/usr/bin/env bash
# SkepStack demo: log, list, export, import and a field-for-field round trip.
# Non-interactive; every file it touches lives in a temporary directory that is
# removed on exit, so the working tree is left exactly as it was.
set -euo pipefail
cd "$(dirname "$0")"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

skep() { python3 skepstack.py "$@"; }
step() { printf '\n== %s ==\n\n' "$1"; }

step "version and help-first usage"
python3 skepstack.py --version
python3 skepstack.py --help | head -12

step "log three inspections (append-only JSON Lines ledger)"
skep --ledger "$WORKDIR/ledger.jsonl" log --hive H1 --date 2024-05-01 --mites 3 \
     --queen queenright --notes 'calm, 2 supers'
skep --ledger "$WORKDIR/ledger.jsonl" log --hive H1 --date 2024-05-08 --mites 7 \
     --queen queenless --treatment-date 2024-05-08 --notes 'oxalic acid dribble'
skep --ledger "$WORKDIR/ledger.jsonl" log --hive H2 --date 2024-06-02 --mites 0 \
     --queen virgin

step "a failed log writes nothing and exits 2"
set +e
skep --ledger "$WORKDIR/ledger.jsonl" log --hive 'H 1!' --date 2024-13-01 --mites -2 --queen maybe
printf 'exit code: %s\n' "$?"
set -e

step "list every inspection, newest first"
skep --ledger "$WORKDIR/ledger.jsonl" list

step "list a single hive"
skep --ledger "$WORKDIR/ledger.jsonl" list --hive H1

step "the ledger on disk, one JSON object per line"
cat "$WORKDIR/ledger.jsonl"

step "export to CSV"
skep --ledger "$WORKDIR/ledger.jsonl" export --csv "$WORKDIR/inspections.csv"
cat "$WORKDIR/inspections.csv"

step "import that CSV into a second, empty ledger"
skep --ledger "$WORKDIR/second.jsonl" import --csv "$WORKDIR/inspections.csv"

step "export the second ledger and compare both files"
skep --ledger "$WORKDIR/second.jsonl" export --csv "$WORKDIR/second.csv"
if diff -u "$WORKDIR/inspections.csv" "$WORKDIR/second.csv"; then
  printf '\nround trip identical: every field survived export -> import -> export\n'
fi

step "import the bundled season sample (10 inspections)"
skep --ledger "$WORKDIR/season.jsonl" import --csv samples/sample_inspections.csv
skep --ledger "$WORKDIR/season.jsonl" list --hive H3

printf '\nDemo complete. Nothing outside %s was touched.\n' "$WORKDIR"
