"""Find removed and deprecated pandas APIs, using type inference to avoid false alarms.

Plain English: `rows.append(x)` is fine if `rows` is a list and broken if it's a DataFrame. Python
doesn't record types, so the scanner works them out the way a compiler does. It walks each function
top to bottom and tracks what every variable holds: "assigned from pd.read_csv → DataFrame",
"assigned []  → list", "df['col'] → Series", and so on.

How it works:
- A small lattice of kinds (rules.Kind): DataFrame, Series, Index, GroupBy, Pandas, list, dict, str,
  other, unknown.
- Forward pass over statements; assignments update the environment. Assignments inside if/for/while
  *join* with the previous kind (they may not run), so the analysis stays conservative.
- `self.x` attributes are tracked per class; function return kinds are inferred first (a light
  inter-procedural pass), so `df = load()` works when `load` returns `pd.read_csv(...)`.
- A receiver of known pandas kind is a *certain* finding. An *unknown* receiver of an ambiguous
  method like `.append` is *possible* (the LLM decides). Lists, dicts and strings are never flagged.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..rules import BY_ID, RULES, Kind, Rule
from .imports import Imports, resolve_imports

D, S, I, G, P = Kind.DATAFRAME, Kind.SERIES, Kind.INDEX, Kind.GROUPBY, Kind.PANDAS
U, O = Kind.UNKNOWN, Kind.OTHER

# --- what pandas functions and methods return ---------------------------------------------------
PD_FUNCS = {
    **dict.fromkeys(["DataFrame", "read_csv", "read_table", "read_excel", "read_json", "read_parquet",
                     "read_sql", "read_sql_query", "read_sql_table", "read_pickle", "read_feather",
                     "read_fwf", "merge", "pivot_table", "crosstab", "get_dummies", "json_normalize",
                     "merge_asof", "merge_ordered", "melt", "wide_to_long"], D),
    "Series": S, "concat": P, "to_numeric": P,
    **dict.fromkeys(["Index", "RangeIndex", "DatetimeIndex", "MultiIndex", "CategoricalIndex",
                     "date_range", "period_range", "timedelta_range", "Int64Index", "Float64Index",
                     "UInt64Index"], I),
}
DF_TO_DF = set("""copy head tail sort_values sort_index reset_index drop drop_duplicates dropna fillna ffill bfill
merge join assign query rename astype set_index pivot pivot_table melt sample filter where mask
transpose abs round clip replace explode nlargest nsmallest select_dtypes reindex append applymap
map interpolate convert_dtypes infer_objects set_axis rename_axis add_prefix add_suffix combine_first
update_frame swapaxes backfill pad shift diff cumsum cumprod cummax cummin rank pct_change truncate
stack unstack corr cov describe isna isnull notna notnull duplicated_frame""".split())
DF_TO_SERIES = set("""sum mean median std var min max count nunique idxmax idxmin mad prod sem skew kurt
quantile mode_series dtypes memory_usage duplicated any all""".split())
SERIES_TO_SERIES = set("""copy head tail sort_values sort_index dropna fillna ffill bfill map apply astype abs
round replace cumsum cumprod cummax cummin diff shift value_counts rank clip where mask append
interpolate isna isnull notna notnull between isin rename drop drop_duplicates nlargest nsmallest
sample reindex backfill pad pct_change combine_first explode mode""".split())
TO_LIST = {"tolist", "to_list"}
TO_DICT = {"to_dict"}
GROUPBY_TO_PANDAS = set("""agg aggregate sum mean median std var min max count nunique first last size
apply transform cumsum cumcount ngroup head tail describe prod quantile filter""".split())
FRAME_ATTRS = {"T": D, "index": I, "columns": I}
NON_COLUMN_ATTRS = set("""values shape size ndim dtypes empty loc iloc at iat str dt cat plot sparse
attrs flags axes""".split())

BUILTINS = {"list": Kind.LIST, "sorted": Kind.LIST, "dict": Kind.DICT, "str": Kind.STR,
            **dict.fromkeys(["len", "int", "float", "sum", "min", "max", "abs", "round", "bool", "set",
                             "tuple", "range", "enumerate", "zip", "open", "print", "frozenset"], O)}

# Method names that only pandas (still) has. An unknown receiver is treated as pandas for these.
DISTINCTIVE = {"iteritems", "mad", "lookup", "is_monotonic", "applymap", "backfill", "swapaxes"}

_METHOD_RULES: dict[str, list[Rule]] = {}
for _r in RULES:
    if _r.method:
        for _m in _r.method.split("|"):
            _METHOD_RULES.setdefault(_m, []).append(_r)
_MODULE_RULES = {name: r for r in RULES if r.module_attr for name in r.module_attr.split("|")}
_KEYWORD_RULES = [r for r in RULES if r.keyword]


def join(a: Kind | None, b: Kind) -> Kind:
    if a is None or a == b:
        return b
    if a.is_pandas and b.is_pandas:
        return P
    return U


@dataclass
class Finding:
    file: str
    rule_id: str
    line: int
    col: int
    end_line: int
    end_col: int
    receiver_kind: str
    confidence: str  # "certain" or "possible"
    snippet: str
    detail: str = ""  # e.g. which variant (Int64Index) or why it's possible
    node: ast.AST | None = field(default=None, compare=False, repr=False)

    @property
    def rule(self) -> Rule:
        return BY_ID[self.rule_id]

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("node", None)
        d.update(title=self.rule.title, status=self.rule.status, strategy=self.rule.strategy)
        return d


def _dotted(node: ast.AST) -> str | None:
    """`self.df` -> "self.df", `df` -> "df"; anything more complex -> None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


class _Analyzer:
    def __init__(self, path: str, source: str, tree: ast.Module, imports: Imports):
        self.path, self.source, self.tree, self.imp = path, source, tree, imports
        self.lines = source.splitlines()
        self.findings: list[Finding] = []
        self.func_returns: dict[str, Kind] = {}
        self.class_attrs: dict[str, dict[str, Kind]] = {}
        # Instances of classes defined in this file are known not to be pandas objects.
        self.local_classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        self.recording = False

    # ------------------------------------------------------------------ type of an expression
    def kind(self, e: ast.AST | None, env: dict[str, Kind]) -> Kind:
        if e is None:
            return U
        if isinstance(e, ast.Name):
            return env.get(e.id, U)
        if isinstance(e, ast.Attribute):
            dotted = _dotted(e)
            if dotted and dotted in env:
                return env[dotted]
            base = self.kind(e.value, env)
            if base == D or base == P:
                if e.attr in FRAME_ATTRS:
                    return FRAME_ATTRS[e.attr]
                if e.attr in NON_COLUMN_ATTRS or e.attr in DF_TO_DF or e.attr in DF_TO_SERIES:
                    return O
                return S if base == D else P  # df.colname is column access
            if base == S:
                return I if e.attr == "index" else O
            return U
        if isinstance(e, ast.Call):
            return self._call_kind(e, env)
        if isinstance(e, ast.Subscript):
            v = e.value
            if isinstance(v, ast.Attribute) and v.attr in ("loc", "iloc") and self.kind(v.value, env).is_pandas:
                return P
            base = self.kind(v, env)
            if base == D:
                sl = e.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    return S
                if isinstance(sl, ast.List):
                    return D
                return P  # boolean mask, slice, ...
            if base == G:
                return G
            if base == P:
                return P  # frame or series: a column, a row selection or a mask is still pandas
            if base == S and not isinstance(e.slice, ast.Constant):
                return P
            return U
        if isinstance(e, (ast.List, ast.ListComp)):
            return Kind.LIST
        if isinstance(e, (ast.Dict, ast.DictComp)):
            return Kind.DICT
        if isinstance(e, ast.JoinedStr) or (isinstance(e, ast.Constant) and isinstance(e.value, str)):
            return Kind.STR
        if isinstance(e, (ast.Constant, ast.Tuple, ast.Set, ast.SetComp, ast.GeneratorExp, ast.Lambda)):
            return O
        if isinstance(e, ast.BinOp):
            left, right = self.kind(e.left, env), self.kind(e.right, env)
            if left.is_pandas:
                return left
            if right.is_pandas:
                return right
            return left if left == right else U
        if isinstance(e, (ast.Compare, ast.UnaryOp)):
            inner = self.kind(e.left if isinstance(e, ast.Compare) else e.operand, env)
            return P if inner.is_pandas else O
        if isinstance(e, ast.IfExp):
            return join(self.kind(e.body, env), self.kind(e.orelse, env))
        if isinstance(e, ast.Await):
            return self.kind(e.value, env)
        return U

    def _call_kind(self, e: ast.Call, env: dict[str, Kind]) -> Kind:
        f = e.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in self.imp.pandas_modules:
            return PD_FUNCS.get(f.attr, U)
        if isinstance(f, ast.Name):
            if f.id in self.imp.pandas_names:
                return PD_FUNCS.get(self.imp.pandas_names[f.id], U)
            if f.id in self.func_returns:
                return self.func_returns[f.id]
            if f.id in self.local_classes:
                return O
            return BUILTINS.get(f.id, U)
        if isinstance(f, ast.Attribute):
            if isinstance(f.value, ast.Name) and f.value.id == "self" and f"self.{f.attr}()" in env:
                return env[f"self.{f.attr}()"]
            recv = self.kind(f.value, env)
            m = f.attr
            if m in TO_LIST:
                return Kind.LIST
            if m in TO_DICT:
                return Kind.DICT
            if recv == D:
                if m == "groupby":
                    return G
                if m in DF_TO_DF:
                    return D
                if m in DF_TO_SERIES:
                    return S
                return P if m in ("apply", "pipe", "squeeze") else O
            if recv == S:
                if m == "groupby":
                    return G
                if m == "to_frame":
                    return D
                if m in SERIES_TO_SERIES:
                    return S
                return P if m in ("reset_index", "pipe", "squeeze") else O
            if recv == G:
                return P if m in GROUPBY_TO_PANDAS else O
            if recv == I:
                return Kind.LIST if m in TO_LIST else I
            if recv == P:
                if m == "groupby":
                    return G
                return P if m in DF_TO_DF | SERIES_TO_SERIES | {"apply", "pipe", "squeeze", "to_frame"} else O
            if recv == Kind.STR:
                return Kind.LIST if m in ("split", "rsplit", "splitlines") else Kind.STR
            if recv in (Kind.LIST, Kind.DICT):
                return recv if m == "copy" else U
        return U

    def annotation_kind(self, ann: ast.AST | None) -> Kind | None:
        if ann is None:
            return None
        if isinstance(ann, ast.Constant) and isinstance(ann.value, str):  # "pd.DataFrame"
            try:
                ann = ast.parse(ann.value, mode="eval").body
            except SyntaxError:
                return None
        name = None
        if isinstance(ann, ast.Attribute) and isinstance(ann.value, ast.Name) and ann.value.id in self.imp.pandas_modules:
            name = ann.attr
        elif isinstance(ann, ast.Name):
            if ann.id in self.imp.pandas_names:
                name = self.imp.pandas_names[ann.id]
            elif ann.id in ("list", "List"):
                return Kind.LIST
            elif ann.id in ("dict", "Dict"):
                return Kind.DICT
            elif ann.id == "str":
                return Kind.STR
            elif ann.id in ("int", "float", "bool"):
                return O
        elif isinstance(ann, ast.Subscript):
            base = ann.value.id if isinstance(ann.value, ast.Name) else getattr(ann.value, "attr", None)
            if base in ("list", "List", "Sequence"):
                return Kind.LIST
            if base in ("dict", "Dict", "Mapping"):
                return Kind.DICT
        if name == "DataFrame":
            return D
        if name == "Series":
            return S
        if name and name.endswith("Index"):
            return I
        return None

    # ------------------------------------------------------------------ findings
    def _add(self, rule: Rule, node: ast.AST, kind: Kind, confidence: str, detail: str = "") -> None:
        if not self.recording:
            return
        line = node.lineno
        self.findings.append(Finding(
            file=self.path, rule_id=rule.id, line=line, col=node.col_offset,
            end_line=node.end_lineno or line, end_col=node.end_col_offset or 0,
            receiver_kind=kind.value, confidence=confidence,
            snippet=self.lines[line - 1].strip() if line - 1 < len(self.lines) else "",
            detail=detail, node=node,
        ))

    def _confidence(self, kind: Kind, rule: Rule, method: str) -> str | None:
        if kind in rule.receivers or (kind.is_pandas and kind == P):
            return "certain"
        if kind == U:
            if not self.imp.uses_pandas:
                return None  # no pandas in this file: an unknown object's .append is not our business
            return "certain" if method in DISTINCTIVE else "possible"
        return None  # list, dict, str, other, or a pandas kind this rule doesn't apply to

    def check_expr(self, root: ast.AST, env: dict[str, Kind]) -> None:
        for node in ast.walk(root):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)) and node is not root:
                continue
            if isinstance(node, ast.Attribute):
                self._check_attribute(node, env)
            if isinstance(node, ast.Call):
                self._check_keywords(node, env)
            if isinstance(node, ast.Name) and node.id in self.imp.pandas_names and isinstance(node.ctx, ast.Load):
                original = self.imp.pandas_names[node.id]
                if original in _MODULE_RULES:
                    self._add(_MODULE_RULES[original], node, P, "certain", detail=f"from-import:{original}")

    def _check_attribute(self, node: ast.Attribute, env: dict[str, Kind]) -> None:
        # pandas module attributes: pd.np, pd.datetime, pd.Int64Index, pd.value_counts
        if isinstance(node.value, ast.Name) and node.value.id in self.imp.pandas_modules:
            if node.attr in _MODULE_RULES:
                self._add(_MODULE_RULES[node.attr], node, P, "certain", detail=node.attr)
            return
        rules = _METHOD_RULES.get(node.attr)
        if not rules:
            return
        kind = self.kind(node.value, env)
        for rule in rules:
            conf = self._confidence(kind, rule, node.attr)
            if conf is None:
                continue
            # property vs call must match (is_monotonic is a property; the others are calls)
            parent_is_call = getattr(node, "_apishift_called", False)
            if rule.is_call is not None and rule.is_call != parent_is_call:
                continue
            if rule.id == "PD003" and kind == G:
                continue
            self._add(rule, node, kind, conf, detail=node.attr)
            break

    def _check_keywords(self, node: ast.Call, env: dict[str, Kind]) -> None:
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else (self.imp.pandas_names.get(f.id) if isinstance(f, ast.Name) else None)
        if not name:
            return
        for rule in _KEYWORD_RULES:
            if name not in rule.call_of:
                continue
            kw = next((k for k in node.keywords if k.arg == rule.keyword), None)
            if kw is None:
                continue
            if rule.keyword_value is not None and not (isinstance(kw.value, ast.Constant) and kw.value.value == rule.keyword_value):
                continue
            if isinstance(f, ast.Attribute):
                is_module = isinstance(f.value, ast.Name) and f.value.id in self.imp.pandas_modules
                kind = P if is_module else self.kind(f.value, env)
                if not is_module and kind not in (D, S, P, G, U):
                    continue
                if kind == U and not self.imp.uses_pandas:
                    continue
            else:
                kind = P
            self._add(rule, node, kind, "certain", detail=f"{name}({rule.keyword}=)")

    # ------------------------------------------------------------------ statements
    def bind(self, target: ast.AST, kind: Kind, env: dict[str, Kind], nested: bool) -> None:
        if isinstance(target, (ast.Tuple, ast.List)):
            for t in target.elts:
                self.bind(t, U, env, nested)
            return
        key = _dotted(target)
        if key:
            env[key] = join(env.get(key), kind) if nested else kind

    def run_block(self, body: list[ast.stmt], env: dict[str, Kind], nested: bool = False) -> None:
        for stmt in body:
            self.run_stmt(stmt, env, nested)

    def run_stmt(self, stmt: ast.stmt, env: dict[str, Kind], nested: bool) -> None:
        _mark_calls(stmt)
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.run_function(stmt, env)
            return
        if isinstance(stmt, ast.ClassDef):
            self.run_class(stmt, env)
            return
        if isinstance(stmt, ast.Assign):
            self.check_expr(stmt, env)
            k = self.kind(stmt.value, env)
            for t in stmt.targets:
                self.bind(t, k, env, nested)
            return
        if isinstance(stmt, ast.AnnAssign):
            self.check_expr(stmt, env)
            k = self.annotation_kind(stmt.annotation) or self.kind(stmt.value, env)
            self.bind(stmt.target, k, env, nested)
            return
        if isinstance(stmt, ast.AugAssign):
            self.check_expr(stmt, env)
            return
        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            self.check_expr(stmt.iter, env)
            self._bind_loop_target(stmt, env)
            self.run_block(stmt.body, env, nested=True)
            self.run_block(stmt.orelse, env, nested=True)
            return
        if isinstance(stmt, (ast.If, ast.While)):
            self.check_expr(stmt.test, env)
            self.run_block(stmt.body, env, nested=True)
            self.run_block(stmt.orelse, env, nested=True)
            return
        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                self.check_expr(item.context_expr, env)
            self.run_block(stmt.body, env, nested)
            return
        if isinstance(stmt, ast.Try) or type(stmt).__name__ == "TryStar":
            self.run_block(stmt.body, env, nested=True)
            for h in stmt.handlers:
                self.run_block(h.body, env, nested=True)
            self.run_block(stmt.orelse, env, nested=True)
            self.run_block(stmt.finalbody, env, nested=True)
            return
        if isinstance(stmt, ast.Match):
            self.check_expr(stmt.subject, env)
            for case in stmt.cases:
                self.run_block(case.body, env, nested=True)
            return
        self.check_expr(stmt, env)

    def _bind_loop_target(self, stmt: ast.For | ast.AsyncFor, env: dict[str, Kind]) -> None:
        it, tgt = stmt.iter, stmt.target
        if isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute):
            recv = self.kind(it.func.value, env)
            m = it.func.attr
            if recv.is_pandas and m in ("items", "iteritems", "iterrows") and isinstance(tgt, ast.Tuple) and len(tgt.elts) == 2:
                self.bind(tgt.elts[0], U, env, True)
                self.bind(tgt.elts[1], S, env, True)
                return
        # for key, group in df.groupby(...): each group is a DataFrame (or Series)
        if self.kind(it, env) == G and isinstance(tgt, ast.Tuple) and len(tgt.elts) == 2:
            self.bind(tgt.elts[0], U, env, True)
            self.bind(tgt.elts[1], P, env, True)
            return
        self.bind(tgt, U, env, True)

    def run_function(self, fn: ast.FunctionDef | ast.AsyncFunctionDef, outer: dict[str, Kind],
                     self_attrs: dict[str, Kind] | None = None) -> Kind:
        env = dict(outer)
        args = fn.args
        positional = args.posonlyargs + args.args
        defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
        for a, default in zip(positional, defaults):
            env[a.arg] = self.annotation_kind(a.annotation) or (self.kind(default, env) if default is not None and not (isinstance(default, ast.Constant) and default.value is None) else U)
        for a, default in zip(args.kwonlyargs, args.kw_defaults):
            env[a.arg] = self.annotation_kind(a.annotation) or U
        if self_attrs:
            env.update(self_attrs)
        for d in fn.decorator_list:
            self.check_expr(d, env)
        returns: Kind | None = self.annotation_kind(fn.returns)
        self.run_block(fn.body, env)
        self._last_env = env  # run_class reads self.<attr> kinds from here
        if returns is None:
            for node in ast.walk(fn):
                if isinstance(node, ast.Return) and node.value is not None:
                    returns = join(returns, self.kind(node.value, env))
        return returns or U

    def run_class(self, cls: ast.ClassDef, outer: dict[str, Kind]) -> None:
        attrs = self.class_attrs.setdefault(cls.name, {})
        for stmt in cls.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                ret = self.run_function(stmt, outer, attrs)
                attrs[f"self.{stmt.name}()"] = ret
                # Remember what this method left in self.<x> for the other methods. Read it from the
                # method's own environment, so `self.df = df` sees the parameter's annotation.
                for key, kind in self._last_env.items():
                    if key.startswith("self.") and not key.endswith("()"):
                        attrs[key] = join(attrs.get(key), kind)
            else:
                self.run_stmt(stmt, outer, nested=False)

    def analyze(self) -> list[Finding]:
        # Pass 1-2 (no findings recorded): learn what functions return and what self.x holds.
        self.recording = False
        for _ in range(2):
            env: dict[str, Kind] = {}
            for stmt in self.tree.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.func_returns[stmt.name] = self.run_function(stmt, env)
                else:
                    self.run_stmt(stmt, env, nested=False)
        # Pass 3: record findings.
        self.recording = True
        env = {}
        self.run_block(self.tree.body, env)
        # from-imports of removed names break at import time; flag the import itself
        for node in self.imp.pandas_from_nodes:
            for a in node.names:
                if a.name in _MODULE_RULES:
                    self._add(_MODULE_RULES[a.name], node, P, "certain", detail=f"import:{a.name}")
        return _dedupe(self.findings)


def _mark_calls(stmt: ast.AST) -> None:
    """Tag Attribute nodes that are the function part of a Call (`x.f(...)` vs `x.f`)."""
    for node in ast.walk(stmt):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            node.func._apishift_called = True  # type: ignore[attr-defined]


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in sorted(findings, key=lambda f: (f.line, f.col, f.rule_id)):
        key = (f.rule_id, f.line, f.col, f.end_line, f.end_col)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def scan_source(source: str, path: str = "<string>") -> list[Finding]:
    """Scan one file's source. Raises SyntaxError if it isn't valid Python."""
    tree = ast.parse(source)
    return _Analyzer(path, source, tree, resolve_imports(tree)).analyze()


def scan_file(path: Path, root: Path | None = None) -> list[Finding]:
    rel = str(path.relative_to(root)) if root else str(path)
    return scan_source(path.read_text(encoding="utf-8", errors="replace"), rel.replace("\\", "/"))


SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", "build", "dist", ".tox", ".mypy_cache",
             "site-packages", ".pytest_cache"}


def is_test_file(rel_parts: tuple[str, ...]) -> bool:
    name = rel_parts[-1]
    return "tests" in rel_parts or "test" in rel_parts or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def python_files(root: Path, include_tests: bool = False) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*.py")):
        parts = p.relative_to(root).parts
        if set(parts) & SKIP_DIRS:
            continue
        if not include_tests and is_test_file(parts):
            continue
        out.append(p)
    return out


@dataclass
class ScanResult:
    findings: list[Finding]
    errors: list[str]  # files that could not be parsed: never skipped silently
    files_scanned: int


def scan_path(root: Path, include_tests: bool = False) -> ScanResult:
    root = root.resolve()
    files = [root] if root.is_file() else python_files(root, include_tests)
    base = root.parent if root.is_file() else root
    findings: list[Finding] = []
    errors: list[str] = []
    for p in files:
        try:
            findings.extend(scan_file(p, base))
        except SyntaxError as exc:
            errors.append(f"{p.relative_to(base).as_posix()}:{exc.lineno}: could not parse ({exc.msg})")
    return ScanResult(findings, errors, len(files))
