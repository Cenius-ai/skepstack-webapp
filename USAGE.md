# Using SkepStack

Five walkthroughs against a real ledger. Every command below is copy-pasteable;
`python3 skepstack.py` can be shortened to `skepstack` once `install.sh` has run.

## 1. Log the first inspection of the season

```bash
python3 skepstack.py log --hive H1 --date 2024-04-14 --mites 2 --queen queenright \
        --notes "first spring check; 6 frames of brood"
```

```
Logged insp-20240414T072233Z-5b0c9d47 for hive H1 on 2024-04-14
```

The ledger file `./skepstack-ledger.jsonl` is created on that first successful
save. Every later inspection is appended as one more JSON line; earlier lines are
never rewritten. Quote the `inspection_id` when you need to point at exactly one
observation — it is unique and sorted roughly by when it was recorded.

## 2. A rejected inspection writes nothing

```bash
python3 skepstack.py log --hive 'H 1!' --date 2024-13-01 --mites -2 --queen maybe
```

```
hive_id: use 1-32 letters, digits, hyphens or underscores
inspected_on: not a valid ISO date (YYYY-MM-DD)
mite_count: must be a whole number 0 or greater
queen_status: must be one of queenright, queenless, virgin, unknown
```

One line per bad field, exit code 2, and the ledger is untouched (not even
created if this was the first attempt). Nothing is ever half-written.

## 3. Read the ledger back

```bash
python3 skepstack.py list
python3 skepstack.py list --hive H1
```

```
SkepStack  3 inspections  newest first
┌────────────────────────────────┬─────────┬──────────────┬───────┬────────────┬────────────┬─────────────────────┐
│ inspection_id                  │ hive_id │ inspected_on │ mites │ queen      │ treatment  │ notes               │
├────────────────────────────────┼─────────┼──────────────┼───────┼────────────┼────────────┼─────────────────────┤
│ insp-20240602T101500Z-8f2ac1b0 │ H2      │ 2024-06-02   │     0 │ virgin     │ -          │ -                   │
│ insp-20240508T071500Z-2c9d40aa │ H1      │ 2024-05-08   │     7 │ queenless  │ 2024-05-08 │ treated with oxalic │
│ insp-20240414T072233Z-5b0c9d47 │ H1      │ 2024-04-14   │     2 │ queenright │ -          │ first spring check  │
└────────────────────────────────┴─────────┴──────────────┴───────┴────────────┴────────────┴─────────────────────┘
```

Newest `inspected_on` first; two inspections on the same day come out in reverse
write order, so the most recently recorded line is on top. `-` means the optional
field is empty. Piping it into `less` or a file works because the table is plain
text on stdout.

An empty ledger teaches instead of scolding:

```bash
python3 skepstack.py list          # in a directory with no ledger yet
```

```
No inspections yet.
Log your first inspection with:
  skepstack log --hive H1 --date 2024-05-01 --mites 0 --queen queenright
Running it straight from this file works too:
  python3 skepstack.py log --hive H1 --date 2024-05-01 --mites 0 --queen queenright
```

And a filter that matches nothing says so and still exits 0:

```bash
python3 skepstack.py list --hive H2
No inspections for hive H2.
```

## 4. Export a spreadsheet

```bash
python3 skepstack.py export --csv season.csv
3 inspections exported to season.csv
```

`season.csv` starts with the fixed header
`inspection_id,hive_id,inspected_on,mite_count,queen_status,treatment_date,notes`
and holds one row per record, in the order the records were logged. Notes with
commas, quotes or newlines are quoted properly. `--csv -` writes the CSV to
stdout with the count on stderr, so `python3 skepstack.py export --csv - | head -3`
stays clean.

A ledger with nothing in it still gets a valid file — header only — and reports
`0 inspections exported`. An unwritable destination names the path and the
reason and exits 2.

## 5. Import a season from a spreadsheet

Your spreadsheet needs at least these columns, in any order:
`hive_id`, `inspected_on`, `mite_count`, `queen_status`. `treatment_date` and
`notes` are picked up when present, and `inspection_id` is honoured when present
(blank or absent → a fresh id is minted).

```bash
python3 skepstack.py import --csv rows.csv
```

```
row 4: inspected_on: not a valid ISO date (YYYY-MM-DD)
2 row(s) skipped; see the messages above
2 inspections imported
```

The good rows land, the bad rows are named by spreadsheet row number (row 1 is
the header), and the exit code is `1` so a script can tell a partial import from a
clean one. If a required column is missing, nothing at all is written:

```bash
python3 skepstack.py import --csv broken.csv
missing required column(s): queen_status        # exit code 2
```

Importing the same file twice is safe: rows whose `inspection_id` is already in
the ledger are skipped instead of duplicated.

## Round trip in one command

```bash
python3 skepstack.py export --csv a.csv
python3 skepstack.py --ledger copy.jsonl import --csv a.csv
python3 skepstack.py --ledger copy.jsonl export --csv b.csv
diff a.csv b.csv && echo "every field survived"
```

`python3 scripts/smoke.py` runs exactly that (plus the sample season) in a
temporary directory and prints `SMOKE OK` when every field of every row matches.

## Where files may live

Relative paths (`out.csv`, `sub/ledger.jsonl`) resolve against the current
directory and must stay inside it — `--csv ../out.csv` is refused:

```bash
python3 skepstack.py export --csv ../out.csv
csv: relative path leaves the working directory (/home/ann/out.csv); pass an absolute path instead
```

Use an absolute path for anything outside the working directory; it is honoured
after canonicalisation (`.`, `..` and symlinks collapsed).

## Keeping several ledgers

```bash
python3 skepstack.py --ledger 2023.jsonl list
python3 skepstack.py list --ledger 2023.jsonl          # same thing, either side
SKEPSTACK_LEDGER=2023.jsonl python3 skepstack.py list  # or pin it in the shell
```

## Everyday recipes

```bash
# log every visit for hive H1 to one file, then read just that hive
python3 skepstack.py list --hive H1 > h1-history.txt

# keep a copy of the whole ledger next to the CSV export
cp skepstack-ledger.jsonl skepstack-ledger.backup.jsonl
python3 skepstack.py export --csv season-backup.csv

# count inspections per hive (the ledger is plain JSON Lines)
python3 -c "import json,collections;print(collections.Counter(json.loads(l)['hive_id'] for l in open('skepstack-ledger.jsonl')))"
```

Correcting a mistake means logging the corrected observation — the ledger is
append-only on purpose, so nothing that was once recorded can quietly disappear.
