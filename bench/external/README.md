# External cases

The 28 cases in [`bench/cases/`](../cases) were written for this project, which makes them easy to
fit. The cases here are taken from **real pandas 2 migrations in open-source projects** instead: the
old code is the upstream file before the fix, the reference solution is the upstream file after it,
and the tests are the project's own. They are scored separately (`apishift eval --suite external`)
and never mixed into the self-written numbers.

| Case | Project (license) | Upstream fix | What breaks on pandas 2 | Upstream tests |
|---|---|---|---|---|
| `e01-timeflux-window` | [timeflux](https://github.com/timeflux/timeflux) (MIT) | `5cd170c0f1c4` + `0a1012e94c60` | `DataFrame.append` on a streaming buffer, `Index.is_monotonic` | `test/nodes/test_window.py` |
| `e02-epathermostat-climate-zone` | [epathermostat](https://github.com/EPAENERGYSTAR/epathermostat) (MIT) | `97153b118159` | `Series.iteritems` | `tests/test_climate_zone.py`, added with the fix |
| `e03-timeflux-dsp-peaks` | [timeflux_dsp](https://github.com/timeflux/timeflux_dsp) (MIT) | `cdd75dd04d35` | `DataFrame.append` of each detected event | `test/test_peaks.py` |

## What was changed, and why

Each `case.json` has a `source` block that records the repository, the commits and every change.
The changes are limited to what a single-file case needs:

- The test's import of the module (e.g. `from timeflux.nodes.window import` → `from window import`).
- The parts of the project the module imports are vendored under `tests/`, cut to what is used. For
  timeflux that is `Node`, `Port`, `ReadData`, `Looper` and `clock.now`, and each file says so.
- Data files are cut to the rows the tests read.
- Breakages that are not pandas migrations are fixed in both the old code and the solution, so that
  a case measures only the pandas change. Two such changes were needed: `np.Inf` → `np.inf` (NumPy 2)
  in e03, and `pandas.util.testing.makeTimeDataFrame` (removed) in e03's test.

`apishift bench-check --suite external` checks, as for the self-written set, that every test fails
on the old code and passes on the upstream fix. CI runs that check on every push.

## Result

Codemods only, no LLM: **3/3 fixed** (2026-11-01, pandas 2.2.3, strict mode). Raw numbers:
[`bench/results/partial_external-codemod.json`](../results/partial_external-codemod.json).

The upstream fix for e01 took two commits, a month apart: the first replaced `append` but left
`is_monotonic`, which still raises `AttributeError` on pandas 2. The codemod fixes both in one pass.

The LLM modes were not run on this suite, because that costs API credits.

**Caveat:** three cases is a small set. These are the simple, mechanical patterns that the codemod
already handles (11/25 on the self-written set, which was built to include hard cases). They show
that the tool works on code it was not written against. They do not show how often it succeeds on
real migrations.

## Considered and left out

| Candidate | Why it is not a case |
|---|---|
| py3plex `f9c5d4bde553`, duva `9fa59f7821`, mmctools `7e26348b27` | No upstream test covers the changed code |
| data-wrangler `27bb16dedcd6` | Tied to the whole package (relative imports, image and file loaders). A good hard case, though: `'iteritems'` appears as a string in a list of attribute names, not as a call |
| plotnine `e9cc70dd544f` | Needs most of plotnine. Its fix calls `pd.concat(base, cross_join(...), ignore_index=True)`, which passes the second frame as `axis` |
| resqpy `78d73761632c` | Spans six large files |
| radiostats | No license |
