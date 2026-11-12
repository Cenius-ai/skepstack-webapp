#!/usr/bin/env bash
# Seed a demo ledger with a realistic beekeeping season so `list` and `export`
# show real content on a fresh checkout. Idempotent: it only imports when the
# ledger is missing or empty. Never starts a server (SkepStack is a CLI).
set -euo pipefail
cd "$(dirname "$0")/.."

LEDGER="${SKEPSTACK_LEDGER:-./skepstack-ledger.jsonl}"

if [ -s "$LEDGER" ] && [ "$(wc -l < "$LEDGER")" -gt 0 ]; then
  echo "seed: $LEDGER already holds inspections; nothing to do"
  exit 0
fi

echo "seed: importing samples/sample_inspections.csv into $LEDGER"
python3 skepstack.py --ledger "$LEDGER" import --csv samples/sample_inspections.csv
