"""Command line: `apishift <command>` (or `python -m apishift <command>`).

    scan PATH          list removed / deprecated pandas APIs (text, json or sarif)
    fix PATH           migrate them, verified by the tests; --write applies, --pr opens a pull request
    rules              print the rule catalogue (and regenerate docs/RULES.md with --write)
    bench-check        prove every benchmark case is fair (no LLM)
    eval               score codemod-only vs LLM one-shot vs APIShift on the benchmark
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import PROJECT_ROOT, Settings


def _log(msg: str) -> None:
    print(msg, flush=True)


def cmd_scan(args) -> int:
    from .analysis import scan_path
    from .analysis.sarif import to_sarif

    res = scan_path(Path(args.path), include_tests=args.include_tests)
    if args.format == "json":
        print(json.dumps({"findings": [f.to_dict() for f in res.findings], "errors": res.errors}, indent=2))
    elif args.format == "sarif":
        print(json.dumps(to_sarif(res.findings), indent=2))
    else:
        for f in res.findings:
            mark = "?" if f.confidence == "possible" else "!"
            print(f"{f.file}:{f.line}:{f.col + 1}: {mark} {f.rule_id} {f.rule.title} [{f.rule.status}] {f.snippet}")
        for e in res.errors:
            print(f"warning: {e}", file=sys.stderr)
        n_certain = sum(f.confidence == "certain" for f in res.findings)
        print(f"\n{len(res.findings)} findings ({n_certain} certain, {len(res.findings) - n_certain} possible) "
              f"in {res.files_scanned} files")
    certain = any(f.confidence == "certain" for f in res.findings)
    return 1 if (certain and args.fail_on_findings) else 0


def cmd_fix(args) -> int:
    from .fix.llm import make_provider
    from .fix.orchestrator import Options, migrate
    from .report import pr_body

    settings = Settings()
    provider = None if args.no_llm else make_provider(settings)
    if provider is None and not args.no_llm:
        _log("No LLM key found (GROQ_API_KEY or ANTHROPIC_API_KEY): running codemods only.")
    opts = Options(use_llm=provider is not None, max_attempts=settings.max_attempts, strict=args.strict)
    repo = Path(args.path).resolve()
    res = migrate(repo, provider, opts, log=_log, timeout=settings.test_timeout)
    body = pr_body(res)
    if args.report:
        Path(args.report).write_text(body, encoding="utf-8")
    if not res.changed_files:
        _log("Nothing to change.")
        return 0
    for f in res.changed_files:
        _log(f.diff())
    if args.write or args.pr:
        for f in res.changed_files:
            (repo / f.path).write_text(f.final, encoding="utf-8", newline="")
        _log(f"Wrote {len(res.changed_files)} files.")
    if args.pr:
        from .github.pr import open_pull_request

        url = open_pull_request(repo, res, body, branch=args.branch, base=args.base)
        _log(f"Pull request: {url}")
    else:
        _log("\n" + body)
    return 1 if res.needs_human else 0


def cmd_rules(args) -> int:
    from .rules import rules_markdown

    md = rules_markdown()
    if args.write:
        (PROJECT_ROOT / "docs" / "RULES.md").write_text(md, encoding="utf-8")
        _log("Wrote docs/RULES.md")
    else:
        print(md)
    return 0


def cmd_bench_check(args) -> int:
    from .eval.benchmark import check, load_cases

    results = check(load_cases(only=args.case))
    for r in results:
        _log(f"{'ok  ' if r.ok else 'FAIL'} {r.case}" + "".join(f"\n       {p}" for p in r.problems))
    bad = [r for r in results if not r.ok]
    _log(f"\n{len(results) - len(bad)}/{len(results)} cases valid")
    return 1 if bad else 0


def cmd_eval(args) -> int:
    from .eval.report import run_eval

    run_eval(modes=args.modes.split(","), only=args.case, log=_log)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="apishift", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="find removed / deprecated pandas APIs")
    s.add_argument("path", nargs="?", default=".")
    s.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    s.add_argument("--include-tests", action="store_true")
    s.add_argument("--fail-on-findings", action="store_true", help="exit 1 if anything certain is found (for CI)")
    s.set_defaults(fn=cmd_scan)

    f = sub.add_parser("fix", help="migrate and verify with the tests")
    f.add_argument("path", nargs="?", default=".")
    f.add_argument("--write", action="store_true", help="apply the accepted changes to the files")
    f.add_argument("--pr", action="store_true", help="commit on a branch, push and open a pull request")
    f.add_argument("--branch", default="apishift/pandas-2")
    f.add_argument("--base", default=None, help="base branch for the PR (default: the current branch)")
    f.add_argument("--strict", action="store_true", help="treat FutureWarning as test failures")
    f.add_argument("--no-llm", action="store_true", help="codemods only")
    f.add_argument("--report", help="also write the PR description to this file")
    f.set_defaults(fn=cmd_fix)

    r = sub.add_parser("rules", help="print the rule catalogue")
    r.add_argument("--write", action="store_true", help="regenerate docs/RULES.md")
    r.set_defaults(fn=cmd_rules)

    b = sub.add_parser("bench-check", help="validate the benchmark cases (no LLM)")
    b.add_argument("--case", help="only cases whose id contains this text")
    b.set_defaults(fn=cmd_bench_check)

    e = sub.add_parser("eval", help="score the methods on the benchmark")
    e.add_argument("--modes", default="codemod,llm-one-shot,apishift")
    e.add_argument("--case", help="only cases whose id contains this text")
    e.set_defaults(fn=cmd_eval)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
