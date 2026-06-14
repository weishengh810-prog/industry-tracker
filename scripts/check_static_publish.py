from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"
REQUIRED_FILES = (
    Path("index.html"),
    Path("data/meta.json"),
    Path("data/ranking.json"),
    Path("data/history.csv"),
)
SENSITIVE_PATTERNS = (
    re.compile(rb"PRIVATE KEY", re.IGNORECASE),
    re.compile(rb"BEGIN OPENSSH", re.IGNORECASE),
    re.compile(rb"ghp_", re.IGNORECASE),
    re.compile(rb"github_pat_", re.IGNORECASE),
    re.compile(rb"password\s*=", re.IGNORECASE),
    re.compile(rb"token\s*=", re.IGNORECASE),
)


def _report(passed: bool, message: str) -> bool:
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {message}")
    return passed


def _load_json(path: Path) -> tuple[bool, object | None]:
    try:
        return True, json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _report(False, f"{path.name} is not valid JSON: {exc}")
        return False, None


def check_static_publish(docs_dir: Path | str = DEFAULT_DOCS_DIR) -> bool:
    root = Path(docs_dir).resolve()
    results: list[bool] = []

    for relative_path in REQUIRED_FILES:
        path = root / relative_path
        results.append(
            _report(path.is_file(), f"required file exists: {relative_path.as_posix()}")
        )

    index_path = root / "index.html"
    if index_path.is_file():
        try:
            index_html = index_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            results.append(_report(False, f"index.html is readable UTF-8: {exc}"))
        else:
            results.append(
                _report("/api/" not in index_html, "index.html contains no /api/ reference")
            )

    sensitive_matches: list[str] = []
    if root.is_dir():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            try:
                content = path.read_bytes()
            except OSError as exc:
                sensitive_matches.append(f"{path.relative_to(root).as_posix()} ({exc})")
                continue
            if any(pattern.search(content) for pattern in SENSITIVE_PATTERNS):
                sensitive_matches.append(path.relative_to(root).as_posix())
    results.append(
        _report(
            not sensitive_matches,
            "docs contains no sensitive credential pattern"
            if not sensitive_matches
            else "sensitive credential pattern found in: "
            + ", ".join(sensitive_matches),
        )
    )

    meta_path = root / "data" / "meta.json"
    if meta_path.is_file():
        valid_json, meta = _load_json(meta_path)
        results.append(valid_json)
        if valid_json:
            results.append(
                _report(
                    isinstance(meta, dict) and "last_updated" in meta,
                    "meta.json contains last_updated",
                )
            )

    ranking_path = root / "data" / "ranking.json"
    if ranking_path.is_file():
        valid_json, ranking = _load_json(ranking_path)
        results.append(valid_json)
        if valid_json:
            results.append(
                _report(
                    isinstance(ranking, list) and bool(ranking),
                    "ranking.json is a non-empty array",
                )
            )

    history_path = root / "data" / "history.csv"
    if history_path.is_file():
        try:
            with history_path.open(encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), [])
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            results.append(_report(False, f"history.csv is readable: {exc}"))
        else:
            results.append(
                _report(
                    header[:3] == ["date", "industry", "composite_score"],
                    "history.csv starts with date,industry,composite_score",
                )
            )

    passed = bool(results) and all(results)
    print(
        "[PASS] static publish check completed"
        if passed
        else "[FAIL] static publish check failed"
    )
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate GitHub Pages static dashboard output."
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=DEFAULT_DOCS_DIR,
        help="Static docs directory to validate (default: repository docs/).",
    )
    args = parser.parse_args()
    raise SystemExit(0 if check_static_publish(args.docs_dir) else 1)


if __name__ == "__main__":
    main()
