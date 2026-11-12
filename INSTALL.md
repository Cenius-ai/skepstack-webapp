# Installing SkepStack

SkepStack is a single standard-library Python file. You can run it without
installing anything:

```bash
python3 skepstack.py --help
```

The steps below add the test runner, the optional `skepstack` console script and
a seeded demo ledger.

## Prerequisites (not installed by any script)

| Requirement | Why | Check |
|---|---|---|
| Python 3.9 or newer | the interpreter SkepStack runs on | `python3 --version` |
| pip (bundled with CPython) | installs the test runner and the console script | `python3 -m pip --version` |

No system packages, no database server, no compiler, no network access at
runtime. The only package SkepStack installs is `pytest` (test-only, pinned in
`requirements.txt`); the tool itself imports nothing outside the standard library.

## 1. Install dependencies and seed the demo ledger

```bash
bash install.sh
```

That one command, in order:

1. refreshes `pip`, `setuptools` and `wheel`;
2. `pip install -r requirements.txt` (pytest, test-only);
3. `pip install --no-build-isolation -e .` to expose the optional `skepstack`
   console script (if this fails, `python3 skepstack.py <command>` still works);
4. verifies the tool imports and prints its version;
5. seeds `./skepstack-ledger.jsonl` from `samples/sample_inspections.csv`
   (skipped when the ledger already has rows).

It installs only project-level packages into the current Python environment — no
`sudo`, no `apt`, no services — and it **exits**; nothing is left running.

## 2. Seed the demo ledger on its own (optional, idempotent)

```bash
bash scripts/seed_demo.sh
```

Imports the ten sample inspections into `$SKEPSTACK_LEDGER` (default
`./skepstack-ledger.jsonl`) only when that file is missing or empty. Re-running
is a no-op. Set `SKEPSTACK_LEDGER` to seed somewhere else:

```bash
SKEPSTACK_LEDGER=./season-2024.jsonl bash scripts/seed_demo.sh
```

## 3. Run it

```bash
python3 skepstack.py list                 # the seeded season, newest first
python3 skepstack.py list --hive H1
python3 skepstack.py log --hive H1 --date 2024-06-09 --mites 4 --queen queenright \
        --notes "added a third super"
python3 skepstack.py export --csv season.csv
```

If step 1 installed the console script you can drop `python3 skepstack.py` for
`skepstack`. `python3 -m skepstack ...` works as well.

There is no server to start and no port to open: SkepStack is a command that
runs, writes one line and exits.

## 4. Verify the installation

```bash
python3 -m pytest          # the test suite
python3 scripts/smoke.py   # end-to-end smoke run
bash demo.sh               # narrated demo
```

## Configuration

One optional environment variable, no secrets:

| Variable | Default | Meaning |
|---|---|---|
| `SKEPSTACK_LEDGER` | `./skepstack-ledger.jsonl` | ledger path used when `--ledger` is not passed |

`cp .env.example .env` is safe but unnecessary — SkepStack works with no `.env`
at all. (SkepStack does not read `.env` files itself; export variables in your
shell if you want them.) Colour is on for terminals only; `NO_COLOR=1` or
`--no-color` disables it.

## Uninstall

Delete the checkout, or just `python3 -m pip uninstall skepstack` to remove the
console script. Your ledger file is yours — SkepStack never deletes it.
