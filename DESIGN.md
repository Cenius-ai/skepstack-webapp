# SkepStack design direction

Committed visual direction for this build. SkepStack is a terminal product, so
there is no CSS: the tokens below live in `THEME` at the top of `skepstack.py`
and are the only place colour is decided.

## Direction

| Property | Value |
|---|---|
| Archetype | CLI |
| Style family | calm-precise |
| Accent (one) | `oklch(0.58 0.12 151)` — `#3a8e54`, the same hue in ANSI truecolor as `38;2;58;142;84` |
| Type personality | monospace only (the terminal's own font; no webfont to load) |
| Density | compact — single-space cell padding, no blank lines between rows |
| Surface / mode | terminal dark: the tool paints **no** background, so the terminal's dark surface shows through; only foreground hues come from the ramp |
| Shape language | monospace, no chrome; box-drawing separators; one border treatment everywhere |
| Signature | aligned terminal columns; one accent for the primary status; never colour-only |

## Neutral ramp (dark surface)

| Token | Value | Used for |
|---|---|---|
| `strong_ansi` | `1;38;2;226;230;228` | table header labels (bold, near-white) |
| `text_ansi` | `38;2;226;230;228` | non-accent status values |
| `muted_ansi` | `38;2;138;148;143` | title line, footnotes |
| `border_ansi` | `38;2;88;100;94` | box-drawing rules and cell separators |
| `accent_ansi` | `38;2;58;142;84` | the `queenright` status only |
| `accent_strong_ansi` | `1;38;2;58;142;84` | `queenright` in the table body |

## Rules that follow from the direction

1. **One accent, one meaning.** `#3a8e54` marks a queenright hive and nothing
   else. Every other status is plain text, so the table still reads correctly for
   colour-blind users and in a pipe: the word `queenright` is always present.
2. **No colour-only signal.** Status never depends on hue; the textual status,
   the `-` for an absent optional field and the `…` for a shortened note carry
   the meaning.
3. **Help-first.** `skepstack` with no arguments prints the full help (usage,
   commands, examples, exit codes) and exits 0 — the first thing a new user sees
   is how to use the tool. One muted line under it states what the current ledger
   holds, so the lander is never blind: `ledger: ./skepstack-ledger.jsonl - 10
   inspections across 3 hives; run: skepstack list`.
4. **Aligned columns, box-drawing separators.** Every table is measured from the
   data, padded before colouring so ANSI escapes never break alignment.
5. **Colour is opt-out and never assumed.** On only when stdout is a terminal;
   off for pipes, files, `NO_COLOR`, `TERM=dumb` and `--no-color`.
6. **Compact, honest output.** One line per inspection, a title line, a footer
   only when notes were shortened. Nothing decorative, no spinners, no splash.

## Where it shows up

* `list` — title line, aligned table, accent on `queenright`, dim rules.
* `log`, `import`, `export` — one plain result line on stdout; field-level errors
  on stderr, one line per bad field, prefixed by the field name so they read like
  a linter, not a stack trace.
* Empty states — an invitation with a copy-pasteable command, in the muted hue.
