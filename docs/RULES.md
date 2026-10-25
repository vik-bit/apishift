# Supported rules

_Generated from `apishift/rules.py` by `apishift rules`. "Removed" rules raise on pandas 2.2; "deprecated" rules warn on 2.2 and are removed in pandas 3._

| ID | API | Status on pandas 2.2 | Fix | Migration |
|---|---|---|---|---|
| PD001 | `DataFrame.append / Series.append` | removed | LLM | Replace `x.append(other, ...)` with `pd.concat(...)`. The rewrite depends on what `other` is: a DataFrame or Series → `pd.concat([x, other])`; a list of frames → `pd.concat([x, *others])`; a dict (one row) → `pd.concat([x, pd.DataFrame([row])], ignore_index=True)`; a Series meant as a row of a DataFrame → `pd.concat([x, row.to_frame().T])`. Keep keyword arguments that pd.concat supports (ignore_index, verify_integrity, sort). append returned a new object and never modified `x` in place. |
| PD002 | `iteritems()` | removed | Codemod | Rename `.iteritems()` to `.items()`; it yields the same (label, value) pairs. |
| PD003 | `DataFrame.mad / Series.mad` | removed | Codemod, LLM if complex | Mean absolute deviation: replace `x.mad()` with `(x - x.mean()).abs().mean()`. For a DataFrame this is computed per column, as before. If axis= or skipna= were passed, apply them to mean() accordingly. |
| PD004 | `GroupBy.mad` | removed | LLM | Replace `g.mad()` with `g.agg(lambda s: (s - s.mean()).abs().mean())`. |
| PD005 | `DataFrame.lookup` | removed | LLM | Replace `df.lookup(row_labels, col_labels)` with label-based indexing, for example: `idx, cols = pd.factorize(col_labels); df.reindex(cols, axis=1).to_numpy()[np.arange(len(df)), idx]` when row_labels is df.index, or `np.array([df.at[r, c] for r, c in zip(row_labels, col_labels)])` in general. It must return a NumPy array, as lookup did. |
| PD006 | `is_monotonic` | removed | Codemod | Rename the property `.is_monotonic` to `.is_monotonic_increasing`. |
| PD007 | `to_csv(line_terminator=)` | removed | Codemod | Rename the keyword `line_terminator=` to `lineterminator=`. |
| PD008 | `read_csv(squeeze=True)` | removed | Codemod | Remove `squeeze=True` and call `.squeeze("columns")` on the result. |
| PD009 | `set_axis(inplace=True)` | removed | LLM | `df.set_axis(labels, axis=..., inplace=True)` as a statement becomes `df = df.set_axis(labels, axis=...)`. Keep every other argument. |
| PD010 | `Int64Index / Float64Index / UInt64Index` | removed | Codemod | Replace `pd.Int64Index(data)` with `pd.Index(data, dtype="int64")` (float64 / uint64 likewise). |
| PD011 | `pd.datetime` | removed | Codemod | Use the standard library: `pd.datetime` → `datetime.datetime` (import datetime). |
| PD012 | `pd.np` | removed | Codemod | Import NumPy directly: `pd.np` → `np` with `import numpy as np`. |
| PD101 | `applymap` | deprecated | Codemod | Rename `.applymap(...)` to `.map(...)` on DataFrames (same arguments). |
| PD102 | `backfill() / pad()` | deprecated | Codemod | Rename `.backfill(...)` to `.bfill(...)` and `.pad(...)` to `.ffill(...)`. |
| PD103 | `fillna(method=)` | deprecated | Codemod | `x.fillna(method="ffill")` → `x.ffill()`, `method="bfill"` → `x.bfill()` (also 'pad'/'backfill'). Keep `limit=`, `axis=` and `inplace=`. |
| PD104 | `swapaxes` | deprecated | LLM | For a DataFrame, `df.swapaxes(0, 1)` (or 'index', 'columns') is `df.T`; swapping an axis with itself returns an unchanged copy (`df.copy()`). |
| PD105 | `groupby(axis=1)` | deprecated | LLM | `df.groupby(keys, axis=1).agg(...)` → `df.T.groupby(keys).agg(...).T`. Make sure the result has the same orientation as before. |
| PD106 | `pd.value_counts` | deprecated | LLM | `pd.value_counts(values, ...)` → `pd.Series(values).value_counts(...)` (or `s.value_counts(...)` when values is already a Series). |
