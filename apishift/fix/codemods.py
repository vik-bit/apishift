"""Deterministic rewrites for the unambiguous rules.

Plain English: renaming `.iteritems()` to `.items()` needs no AI. A precise edit is free, instant
and always the same. These edits change only the exact characters involved, so comments and
formatting everywhere else stay as they were.

How it works:
- Positions come from the AST. AST columns are UTF-8 *byte* offsets, so they're converted to
  character offsets per line before slicing text.
- Each fix is a list of (start, end, replacement) edits. Edits within one pass must not overlap;
  overlapping fixes (two rules on one chained expression) wait for the next pass. The file is
  re-parsed and re-scanned between passes, until nothing more can be codemodded.
- A result that doesn't parse is thrown away and the original kept.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ..analysis.imports import Imports, resolve_imports
from ..analysis.scanner import Finding, scan_source

Edit = tuple[int, int, str]  # start char offset, end char offset, replacement

_RENAMES = {"PD002": {"iteritems": "items"}, "PD006": {"is_monotonic": "is_monotonic_increasing"},
            "PD101": {"applymap": "map"}, "PD102": {"backfill": "bfill", "pad": "ffill"}}
_FILL = {"ffill": "ffill", "pad": "ffill", "bfill": "bfill", "backfill": "bfill"}
_INDEX_DTYPES = {"Int64Index": "int64", "Float64Index": "float64", "UInt64Index": "uint64"}


@dataclass
class Applied:
    rule_id: str
    line: int
    description: str


class _Text:
    """Maps AST (line, utf-8 byte column) positions to character offsets in the source."""

    def __init__(self, source: str):
        self.source = source
        self.lines = source.splitlines(keepends=True)
        self.starts = [0]
        for ln in self.lines:
            self.starts.append(self.starts[-1] + len(ln))

    def off(self, line: int, byte_col: int) -> int:
        text = self.lines[line - 1] if line - 1 < len(self.lines) else ""
        return self.starts[line - 1] + len(text.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore"))

    def start(self, node: ast.AST) -> int:
        return self.off(node.lineno, node.col_offset)

    def end(self, node: ast.AST) -> int:
        return self.off(node.end_lineno, node.end_col_offset)

    def seg(self, node: ast.AST) -> str:
        return self.source[self.start(node):self.end(node)]


def _attr_name_span(t: _Text, node: ast.Attribute) -> tuple[int, int]:
    end = t.end(node)
    return end - len(node.attr), end


def _remove_keyword(t: _Text, call: ast.Call, kw: ast.keyword) -> Edit:
    """Delete `kw` and exactly one adjoining comma from a call's argument list."""
    args: list[ast.AST] = [*call.args, *call.keywords]
    args.sort(key=lambda a: (a.lineno, a.col_offset))
    i = args.index(kw)
    kw_start = t.off(kw.lineno, kw.col_offset)
    kw_end = t.end(kw.value)
    if i + 1 < len(args):  # not last: delete up to the next argument
        return kw_start, t.off(args[i + 1].lineno, args[i + 1].col_offset), ""
    if i > 0:  # last: delete from the end of the previous argument
        return t.end(args[i - 1]), kw_end, ""
    # only argument: delete it and any surrounding whitespace inside the parentheses
    close = t.end(call) - 1
    open_ = t.end(call.func)
    return open_ + 1, close, ""


def _import_edit(t: _Text, imp: Imports, tree: ast.Module, line: str) -> Edit:
    if imp.last_import_line:
        pos = t.starts[imp.last_import_line]
    else:
        body = tree.body
        doc = body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)
        pos = t.starts[body[0].end_lineno] if doc else 0
    if pos > 0 and not t.source[:pos].endswith("\n"):
        line = "\n" + line
    return pos, pos, line + "\n"


def fix_for(f: Finding, t: _Text, imp: Imports, tree: ast.Module, naive_append: bool = False) -> tuple[list[Edit], str] | None:
    """The edits that fix one finding, or None if this finding needs the LLM."""
    node = f.node
    if f.confidence != "certain" or node is None:
        return None
    rid = f.rule_id

    if rid in _RENAMES and isinstance(node, ast.Attribute):
        new = _RENAMES[rid].get(node.attr)
        if new is None or (rid == "PD102" and f.receiver_kind == "unknown"):
            return None
        s, e = _attr_name_span(t, node)
        return [(s, e, new)], f".{node.attr} → .{new}"

    if rid == "PD007" and isinstance(node, ast.Call):
        kw = next(k for k in node.keywords if k.arg == "line_terminator")
        s = t.off(kw.lineno, kw.col_offset)
        return [(s, s + len("line_terminator"), "lineterminator")], "line_terminator= → lineterminator="

    if rid == "PD008" and isinstance(node, ast.Call):
        kw = next(k for k in node.keywords if k.arg == "squeeze")
        end = t.end(node)
        return [_remove_keyword(t, node, kw), (end, end, '.squeeze("columns")')], 'squeeze=True → .squeeze("columns")'

    if rid == "PD103" and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        kw = next(k for k in node.keywords if k.arg == "method")
        value = kw.value.value if isinstance(kw.value, ast.Constant) else None
        if value not in _FILL or node.args or any(k.arg == "value" for k in node.keywords):
            return None
        s, e = _attr_name_span(t, node.func)
        return [(s, e, _FILL[value]), _remove_keyword(t, node, kw)], f'fillna(method="{value}") → .{_FILL[value]}()'

    if rid == "PD003" and isinstance(node, ast.Attribute):
        call = getattr(node, "_apishift_parent_call", None)
        simple = isinstance(node.value, (ast.Name, ast.Attribute)) and all(
            isinstance(n, (ast.Name, ast.Attribute, ast.Load)) for n in ast.walk(node.value))
        if call is None or call.args or call.keywords or not simple or f.receiver_kind == "unknown":
            return None
        r = t.seg(node.value)
        return [(t.start(call), t.end(call), f"({r} - {r}.mean()).abs().mean()")], ".mad() → (x - x.mean()).abs().mean()"

    if rid == "PD010" and isinstance(node, ast.Attribute):
        call = getattr(node, "_apishift_parent_call", None)
        if call is None or call.func is not node:
            return None  # e.g. isinstance(x, pd.Int64Index): needs judgement
        dtype = _INDEX_DTYPES[node.attr]
        s, e = _attr_name_span(t, node)
        edits: list[Edit] = [(s, e, "Index")]
        if any(k.arg == "dtype" for k in call.keywords):
            return None
        if call.args:
            pos = t.end(call.args[0])
            edits.append((pos, pos, f', dtype="{dtype}"'))
        else:
            pos = t.end(node) + 1  # just after "("
            edits.append((pos, pos, f'dtype="{dtype}"' + (", " if call.keywords else "")))
        return edits, f'{node.attr}(...) → Index(..., dtype="{dtype}")'

    if rid == "PD011" and isinstance(node, ast.Attribute):
        if imp.datetime_class:
            repl, extra = sorted(imp.datetime_class)[0], []
        elif imp.datetime_module:
            repl, extra = f"{sorted(imp.datetime_module)[0]}.datetime", []
        elif "datetime" not in imp.bound_names:
            repl, extra = "datetime.datetime", [_import_edit(t, imp, tree, "import datetime")]
        else:
            return None
        return [(t.start(node), t.end(node), repl), *extra], f"pd.datetime → {repl}"

    if rid == "PD012" and isinstance(node, ast.Attribute):
        if imp.numpy_modules:
            repl, extra = sorted(imp.numpy_modules)[0], []
        elif "np" not in imp.bound_names:
            repl, extra = "np", [_import_edit(t, imp, tree, "import numpy as np")]
        else:
            return None
        return [(t.start(node), t.end(node), repl), *extra], f"pd.np → {repl}"

    if rid == "PD001" and naive_append and isinstance(node, ast.Attribute) and f.receiver_kind != "unknown":
        # Baseline only: what a find-and-replace tool would do. Wrong when `other` is a dict or a row.
        call = getattr(node, "_apishift_parent_call", None)
        if call is None or not call.args or not imp.pandas_modules:
            return None
        pd_name = sorted(imp.pandas_modules)[0]
        rest = ", ".join([t.seg(a) for a in call.args[1:]] + [t.seg(k) for k in call.keywords])
        new = f"{pd_name}.concat([{t.seg(node.value)}, {t.seg(call.args[0])}]{', ' + rest if rest else ''})"
        return [(t.start(call), t.end(call), new)], "x.append(y) → pd.concat([x, y]) (naive)"

    return None


def _link_parents(tree: ast.Module) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            node.func._apishift_parent_call = node  # type: ignore[attr-defined]


def _overlaps(a: Edit, b: Edit) -> bool:
    if a[0] == a[1] or b[0] == b[1]:  # insertions only clash if strictly inside the other span
        point, span = (a, b) if a[0] == a[1] else (b, a)
        return span[0] < point[0] < span[1]
    return a[0] < b[1] and b[0] < a[1]


def apply_codemods(source: str, path: str = "<string>", naive_append: bool = False,
                   max_passes: int = 10) -> tuple[str, list[Applied]]:
    """Apply every codemod that applies; return the new source and what was done."""
    applied: list[Applied] = []
    for _ in range(max_passes):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            break
        _link_parents(tree)
        findings = scan_source(source, path)
        # scan_source parses its own tree; re-attach our nodes by position
        by_pos = {(type(n).__name__, n.lineno, n.col_offset, getattr(n, "end_lineno", None), getattr(n, "end_col_offset", None)): n
                  for n in ast.walk(tree) if hasattr(n, "lineno")}
        imp = resolve_imports(tree)
        t = _Text(source)
        chosen: list[Edit] = []
        chosen_desc: list[Applied] = []
        imports_added: set[str] = set()
        for f in findings:
            if f.node is not None:
                key = (type(f.node).__name__, f.node.lineno, f.node.col_offset, f.node.end_lineno, f.node.end_col_offset)
                f.node = by_pos.get(key, f.node)
            fix = fix_for(f, t, imp, tree, naive_append)
            if fix is None:
                continue
            edits, desc = fix
            # one import line per pass is enough; drop duplicates
            edits = [e for e in edits if not (e[0] == e[1] and e[2].strip() in imports_added)]
            if any(_overlaps(e, c) for e in edits for c in chosen):
                continue
            for e in edits:
                if e[0] == e[1] and e[2].strip().startswith("import "):
                    imports_added.add(e[2].strip())
            chosen.extend(edits)
            chosen_desc.append(Applied(f.rule_id, f.line, desc))
        if not chosen:
            break
        new = source
        for s, e, text in sorted(chosen, key=lambda x: (x[0], x[1]), reverse=True):
            new = new[:s] + text + new[e:]
        try:
            ast.parse(new)
        except SyntaxError:
            break  # never return code that doesn't parse
        source = new
        applied.extend(chosen_desc)
    return source, applied
