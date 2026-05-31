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
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.ollama import OllamaClient
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

DISCOVERY_FILES: dict[str, list[str]] = {
    "music": ["AGENT_STARTUP.md", "README.md", "Brand/**/*.html", "docs/**/*.md"],
    "life": ["AGENT_STARTUP.md", "README.md", "docs/**/*.md", "research/**/*.md"],
    "quantum": ["AGENT_STARTUP.md", "README.md", "docs/**/*.md", "research/**/*.md"],
    "ai_manifest": ["AGENT_STARTUP.md", "README.md", "docs/**/*.md", "research/**/*.md"],
    "workspace": ["AGENT_STARTUP.md", "README.md", ".github/FEATURE_REQUESTS.md", "REPO_VISIBILITY.md"],
}

_PREFERRED_MODEL = "llama3.3:70b"
_OLLAMA_MODELS_PATH = r"F:\.ollama\models"


def _select_model(override: str | None = None) -> str:
    """Return the best available Ollama model name.

    If *override* is given, return it immediately without querying Ollama.
    Otherwise, detect the best local model:
    1. llama3.3:70b (preferred)
    2. Any 70b model
    3. Any 13b model
    4. llama3.1:8b
    5. First available model
    6. Absolute default: llama3.1:8b
    """
    if override is not None:
        return override

    model_names: list[str] = []
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        lines = result.stdout.strip().splitlines()
        for line in lines[1:]:  # skip header
            parts = line.split()
            if parts:
                model_names.append(parts[0])
    except Exception:
        pass

    if _PREFERRED_MODEL in model_names:
        print(f"[discover] Using model: {_PREFERRED_MODEL}")
        return _PREFERRED_MODEL

    # Preferred not found — warn, set env, attempt pull
    print(
        f"[discover] {_PREFERRED_MODEL} not found. "
        f"Set OLLAMA_MODELS={_OLLAMA_MODELS_PATH} and run: ollama pull {_PREFERRED_MODEL}"
    )
    os.environ["OLLAMA_MODELS"] = _OLLAMA_MODELS_PATH
    try:
        subprocess.run(
            ["ollama", "pull", _PREFERRED_MODEL],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
    except Exception:
        pass

    # Fall back through preference order
    for name in model_names:
        if "70b" in name:
            print(f"[discover] Using model: {name}")
            return name
    for name in model_names:
        if "13b" in name:
            print(f"[discover] Using model: {name}")
            return name
    for name in model_names:
        if name == "llama3.1:8b":
            print(f"[discover] Using model: {name}")
            return name
    if model_names:
        print(f"[discover] Using model: {model_names[0]}")
        return model_names[0]

    # Absolute fallback
    print("[discover] Using model: llama3.1:8b (default fallback)")
    return "llama3.1:8b"


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
        choices=sorted(PROJECT_ROOTS.keys()),
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
        "--model",
        default=None,
        help="Ollama model to use (default: auto-detect best available).",
    )
    return parser


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


def _discovery_prompt(project: str, context: str, target_count: int) -> str:
    return (
        "You are a product strategist. Read project context and propose backlog opportunities. "
        "Only suggest epic/story-level outcomes (new capability, launch, integration, system-level improvement), "
        "not code-style micro tasks.\n\n"
        f"Project key: {project}\n"
        f"Target suggestions: {target_count}\n"
        "Return STRICT JSON (no markdown) as an array of objects with keys:"
        " project, text, rationale, implementation_hints, context_snapshot, estimated_effort, dependencies.\n"
        "Rules:\n"
        "- project must equal the project key above\n"
        "- text must be <= 140 chars and action-oriented\n"
        "- rationale: why this todo matters now (<= 400 chars)\n"
        "- implementation_hints: suggested first steps / relevant files / APIs (<= 300 chars)\n"
        "- context_snapshot: key project facts that led to this suggestion (<= 400 chars)\n"
        "- estimated_effort: one of XS, S, M, L, XL\n"
        "- dependencies: comma-separated todo IDs or FR IDs (empty string if none)\n"
        "- avoid duplicates / near-duplicates\n"
        "- keep suggestions realistic based on context\n\n"
        "Context:\n"
        f"{context}\n"
    )


def _extract_json_candidates(raw: str, project: str) -> list[dict[str, str]]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            rows: list[dict[str, str]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                rows.append(
                    {
                        "project": project,
                        "text": text,
                        "rationale": str(item.get("rationale", "")).strip(),
                        "implementation_hints": str(item.get("implementation_hints", "")).strip(),
                        "context_snapshot": str(item.get("context_snapshot", "")).strip(),
                        "estimated_effort": str(item.get("estimated_effort", "")).strip(),
                        "dependencies": str(item.get("dependencies", "")).strip(),
                    }
                )
            return rows
    except Exception:
        pass

    rows = []
    for line in raw.splitlines():
        s = line.strip(" -\t")
        if not s:
            continue
        s = re.sub(r"^\d+[.)]\s*", "", s).strip()
        if len(s) < 8:
            continue
        rows.append({"project": project, "text": s, "rationale": "",
                     "implementation_hints": "", "context_snapshot": "",
                     "estimated_effort": "", "dependencies": ""})
    return rows


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


def _discover_for_project(project: str, limit: int, model: str = "llama3.1:8b") -> list[dict[str, str]]:
    context = _collect_context(project)
    if not context:
        return []

    prompt = _discovery_prompt(project, context, target_count=max(3, min(8, limit)))

    try:
        raw = OllamaClient(model=model).generate(prompt)
        rows = _extract_json_candidates(raw, project)
        if rows:
            return rows
    except Exception:
        pass

    try:
        import openai  # type: ignore[import]

        api_key = os.environ.get("OPENAPI_TOKEN")
        if not api_key:
            return []

        client = openai.OpenAI(api_key=api_key, timeout=25)
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=700,
        )
        raw = response.choices[0].message.content or ""
        return _extract_json_candidates(raw, project)
    except Exception:
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


def _prepare_candidates(projects: list[str], limit: int, model: str = "llama3.1:8b") -> list[Candidate]:
    open_rows = get_open_todos()
    open_by_project: dict[str, list[dict[str, Any]]] = {}
    for row in open_rows:
        key = str(row.get("project", ""))
        open_by_project.setdefault(key, []).append(row)

    results: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    for project in projects:
        discovered = _discover_for_project(project, limit=limit, model=model)
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

    init_db()

    model = _select_model(override=args.model)

    projects = [args.project] if args.project else list(PROJECT_ROOTS.keys())
    candidates = _prepare_candidates(projects=projects, limit=max(1, args.limit), model=model)

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
