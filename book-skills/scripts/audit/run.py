"""Book QA Audit System: pluggable check framework.

Discovers and runs individual check modules from the checks/ directory.
Each check is a standalone .py file that exports:
    PRIORITY: str          ("P0", "P1", "P2", "P3")
    CHECK_ID: str          (e.g. "BROKEN_XREF")
    DESCRIPTION: str       (human-readable one-liner)
    def run(filepath, html, context) -> list[Issue]

Usage:
    python -m scripts.audit.run                    # run all checks
    python -m scripts.audit.run --priority P0      # only critical
    python -m scripts.audit.run --checks BROKEN_XREF,DUP_FIGURE_NUM
    python -m scripts.audit.run --list             # list available checks
    python -m scripts.audit.run --json             # machine-readable output
    python -m scripts.audit.run --files section-5.1.html
"""
import argparse
import importlib
import json
import sys
import time
from collections import defaultdict, namedtuple
from pathlib import Path

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# --- Configuration (override per-book via env or CLI) ---
BOOK_ROOT = Path(r"E:\Projects\LLMCourse")
SKIP_DIRS = {"vendor", "node_modules", ".git", "deprecated", "__pycache__", "agents", "_archive", "templates"}
CHECKS_DIR = Path(__file__).parent / "checks"


def find_html_files(book_root, skip_dirs, file_filter=None):
    """Yield all HTML files, excluding skip dirs."""
    for f in book_root.rglob("*.html"):
        if any(s in f.parts for s in skip_dirs):
            continue
        if file_filter and not any(flt in str(f) for flt in file_filter):
            continue
        yield f


def discover_checks(checks_dir):
    """Import all check modules from the checks directory."""
    checks = []
    for py_file in sorted(checks_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"audit_check_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            print(f"WARNING: Failed to load check {py_file.name}: {e}", file=sys.stderr)
            continue
        required = ("PRIORITY", "CHECK_ID", "DESCRIPTION", "run")
        if all(hasattr(mod, attr) for attr in required):
            checks.append(mod)
        else:
            missing = [a for a in required if not hasattr(mod, a)]
            print(f"WARNING: {py_file.name} missing: {', '.join(missing)}", file=sys.stderr)
    return checks


def build_context(book_root, skip_dirs):
    """Build shared context dict passed to every check."""
    all_files = set()
    all_html = set()
    for f in book_root.rglob("*"):
        if f.is_file() and not any(s in f.parts for s in skip_dirs):
            all_files.add(f.resolve())
            if f.suffix == ".html":
                all_html.add(f.resolve())
    return {
        "book_root": book_root,
        "all_files": all_files,
        "all_html": all_html,
    }


def run_checks(checks, html_files, context, priority_filter=None, check_filter=None):
    """Run all checks on all files, return list of Issues."""
    active_checks = checks
    if priority_filter:
        active_checks = [c for c in active_checks if c.PRIORITY in priority_filter]
    if check_filter:
        active_checks = [c for c in active_checks if c.CHECK_ID in check_filter]

    all_issues = []
    file_count = 0
    book_root = context["book_root"]

    for filepath in html_files:
        file_count += 1
        try:
            html = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"WARNING: Cannot read {filepath}: {e}", file=sys.stderr)
            continue

        for check in active_checks:
            try:
                issues = check.run(filepath, html, context)
                all_issues.extend(issues)
            except Exception as e:
                rel = filepath.relative_to(book_root)
                print(f"WARNING: {check.CHECK_ID} failed on {rel}: {e}", file=sys.stderr)

    # Run cross-file checks (if any check has a run_cross_file function)
    for check in active_checks:
        if hasattr(check, "run_cross_file"):
            try:
                issues = check.run_cross_file(context)
                all_issues.extend(issues)
            except Exception as e:
                print(f"WARNING: {check.CHECK_ID} cross-file failed: {e}", file=sys.stderr)

    return all_issues, file_count


def print_text(issues, file_count, book_root):
    """Print human-readable output grouped by priority and check."""
    grouped = defaultdict(lambda: defaultdict(list))
    for issue in issues:
        grouped[issue.priority][issue.check_id].append(issue)

    for priority in ("P0", "P1", "P2", "P3"):
        if priority not in grouped:
            continue
        print(f"\n{'=' * 70}")
        print(f"  {priority} issues")
        print(f"{'=' * 70}")
        for check_id in sorted(grouped[priority]):
            check_issues = grouped[priority][check_id]
            print(f"\n  [{check_id}] ({len(check_issues)} issues)")
            for issue in sorted(check_issues, key=lambda i: (str(i.filepath), i.line)):
                try:
                    rel = issue.filepath.relative_to(book_root)
                except ValueError:
                    rel = issue.filepath
                print(f"  [{check_id}] {rel}:{issue.line}  {issue.message}")

    # Summary
    counts = defaultdict(int)
    for issue in issues:
        counts[issue.priority] += 1
    total = sum(counts.values())
    parts = ", ".join(f"{counts.get(p, 0)} {p}" for p in ("P0", "P1", "P2", "P3") if counts.get(p))
    print(f"\n{'=' * 70}")
    print(f"Scanned {file_count} files. Found {total} issues: {parts}.")


def print_json(issues, file_count, book_root):
    """Print JSON output."""
    data = {
        "file_count": file_count,
        "issue_count": len(issues),
        "issues": [
            {
                "priority": i.priority,
                "check_id": i.check_id,
                "file": str(i.filepath.relative_to(book_root)),
                "line": i.line,
                "message": i.message,
            }
            for i in issues
        ],
    }
    json.dump(data, sys.stdout, indent=2)
    print()


def list_checks(checks):
    """Print available checks."""
    print(f"{'ID':<25} {'Priority':<8} Description")
    print("-" * 70)
    for c in sorted(checks, key=lambda c: (c.PRIORITY, c.CHECK_ID)):
        print(f"{c.CHECK_ID:<25} {c.PRIORITY:<8} {c.DESCRIPTION}")


def main():
    parser = argparse.ArgumentParser(description="Book QA Audit System")
    parser.add_argument("--priority", help="Filter by priority (e.g. P0, P0+P1)")
    parser.add_argument("--checks", help="Comma-separated check IDs to run")
    parser.add_argument("--files", nargs="*", help="Only scan files matching these substrings")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--list", action="store_true", help="List available checks")
    parser.add_argument("--root", default=str(BOOK_ROOT), help="Book root directory")
    args = parser.parse_args()

    # Fix Windows UTF-8 output
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    book_root = Path(args.root)
    checks = discover_checks(CHECKS_DIR)

    if args.list:
        list_checks(checks)
        return

    if not checks:
        print("ERROR: No checks found in", CHECKS_DIR, file=sys.stderr)
        sys.exit(1)

    priority_filter = None
    if args.priority:
        priority_filter = set(args.priority.replace("+", ",").split(","))

    check_filter = None
    if args.checks:
        check_filter = set(args.checks.split(","))

    start = time.time()
    context = build_context(book_root, SKIP_DIRS)
    html_files = list(find_html_files(book_root, SKIP_DIRS, args.files))
    issues, file_count = run_checks(checks, html_files, context, priority_filter, check_filter)
    elapsed = time.time() - start

    if args.json:
        print_json(issues, file_count, book_root)
    else:
        print_text(issues, file_count, book_root)
        print(f"Completed in {elapsed:.1f}s.")


if __name__ == "__main__":
    main()
