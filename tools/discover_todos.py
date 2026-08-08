"""Discover epic/story todo opportunities across workspace projects.

Usage examples:
    C:\\G\\python.exe tools/discover_todos.py
    C:\\G\\python.exe tools/discover_todos.py --project music --limit 10
    C:\\G\\python.exe tools/discover_todos.py --apply
    C:\\G\\python.exe tools/discover_todos.py --apply --yes
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.priority_scorer import score_priority
from src.utils.todos_db import add_todo, get_open_todos, init_db

WORKSPACE_ROOT = Path("f:/")
PROJECT_ROOTS: dict[str, Path] = {
    "music": WORKSPACE_ROOT / "❤Music",
    "life": WORKSPACE_ROOT / "∞Life",
    "quantum": WORKSPACE_ROOT / "⟨ψ⟩Quantum",
    "ai_manifest": WORKSPACE_ROOT / "👁AI-Manifest",
    "workspace": WORKSPACE_ROOT / "⊕Workspace",
}

# tech-debt mode scans code only (no DB/data access), so ΣCapital is included
# even though it's excluded from epic/story discovery above.
TECH_DEBT_PROJECT_ROOTS: dict[str, Path] = {
    **PROJECT_ROOTS,
    "capital": WORKSPACE_ROOT / "ΣCapital",
}

TECH_DEBT_SEVERITY_THRESHOLD = 7  # auto-write threshold, no approval gate

DISCOVERY_FILES: dict[str, list[str]] = {
    "music": ["AGENT_STARTUP.md", "README.md", "Brand/**/*.html", "docs/**/*.md"],
    "life": ["AGENT_STARTUP.md", "README.md", "docs/**/*.md", "research/**/*.md"],
    "quantum": ["AGENT_STARTUP.md", "README.md", "docs/**/*.md", "research/**/*.md"],
    "ai_manifest": ["AGENT_STARTUP.md", "README.md", "docs/**/*.md", "research/**/*.md"],
    "workspace": ["AGENT_STARTUP.md", "README.md", ".github/FEATURE_REQUESTS.md", "REPO_VISIBILITY.md"],
}

# Deterministic per-category templates for tech-debt narration (no LLM call).
_TECH_DEBT_ACTION_TEMPLATES: dict[str, str] = {
    "complexity": "Refactor {file} into smaller functions — {detail}.",
    "monolith": "Split {file} into focused modules — {detail}.",
    "coupling": "Decouple {file} from its import graph — {detail}.",
    "filesystem": "Consolidate/rename overlapping paths near {file} — {detail}.",
}


# Keywords that strongly indicate a task can be executed autonomously by AI.
_HIGH_AUTONOMY_PATTERNS = re.compile(
    r"auto|schedul|monitor|watch|poll|sync|detect|alert|scan|nightly|weekly|hourly"
    r"|daily|report|digest|pipeline|queue|refresh|batch|background|cron|recurring"
    r"|health.check|depletion|staleness|regression|rescor",
    re.IGNORECASE,
)


def _classify_autonomy(text: str) -> str:
    """Return 'AI' if the task is automatable with minimal human oversight, else 'TYLER'."""
    return "AI" if _HIGH_AUTONOMY_PATTERNS.search(text) else "TYLER"


def _classify_autonomy_level(text: str, source: str) -> str:
    """Return autonomy_level: 'full' for AI+keyword match, 'supervised' for AI+no match, 'human' for TYLER."""
    if source == "TYLER":
        return "human"
    return "full" if _HIGH_AUTONOMY_PATTERNS.search(text) else "supervised"


@dataclass(slots=True)
class Candidate:
    project: str
    text: str
    priority: int
    similar_to: str | None
    source: str = "TYLER"  # 'AI' or 'TYLER', auto-classified by _classify_autonomy
    autonomy_level: str = "supervised"  # 'full', 'supervised', or 'human'
    rationale: str = ""
    implementation_hints: str = ""
    context_snapshot: str = ""
    estimated_effort: str = ""
    dependencies: str = ""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover epic/story-level todo opportunities across projects."
    )
    parser.add_argument(
        "--project",
        choices=sorted(TECH_DEBT_PROJECT_ROOTS.keys()),
        default=None,
        help="Optional single-project scope (default: all projects).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max number of candidate todos to generate before review.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write approved todos to the DB. Without this, it is dry-run only.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts and insert all shown candidates in --apply mode.",
    )
    parser.add_argument(
        "--mode",
        choices=["discovery", "tech-debt"],
        default="discovery",
        help="'discovery' (default) finds epic/story todos. 'tech-debt' scans for "
             "code-quality/refactor opportunities (radon-ranked, deterministic narration) "
             "and auto-writes severity>=7 findings to workspace.db's tech_debt table.",
    )
    parser.add_argument(
        "--candidates-file",
        default=None,
        help="Path to a JSON array of pre-generated candidates (discovery mode only). "
             "When set, the calling agent has already done the reasoning in-session "
             "(reading docs, synthesizing ideas) — this script only dedups/scores/inserts. "
             "Each item: {project, text, rationale?, implementation_hints?, "
             "context_snapshot?, estimated_effort?, dependencies?}.",
    )
    return parser


def _resolve_workspace_utils_path() -> Path:
    """Locate ⊕Workspace's src/utils, checking known layouts (main checkout,
    then any local git worktree of that repo) rather than assuming main exists.

    Raises FileNotFoundError with an actionable message if neither is found —
    this is a hard cross-repo dependency (tech_debt table lives in workspace.db),
    so `--mode tech-debt` genuinely cannot run without it merged/present somewhere.
    """
    main_path = WORKSPACE_ROOT / "⊕Workspace" / "src" / "utils"
    if (main_path / "tech_debt_scanner.py").exists():
        return main_path

    worktrees_root = WORKSPACE_ROOT / "⊕Workspace" / ".worktrees"
    if worktrees_root.exists():
        for candidate in sorted(worktrees_root.iterdir()):
            candidate_utils = candidate / "src" / "utils"
            if (candidate_utils / "tech_debt_scanner.py").exists():
                return candidate_utils

    raise FileNotFoundError(
        "Could not find src/utils/tech_debt_scanner.py on ⊕Workspace main or in any "
        "local worktree. --mode tech-debt requires FR-20260807-tech-debt-scanner's "
        "⊕Workspace-side changes to be merged (or checked out in a worktree) first."
    )


def _run_tech_debt_scan(projects: list[str]) -> int:
    """Scan projects for tech debt, narrate deterministically, auto-write severity>=7."""
    # ⊕Workspace's utils live under its own "src.utils" package, which collides
    # with this project's "src" namespace — import them as bare modules instead.
    workspace_utils = _resolve_workspace_utils_path()
    if str(workspace_utils) not in sys.path:
        sys.path.insert(0, str(workspace_utils))
    import tech_debt_scanner  # noqa: E402
    import init_db as workspace_init_db  # noqa: E402

    # If workspace_utils resolved inside a worktree (no ⊕Workspace main copy of
    # tech_debt_scanner.py yet), avoid auto-creating a separate/isolated
    # workspace.db there — walk up to the real one, same convention other
    # tools/*.py scripts in this workspace already use.
    workspace_init_db.use_worktree_aware_db_path(workspace_utils.parent.parent)
    workspace_init_db.init_db()

    all_findings = []
    for project in projects:
        root = TECH_DEBT_PROJECT_ROOTS[project]
        if not root.exists():
            continue
        all_findings.extend(tech_debt_scanner.scan_project(project, root))

    if not all_findings:
        print("No tech-debt findings.")
        return 0

    all_findings.sort(key=lambda f: f.severity, reverse=True)

    template = _TECH_DEBT_ACTION_TEMPLATES
    for f in all_findings:
        f.action = template.get(f.category, "Address {file} — {detail}.").format(
            file=_excerpt(f.file_path, max_len=60), detail=f.detail
        )

    print("\nTech-debt findings (ranked by severity)")
    print("SEV  PROJECT      CATEGORY     FILE")
    print("-" * 100)
    for f in all_findings:
        print(f"{f.severity:<4} {f.project:<12} {f.category:<12} {_excerpt(f.file_path, max_len=60)}")
        if f.action:
            print(f"     action: {_excerpt(f.action, max_len=90)}")

    auto_write = [f for f in all_findings if f.severity >= TECH_DEBT_SEVERITY_THRESHOLD]
    if not auto_write:
        print(f"\nNo findings >= severity {TECH_DEBT_SEVERITY_THRESHOLD}; nothing written.")
        return 0

    conn = workspace_init_db.get_connection()
    written = 0
    for f in auto_write:
        try:
            conn.execute(
                "INSERT INTO tech_debt (finding_id, project, category, file_path, severity, detail, action) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f.finding_id, f.project, f.category, f.file_path, f.severity, f.detail, f.action),
            )
            written += 1
        except Exception:
            continue
    conn.commit()
    conn.close()

    print(f"\nAuto-wrote {written} finding(s) with severity >= {TECH_DEBT_SEVERITY_THRESHOLD} to workspace.db tech_debt table.")
    return 0


def _read_path_excerpt(path: Path, max_chars: int = 2400) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _collect_context(project: str) -> str:
    root = PROJECT_ROOTS[project]
    snippets: list[str] = []

    for pattern in DISCOVERY_FILES.get(project, []):
        for path in sorted(root.glob(pattern))[:12]:
            if not path.is_file():
                continue
            excerpt = _read_path_excerpt(path)
            if not excerpt:
                continue
            rel = path.relative_to(root).as_posix()
            snippets.append(f"[{project}:{rel}] {excerpt}")

    return "\n".join(snippets)


def _heuristic_candidates(project: str, context: str, limit: int) -> list[dict[str, str]]:
    text = context.lower()
    suggestions: list[str] = []

    keyword_rules: list[tuple[str, str]] = [
        (r"\bradio\b|\bicecast\b|\baudius\b", "Launch public radio distribution with production-grade fallback routing"),
        (r"\bmcp\b|model context protocol", "Prioritize next MCP integration and publish a phased rollout plan"),
        (r"\bbenchmark\b|\bqpu\b|\bshor", "Publish benchmark observability dashboard with schedule + drift alerts"),
        (r"\bexecutive\b|\bbrief\b", "Add executive brief delivery controls and reliability telemetry"),
        (r"\bsecurity\b|\bsecret\b|\btoken\b", "Introduce automated secret scanning gate in every public-repo PR"),
    ]

    for pattern, todo in keyword_rules:
        if re.search(pattern, text):
            suggestions.append(todo)

    defaults: dict[str, list[str]] = {
        "workspace": [
            "Create prioritized cross-project roadmap from active TRIAGED FRs",
            "Ship weekly discovery sweep that proposes top 10 high-impact stories",
        ],
        "music": [
            "Ship public launch plan for TJD radio with audience-growth instrumentation",
        ],
        "life": [
            "Create intervention opportunity pipeline from new biomarker ingests",
        ],
        "quantum": [
            "Establish monthly execution-policy review with benchmark variance thresholds",
        ],
        "ai_manifest": [
            "Implement opportunity-to-brief pipeline linking discovered stories to executive summaries",
        ],
    }

    suggestions.extend(defaults.get(project, []))
    unique: list[str] = []
    seen: set[str] = set()
    for item in suggestions:
        key = _normalize(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break

    return [{"project": project, "text": t, "rationale": "heuristic fallback",
             "implementation_hints": "", "context_snapshot": "",
             "estimated_effort": "", "dependencies": ""} for t in unique]


def _discover_for_project(project: str, limit: int) -> list[dict[str, str]]:
    """Deterministic-only candidate generation (no LLM). For richer, context-aware
    candidates, the calling agent should reason in-session and pass results via
    `--candidates-file` instead of relying on this heuristic fallback.
    """
    context = _collect_context(project)
    if not context:
        return []
    return _heuristic_candidates(project, context=context, limit=limit)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _similarity(a: str, b: str) -> float:
    a_n = _normalize(a)
    b_n = _normalize(b)
    seq = difflib.SequenceMatcher(a=a_n, b=b_n).ratio()
    toks_a = set(a_n.split())
    toks_b = set(b_n.split())
    jaccard = (len(toks_a & toks_b) / len(toks_a | toks_b)) if (toks_a or toks_b) else 0.0
    return max(seq, jaccard)


def _nearest_open_match(text: str, open_texts: list[str], threshold: float = 0.62) -> str | None:
    best_text = None
    best_score = 0.0
    for existing in open_texts:
        score = _similarity(text, existing)
        if score > best_score:
            best_score = score
            best_text = existing
    if best_text and best_score >= threshold:
        return best_text
    return None


def _load_candidates_file(path: str) -> dict[str, list[dict[str, str]]]:
    """Load agent-supplied candidates JSON, grouped by project key."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    by_project: dict[str, list[dict[str, str]]] = {}
    for item in data:
        project = str(item.get("project", "")).strip()
        text = str(item.get("text", "")).strip()
        if not project or not text:
            continue
        by_project.setdefault(project, []).append({
            "project": project,
            "text": text,
            "priority": item.get("priority"),  # agent-supplied 1-10, or None to fall back to heuristic
            "rationale": str(item.get("rationale", "")).strip(),
            "implementation_hints": str(item.get("implementation_hints", "")).strip(),
            "context_snapshot": str(item.get("context_snapshot", "")).strip(),
            "estimated_effort": str(item.get("estimated_effort", "")).strip(),
            "dependencies": str(item.get("dependencies", "")).strip(),
        })
    return by_project


def _prepare_candidates(projects: list[str], limit: int, candidates_file: str | None = None) -> list[Candidate]:
    open_rows = get_open_todos()
    open_by_project: dict[str, list[dict[str, Any]]] = {}
    for row in open_rows:
        key = str(row.get("project", ""))
        open_by_project.setdefault(key, []).append(row)

    supplied = _load_candidates_file(candidates_file) if candidates_file else {}

    results: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    for project in projects:
        discovered = supplied.get(project) or _discover_for_project(project, limit=limit)
        existing_rows = open_by_project.get(project, [])
        existing_texts = [str(r.get("text", "")) for r in existing_rows]

        for row in discovered:
            text = row["text"].strip()
            if not text:
                continue
            key = (project, _normalize(text))
            if key in seen:
                continue
            seen.add(key)

            similar_to = _nearest_open_match(text, existing_texts)
            supplied_priority = row.get("priority")
            if supplied_priority not in (None, ""):
                try:
                    # Agent already scored this in-session — skip score_priority()'s
                    # heuristic call entirely.
                    priority = max(1, min(10, int(supplied_priority)))
                except (TypeError, ValueError):
                    priority = score_priority(text=text, project=project, existing_todos=existing_rows)
            else:
                priority = score_priority(text=text, project=project, existing_todos=existing_rows)
            source = _classify_autonomy(text)
            autonomy_level = _classify_autonomy_level(text, source)
            results.append(
                Candidate(
                    project=project,
                    text=text,
                    priority=priority,
                    similar_to=similar_to,
                    source=source,
                    autonomy_level=autonomy_level,
                    rationale=row.get("rationale", ""),
                    implementation_hints=row.get("implementation_hints", ""),
                    context_snapshot=row.get("context_snapshot", ""),
                    estimated_effort=row.get("estimated_effort", ""),
                    dependencies=row.get("dependencies", ""),
                )
            )
            if len(results) >= limit:
                return results
    return results


def _excerpt(text: str, max_len: int = 70) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


def _print_candidates(candidates: list[Candidate]) -> None:
    print("\nDiscovered epic/story todo opportunities")
    print("ID   PROJECT      PRI  SOURCE  STATUS      TODO                                                            RATIONALE")
    print("-" * 140)
    for idx, row in enumerate(candidates, start=1):
        status = "SIMILAR" if row.similar_to else "NEW"
        rationale_col = _excerpt(row.rationale, max_len=80) if row.rationale else ""
        print(
            f"{idx:<4} {row.project:<12} {row.priority:<4} {row.source:<7} {status:<10} "
            f"{_excerpt(row.text):<63} {rationale_col}"
        )
        if row.similar_to:
            print(f"     similar to: {_excerpt(row.similar_to, max_len=80)}")


def _parse_selection(raw: str, max_id: int) -> set[int]:
    clean = raw.strip().lower()
    if clean == "all":
        return set(range(1, max_id + 1))
    selected: set[int] = set()
    for token in clean.split():
        if token.isdigit():
            value = int(token)
            if 1 <= value <= max_id:
                selected.add(value)
    return selected


def _insert_selected(candidates: list[Candidate], selected_ids: set[int]) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    for idx, row in enumerate(candidates, start=1):
        if idx not in selected_ids:
            continue
        try:
            add_todo(
                project=row.project,
                text=row.text,
                priority=row.priority,
                source=row.source,  # 'AI' or 'TYLER' — auto-classified by _classify_autonomy
                autonomy_level=row.autonomy_level,
                rationale=row.rationale or None,
                implementation_hints=row.implementation_hints or None,
                context_snapshot=row.context_snapshot or None,
                estimated_effort=row.estimated_effort or None,
                dependencies=row.dependencies or None,
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    return inserted, skipped


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.mode == "tech-debt":
        projects = [args.project] if args.project else list(TECH_DEBT_PROJECT_ROOTS.keys())
        return _run_tech_debt_scan(projects=projects)

    init_db()

    if args.project and args.project not in PROJECT_ROOTS:
        print(f"'{args.project}' is only valid with --mode tech-debt (not in epic/story discovery scope).")
        return 1

    projects = [args.project] if args.project else list(PROJECT_ROOTS.keys())
    candidates = _prepare_candidates(projects=projects, limit=max(1, args.limit), candidates_file=args.candidates_file)

    if not candidates:
        print("No discovery candidates found.")
        return 0

    _print_candidates(candidates)

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to insert approved items into manifest_todos.db")
        return 0

    if args.yes:
        selected_ids = set(range(1, len(candidates) + 1))
    else:
        confirm = input("\nWrite selected discoveries to DB? [y/N]: ").strip().lower()
        if confirm not in {"y", "yes"}:
            print("Aborted by user.")
            return 0
        picks = input("Enter IDs to insert (e.g. 'all' or '1 3 5'): ")
        selected_ids = _parse_selection(picks, max_id=len(candidates))

    if not selected_ids:
        print("No IDs selected. Nothing inserted.")
        return 0

    inserted, skipped = _insert_selected(candidates, selected_ids)
    print(f"Inserted todos (AI/TYLER auto-classified): {inserted}; skipped duplicates: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
