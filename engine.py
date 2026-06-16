"""
DocSentinel engine.py
Phase 1: Parse code chunks + doc sections + build code-doc link graph.
"""

import os
import ast
import json
import re
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
load_dotenv()

from config import (
    GEMINI_API_KEY,
    EMBEDDING_MODEL,
    CHROMA_PATH,
    COLLECTION_NAME,
    SIMILARITY_THRESHOLD,
    CODE_EXTENSIONS,
    DOC_EXTENSIONS,
    MAP_OUTPUT,
)

import chromadb
from google import genai

client = genai.Client(api_key=GEMINI_API_KEY)


# ── Embedding ──────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text
    )
    return result.embeddings[0].values


# ── ChromaDB ───────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_chroma_collection():
    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    return chroma.get_or_create_collection(COLLECTION_NAME)


# ── Code Parser ────────────────────────────────────────────────────────────────

def parse_code_chunks(repo_path: str) -> list[dict]:
    """
    Walk repo, extract functions/classes with signatures + docstrings.
    Returns list of chunks: {id, file, name, type, signature, docstring, full_text}
    """
    chunks = []
    for ext in CODE_EXTENSIONS:
        for fpath in Path(repo_path).rglob(f"*{ext}"):
            rel = str(fpath.relative_to(repo_path))
            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name = node.name
                    docstring = ast.get_docstring(node) or ""
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [a.arg for a in node.args.args]
                        signature = f"def {name}({', '.join(args)})"
                        kind = "function"
                    else:
                        signature = f"class {name}"
                        kind = "class"

                    full_text = f"{signature}\n{docstring}"
                    chunk_id = f"{rel}::{name}"

                    chunks.append({
                        "id": chunk_id,
                        "file": rel,
                        "name": name,
                        "type": kind,
                        "signature": signature,
                        "docstring": docstring,
                        "full_text": full_text,
                    })
    return chunks


# ── Doc Parser ─────────────────────────────────────────────────────────────────

def parse_doc_sections(repo_path: str) -> list[dict]:
    """
    Walk repo, split markdown docs by ## headings.
    Returns list of sections: {id, file, heading, content, full_text}
    """
    sections = []
    for ext in DOC_EXTENSIONS:
        for fpath in Path(repo_path).rglob(f"*{ext}"):
            rel = str(fpath.relative_to(repo_path))
            text = fpath.read_text(encoding="utf-8")

            parts = re.split(r"(?=^## )", text, flags=re.MULTILINE)
            for part in parts:
                if not part.strip():
                    continue
                lines = part.strip().splitlines()
                heading = lines[0].lstrip("#").strip() if lines else "top"
                content = "\n".join(lines[1:]).strip()
                section_id = f"{rel}::{heading}"

                sections.append({
                    "id": section_id,
                    "file": rel,
                    "heading": heading,
                    "content": content,
                    "full_text": part.strip(),
                })
    return sections


# ── Link Graph Builder ─────────────────────────────────────────────────────────

def build_link_graph(code_chunks: list[dict], doc_sections: list[dict]) -> list[dict]:
    """
    Link code chunks to doc sections via:
    1. Name heuristic: doc section mentions function/class name
    2. Embedding similarity: cosine sim > SIMILARITY_THRESHOLD
    """
    col = get_chroma_collection()
    links = []
    name_set = {c["name"]: c["id"] for c in code_chunks}

    print(f"Indexing {len(code_chunks)} code chunks...")
    for chunk in code_chunks:
        emb = embed(chunk["full_text"])
        col.upsert(
            ids=[f"code::{chunk['id']}"],
            embeddings=[emb],
            documents=[chunk["full_text"]],
            metadatas=[{"kind": "code", "name": chunk["name"], "file": chunk["file"]}],
        )

    print(f"Indexing {len(doc_sections)} doc sections...")
    for sec in doc_sections:
        emb = embed(sec["full_text"])
        col.upsert(
            ids=[f"doc::{sec['id']}"],
            embeddings=[emb],
            documents=[sec["full_text"]],
            metadatas=[{"kind": "doc", "heading": sec["heading"], "file": sec["file"]}],
        )

    # Name heuristic links
    for sec in doc_sections:
        for name, code_id in name_set.items():
            if re.search(rf"\b{re.escape(name)}\b", sec["full_text"]):
                links.append({
                    "code_id": code_id,
                    "doc_id": sec["id"],
                    "method": "name_match",
                    "score": 1.0,
                })

    # Embedding similarity links
    for chunk in code_chunks:
        emb = embed(chunk["full_text"])
        results = col.query(
            query_embeddings=[emb],
            n_results=5,
            where={"kind": "doc"},
        )
        for doc_id_raw, dist in zip(results["ids"][0], results["distances"][0]):
            score = 1 - (dist / 2)
            if score >= SIMILARITY_THRESHOLD:
                doc_id = doc_id_raw.replace("doc::", "")
                already = any(
                    l["code_id"] == chunk["id"] and l["doc_id"] == doc_id
                    for l in links
                )
                if not already:
                    links.append({
                        "code_id": chunk["id"],
                        "doc_id": doc_id,
                        "method": "embedding",
                        "score": round(score, 4),
                    })

    return links


# ── Main: Index Repo ───────────────────────────────────────────────────────────

def index_repo(repo_path: str) -> dict:
    print(f"\n🔍 DocSentinel indexing: {repo_path}")

    code_chunks = parse_code_chunks(repo_path)
    doc_sections = parse_doc_sections(repo_path)
    links = build_link_graph(code_chunks, doc_sections)

    graph = {
        "repo_path": repo_path,
        "code_chunks": code_chunks,
        "doc_sections": doc_sections,
        "links": links,
    }

    with open(MAP_OUTPUT, "w") as f:
        json.dump(graph, f, indent=2)

    print(f"\n✅ Indexed {len(code_chunks)} code chunks, {len(doc_sections)} doc sections, {len(links)} links")
    print(f"   Saved → {MAP_OUTPUT}")
    return graph


if __name__ == "__main__":
    import sys
    repo = sys.argv[1] if len(sys.argv) > 1 else "./demo_repo"
    index_repo(repo)


# ── Phase 2: Change Detector ───────────────────────────────────────────────────

def get_git_diff(repo_path: str, base_branch: str = "main") -> list[dict]:
    """
    Get changed files + diffs vs base branch.
    Returns list of: {file, old_content, new_content, diff}
    """
    import subprocess

    changes = []
    try:
        # Try origin/base_branch first (CI), fall back to local base_branch
        fetch = subprocess.run(
            ["git", "fetch", "origin", base_branch],
            cwd=repo_path, capture_output=True, text=True
        )
        base_ref = f"origin/{base_branch}"
        test = subprocess.run(
            ["git", "diff", f"{base_ref}...HEAD", "--name-only"],
            cwd=repo_path, capture_output=True, text=True
        )
        if not test.stdout.strip():
            base_ref = base_branch  # fall back to local

        # Get list of changed files
        result = subprocess.run(
            ["git", "diff", f"{base_ref}...HEAD", "--name-only"],
            cwd=repo_path, capture_output=True, text=True
        )
        changed_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        print(f"   Base ref: {base_ref}, changed files: {changed_files}")

        for fpath in changed_files:
            # Skip non-code, non-doc files
            if not any(fpath.endswith(ext) for ext in CODE_EXTENSIONS + DOC_EXTENSIONS):
                continue

            # Get old content
            old = subprocess.run(
                ["git", "show", f"{base_ref}:{fpath}"],
                cwd=repo_path, capture_output=True, text=True
            )
            # Get new content
            new_path = Path(repo_path) / fpath
            new_content = new_path.read_text(encoding="utf-8") if new_path.exists() else ""

            # Get diff
            diff = subprocess.run(
                ["git", "diff", f"{base_ref}...HEAD", "--", fpath],
                cwd=repo_path, capture_output=True, text=True
            )

            changes.append({
                "file": fpath,
                "old_content": old.stdout,
                "new_content": new_content,
                "diff": diff.stdout,
            })
    except Exception as e:
        print(f"Git diff error: {e}")

    return changes


def is_meaningful_change(diff: str) -> bool:
    """
    Skip comment-only, whitespace-only, test file changes.
    """
    meaningful_lines = [
        l for l in diff.splitlines()
        if l.startswith(("+", "-"))
        and not l.startswith(("+++", "---"))
        and not l.strip().lstrip("+-").startswith("#")
        and l.strip() not in ("+", "-", "")
    ]
    return len(meaningful_lines) > 0


def find_stale_sections(changes: list[dict], graph: dict) -> list[dict]:
    """
    For each meaningful code change, find linked doc sections from map.
    Returns list of suspects: {code_file, doc_id, doc_section, old_code, new_code, diff}
    """
    suspects = []
    links = graph["links"]
    doc_map = {s["id"]: s for s in graph["doc_sections"]}

    for change in changes:
        if not is_meaningful_change(change["diff"]):
            continue
        if not any(change["file"].endswith(ext) for ext in CODE_EXTENSIONS):
            continue

        # Find all doc sections linked to this file's code chunks
        linked_docs = [
            l for l in links
            if change["file"].replace("\\", "/") in l["code_id"].replace("\\", "/")
        ]

        for link in linked_docs:
            doc_id = link["doc_id"]
            if doc_id not in doc_map:
                continue
            suspects.append({
                "code_file": change["file"],
                "doc_id": doc_id,
                "doc_section": doc_map[doc_id],
                "old_code": change["old_content"],
                "new_code": change["new_content"],
                "diff": change["diff"],
                "link_method": link["method"],
            })

    return suspects


def verify_staleness(suspects: list[dict]) -> list[dict]:
    """
    LLM verifies each suspect: is the doc section stale given the code change?
    Adds: is_stale (bool), reason (str), confidence (float)
    """
    from google import genai as _genai
    llm = _genai.Client(api_key=GEMINI_API_KEY)

    verified = []
    for s in suspects:
        prompt = f"""You are a documentation auditor.

CODE CHANGE (diff):
{s['diff'][:2000]}

DOCUMENTATION SECTION (heading: {s['doc_section']['heading']}):
{s['doc_section']['full_text'][:1500]}

Is this documentation section now inaccurate or stale due to the code change?
Reply in JSON only:
{{
  "is_stale": true or false,
  "reason": "one sentence explanation",
  "confidence": 0.0 to 1.0
}}"""

        try:
            response = llm.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            raw = response.text.strip().strip("```json").strip("```").strip()
            result = json.loads(raw)
            s["is_stale"] = result.get("is_stale", False)
            s["reason"] = result.get("reason", "")
            s["confidence"] = result.get("confidence", 0.0)
        except Exception as e:
            s["is_stale"] = False
            s["reason"] = f"Verification error: {e}"
            s["confidence"] = 0.0

        if s["is_stale"]:
            verified.append(s)

    return verified


def detect_changes(repo_path: str, map_path: str = MAP_OUTPUT, base_branch: str = "main") -> list[dict]:
    """
    Full Phase 2 pipeline:
    git diff → filter meaningful → find linked docs → LLM verify staleness.
    """
    print(f"\n🔎 Detecting changes in: {repo_path} vs {base_branch}")

    with open(map_path) as f:
        graph = json.load(f)

    changes = get_git_diff(repo_path, base_branch)
    print(f"   {len(changes)} changed files found")

    suspects = find_stale_sections(changes, graph)
    print(f"   {len(suspects)} suspect doc sections")

    stale = verify_staleness(suspects)
    print(f"   {len(stale)} confirmed stale sections")

    return stale


# ── Phase 3: Doc Repair Engine ─────────────────────────────────────────────────

def repair_doc_section(stale: dict) -> dict:
    """
    LLM rewrites only the stale parts of a doc section.
    Adds: repaired_text, repair_confidence, mode (auto_fix | human_review)
    """
    from google import genai as _genai
    from config import CONFIDENCE_HIGH, CONFIDENCE_LOW
    llm = _genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""You are a technical documentation editor.

ORIGINAL DOCUMENTATION SECTION:
{stale['doc_section']['full_text']}

CODE CHANGE (diff):
{stale['diff'][:2000]}

STALENESS REASON:
{stale['reason']}

Rewrite ONLY the parts of the documentation that are now inaccurate.
Preserve the original style, tone, structure, and all accurate parts.
Do NOT add new sections or change formatting.

Reply in JSON only:
{{
  "repaired_text": "full rewritten doc section",
  "confidence": 0.0 to 1.0,
  "changes_made": "one sentence summary of what you changed"
}}"""

    try:
        response = llm.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        raw = response.text.strip().strip("```json").strip("```").strip()
        result = json.loads(raw)

        confidence = result.get("confidence", 0.0)
        if confidence >= CONFIDENCE_HIGH:
            mode = "auto_fix"
        elif confidence >= CONFIDENCE_LOW:
            mode = "human_review"
        else:
            mode = "skip"

        stale["repaired_text"] = result.get("repaired_text", "")
        stale["repair_confidence"] = confidence
        stale["changes_made"] = result.get("changes_made", "")
        stale["mode"] = mode

    except Exception as e:
        stale["repaired_text"] = ""
        stale["repair_confidence"] = 0.0
        stale["changes_made"] = f"Repair error: {e}"
        stale["mode"] = "skip"

    return stale


def validate_repair(stale: dict) -> dict:
    """
    Second LLM pass: verify repaired doc accurately reflects new code.
    Adds: validation_passed (bool), validation_note (str)
    """
    from google import genai as _genai
    llm = _genai.Client(api_key=GEMINI_API_KEY)

    if not stale.get("repaired_text"):
        stale["validation_passed"] = False
        stale["validation_note"] = "No repaired text to validate."
        return stale

    prompt = f"""You are a documentation quality reviewer.

NEW CODE:
{stale['new_code'][:2000]}

REPAIRED DOCUMENTATION:
{stale['repaired_text']}

Does this documentation accurately describe the new code?
Reply in JSON only:
{{
  "validation_passed": true or false,
  "validation_note": "one sentence explanation"
}}"""

    try:
        from google import genai as _genai
        llm = _genai.Client(api_key=GEMINI_API_KEY)
        response = llm.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        raw = response.text.strip().strip("```json").strip("```").strip()
        result = json.loads(raw)
        stale["validation_passed"] = result.get("validation_passed", False)
        stale["validation_note"] = result.get("validation_note", "")
    except Exception as e:
        stale["validation_passed"] = False
        stale["validation_note"] = f"Validation error: {e}"

    return stale


def apply_repairs(stale_sections: list[dict], repo_path: str) -> list[dict]:
    """
    Full Phase 3 pipeline:
    For each stale section → repair → validate → write fix to disk.
    Returns repaired sections with mode + status.
    """
    print(f"\n🔧 Repairing {len(stale_sections)} stale sections...")
    results = []

    for s in stale_sections:
        print(f"   Repairing: {s['doc_section']['heading']}...")
        s = repair_doc_section(s)
        s = validate_repair(s)

        if s["mode"] == "auto_fix" and s["validation_passed"]:
            # Write repaired content back to doc file
            doc_file = Path(repo_path) / s["doc_section"]["file"]
            if doc_file.exists():
                original = doc_file.read_text(encoding="utf-8")
                updated = original.replace(
                    s["doc_section"]["full_text"],
                    s["repaired_text"]
                )
                doc_file.write_text(updated, encoding="utf-8")
                s["applied"] = True
                print(f"   ✅ Auto-fixed: {s['doc_section']['heading']}")
            else:
                s["applied"] = False
        else:
            s["applied"] = False
            print(f"   🟡 Flagged for review: {s['doc_section']['heading']} (mode={s['mode']})")

        results.append(s)

    return results
