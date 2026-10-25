"""Which names in a file refer to pandas, NumPy and datetime.

Plain English: `pd.np` is only a problem if `pd` really is pandas. This reads the import
statements, so the scanner knows that `pd`, `pandas` or `P` (whatever the alias) means pandas, and
that `DF` came from `from pandas import DataFrame as DF`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class Imports:
    pandas_modules: set[str] = field(default_factory=set)  # names bound to the pandas module
    pandas_names: dict[str, str] = field(default_factory=dict)  # local name -> pandas attribute
    pandas_from_nodes: list[ast.ImportFrom] = field(default_factory=list)
    numpy_modules: set[str] = field(default_factory=set)
    datetime_module: set[str] = field(default_factory=set)  # `import datetime` (as ...)
    datetime_class: set[str] = field(default_factory=set)  # `from datetime import datetime` (as ...)
    bound_names: set[str] = field(default_factory=set)  # every top-level name bound by an import
    last_import_line: int = 0  # 1-based line of the end of the last top-level import (0 = none)

    @property
    def uses_pandas(self) -> bool:
        return bool(self.pandas_modules or self.pandas_names)


def resolve_imports(tree: ast.Module) -> Imports:
    imp = Imports()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                local = a.asname or a.name.split(".")[0]
                imp.bound_names.add(local)
                if a.name == "pandas":
                    imp.pandas_modules.add(local)
                elif a.name == "numpy":
                    imp.numpy_modules.add(local)
                elif a.name == "datetime":
                    imp.datetime_module.add(local)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for a in node.names:
                local = a.asname or a.name
                imp.bound_names.add(local)
                if node.module == "pandas":
                    imp.pandas_names[local] = a.name
                elif node.module == "datetime" and a.name == "datetime":
                    imp.datetime_class.add(local)
            if node.module == "pandas":
                imp.pandas_from_nodes.append(node)
    for node in tree.body:  # where new imports should go
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imp.last_import_line = node.end_lineno or node.lineno
    return imp
