"""
docsentinel_action.py
Runs in GitHub Actions CI:
  1. Index repo
  2. Detect stale docs from PR diff
  3. Repair stale sections
  4. Auto-fix (commit to PR branch) or flag (PR comment)
"""

import os
import json
from pathlib import Path
from github import Github
from engine import index_repo, detect_changes, apply_repairs
from config import MAP_OUTPUT

# ── Env ────────────────────────────────────────────────────────────────────────
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME    = os.environ["REPO_NAME"]
PR_NUMBER    = int(os.environ["PR_NUMBER"])
BASE_BRANCH  = os.environ.get("BASE_BRANCH", "main")
REPO_PATH    = "."

# ── Run pipeline ───────────────────────────────────────────────────────────────
print("=== DocSentinel Action ===")

print("\n[1/3] Indexing repo...")
index_repo(REPO_PATH)

print("\n[2/3] Detecting stale docs...")
stale = detect_changes(REPO_PATH, MAP_OUTPUT, BASE_BRANCH)

print("\n[3/3] Repairing stale sections...")
results = apply_repairs(stale, REPO_PATH) if stale else []

# ── Build PR comment ───────────────────────────────────────────────────────────
auto_fixed   = [r for r in results if r["mode"] == "auto_fix" and r.get("applied")]
needs_review = [r for r in results if r["mode"] == "human_review"]
skipped      = [r for r in results if r["mode"] == "skip"]

if not results:
    summary = "✅ **DocSentinel:** All documentation is up to date. No stale sections found."
else:
    lines = ["## 🛡️ DocSentinel — Doc Health Report", ""]
    lines.append(f"| Status | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| ✅ Auto-fixed | {len(auto_fixed)} |")
    lines.append(f"| 🟡 Needs human review | {len(needs_review)} |")
    lines.append(f"| ⏭️ Skipped (low confidence) | {len(skipped)} |")
    lines.append("")

    if auto_fixed:
        lines.append("### ✅ Auto-Fixed Sections")
        for r in auto_fixed:
            lines.append(f"- **{r['doc_section']['heading']}** — {r['changes_made']}")
        lines.append("")

    if needs_review:
        lines.append("### 🟡 Sections Flagged for Human Review")
        for r in needs_review:
            lines.append(f"- **{r['doc_section']['heading']}** (`{r['doc_section']['file']}`)")
            lines.append(f"  - Reason: {r['reason']}")
            lines.append(f"  - Confidence: {r['repair_confidence']:.0%}")
            lines.append(f"  - Suggested fix:")
            lines.append(f"  ```markdown")
            lines.append(f"  {r.get('repaired_text', '')[:500]}")
            lines.append(f"  ```")
        lines.append("")

    summary = "\n".join(lines)

# ── Post PR comment ────────────────────────────────────────────────────────────
gh   = Github(GITHUB_TOKEN)
repo = gh.get_repo(REPO_NAME)
pr   = repo.get_pull(PR_NUMBER)
pr.create_issue_comment(summary)
print(f"\n✅ Comment posted to PR #{PR_NUMBER}")

# ── Commit auto-fixes ──────────────────────────────────────────────────────────
if auto_fixed:
    import subprocess
    subprocess.run(["git", "config", "user.name", "DocSentinel Bot"])
    subprocess.run(["git", "config", "user.email", "docsentinel@bot.com"])
    subprocess.run(["git", "add", "*.md", "docs/"])
    subprocess.run(["git", "commit", "-m", "docs: auto-fix stale sections [DocSentinel]"])
    subprocess.run(["git", "push"])
    print(f"✅ Auto-fixes committed to PR branch")

print("\n=== Done ===")
