"""
update_readme.py
----------------
Fetches public repos tagged with "portfolio" topic, groups repos that share
a "group-<name>" topic into a single project entry, then updates the
PROJECTS_START / PROJECTS_END block in README.md automatically.

Grouping convention (set via GitHub Topics):
  - Add  portfolio          -> include in portfolio
  - Add  group-my-project   -> merge with other repos sharing the same group tag

Run by GitHub Actions -- see .github/workflows/update-readme.yml
"""

import os
import re
import requests
from datetime import datetime, timezone

# ──────────────────────────────────────────────
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "senmai121")
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")
README_PATH     = "README.md"
TOPIC_TAG       = "portfolio"
MAX_PROJECTS    = 9
# ──────────────────────────────────────────────

LANG_BADGE = {
    "Go":         "![Go](https://img.shields.io/badge/Go-00ADD8?style=flat-square&logo=go&logoColor=white)",
    "C#":         "![C#](https://img.shields.io/badge/C%23-239120?style=flat-square&logo=c-sharp&logoColor=white)",
    "TypeScript": "![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)",
    "JavaScript": "![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat-square&logo=javascript&logoColor=black)",
    "Python":     "![Python](https://img.shields.io/badge/Python-3572A5?style=flat-square&logo=python&logoColor=white)",
    "HTML":       "![HTML](https://img.shields.io/badge/HTML-e34c26?style=flat-square&logo=html5&logoColor=white)",
    "CSS":        "![CSS](https://img.shields.io/badge/CSS-563d7c?style=flat-square&logo=css3&logoColor=white)",
    "Java":       "![Java](https://img.shields.io/badge/Java-b07219?style=flat-square&logo=java&logoColor=white)",
    "Kotlin":     "![Kotlin](https://img.shields.io/badge/Kotlin-A97BFF?style=flat-square&logo=kotlin&logoColor=white)",
    "Rust":       "![Rust](https://img.shields.io/badge/Rust-dea584?style=flat-square&logo=rust&logoColor=black)",
    "Shell":      "![Shell](https://img.shields.io/badge/Shell-89e051?style=flat-square&logo=gnu-bash&logoColor=black)",
}


def fmt_name(slug):
    return slug.replace("-", " ").replace("_", " ").title()


def detect_role(repo):
    """Guess UI or API from name/topics."""
    name   = repo["name"].lower()
    topics = repo.get("topics") or []
    if "frontend" in topics or "ui" in topics or re.search(r"[-_](ui|web|front|client)$", name) or name.endswith("ui"):
        return "UI"
    if "backend" in topics or "api" in topics or re.search(r"[-_](api|backend|server|service|go)$", name):
        return "API"
    return fmt_name(repo["name"])


def get_group_key(repo):
    """Return group slug if repo has a 'group-*' topic, else None."""
    for t in (repo.get("topics") or []):
        if t.startswith("group-"):
            return t[6:]
    return None


def fetch_portfolio_repos():
    headers = {"Accept": "application/vnd.github.mercy-preview+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    url = (
        f"https://api.github.com/search/repositories"
        f"?q=user:{GITHUB_USERNAME}+topic:{TOPIC_TAG}&sort=updated&per_page=30"
    )
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("items", [])


def group_repos(repos):
    """Returns list of project dicts (grouped or single)."""
    groups  = {}
    singles = []

    for repo in repos:
        key = get_group_key(repo)
        if key:
            groups.setdefault(key, []).append(repo)
        else:
            singles.append(repo)

    projects = []

    for key, g_repos in groups.items():
        desc     = next((r["description"] for r in g_repos if r.get("description")), "")
        langs    = list(dict.fromkeys(r["language"] for r in g_repos if r.get("language")))
        stars    = sum(r["stargazers_count"] for r in g_repos)
        homepage = next((r["homepage"] for r in g_repos if r.get("homepage")), "")
        updated  = max(r["updated_at"] for r in g_repos)
        projects.append({
            "is_group": True, "key": key, "name": fmt_name(key),
            "desc": desc, "langs": langs, "stars": stars,
            "homepage": homepage, "updated": updated, "sub_repos": g_repos,
        })

    for repo in singles:
        lang = repo.get("language") or ""
        projects.append({
            "is_group": False, "name": fmt_name(repo["name"]),
            "desc": repo.get("description") or "",
            "langs": [lang] if lang else [],
            "stars": repo["stargazers_count"],
            "homepage": repo.get("homepage") or "",
            "updated": repo["updated_at"],
            "sub_repos": [repo],
        })

    # Sort: grouped first → stars desc → updated desc  (mirrors index.html logic)
    def sort_key(p):
        from datetime import datetime
        ts = datetime.fromisoformat(p["updated"].replace("Z", "+00:00")).timestamp()
        return (0 if p["is_group"] else 1, -p["stars"], -ts)

    projects.sort(key=sort_key)
    return projects[:MAX_PROJECTS]


def project_to_markdown(project):
    title    = project["name"]
    stars    = project["stars"]
    langs    = project["langs"]
    homepage = project["homepage"]

    if project["is_group"]:
        title_line = f"### 📦 {title}"
        if homepage:
            title_line += f" · [🌐 Live]({homepage})"

        # Each sub-repo gets its own line: role link + description
        sub_lines = []
        for r in project["sub_repos"]:
            role = detect_role(r)
            desc = r.get("description") or "_No description_"
            sub_lines.append(f"- **[{role}]({r['html_url']})** — {desc}")

        lines = [title_line, ""] + sub_lines + [""]
    else:
        repo = project["sub_repos"][0]
        title_line = f"### 📦 [{title}]({repo['html_url']})"
        if homepage:
            title_line += f" · [🌐 Live]({homepage})"
        desc = repo.get("description") or "_No description provided._"
        lines = [title_line, f"> {desc}", ""]

    meta = []
    for lang in langs:
        meta.append(LANG_BADGE.get(lang, f"`{lang}`"))
    if stars > 0:
        meta.append(f"⭐ {stars}")
    if meta:
        lines += ["  ".join(meta), ""]

    lines.append("---")
    return "\n".join(lines)


def build_projects_block(projects):
    if not projects:
        return f"_No featured projects. Add `{TOPIC_TAG}` topic to a repo to feature it here._"
    parts = [project_to_markdown(p) for p in projects]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts.append(f"\n<sub>🤖 Auto-updated: {ts}</sub>")
    return "\n\n".join(parts)


def update_readme(new_block):
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pattern     = r"(<!-- PROJECTS_START -->).*?(<!-- PROJECTS_END -->)"
    replacement = f"<!-- PROJECTS_START -->\n{new_block}\n<!-- PROJECTS_END -->"
    new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)

    if count == 0:
        raise ValueError("Markers PROJECTS_START / PROJECTS_END not found in README.md")
    if new_content == content:
        print("README already up to date.")
        return

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"README.md updated.")


if __name__ == "__main__":
    print(f"Fetching repos for @{GITHUB_USERNAME} with topic '{TOPIC_TAG}'...")
    repos    = fetch_portfolio_repos()
    print(f"Found {len(repos)} repo(s).")
    projects = group_repos(repos)
    print(f"Grouped into {len(projects)} project(s): {[p['name'] for p in projects]}")
    block = build_projects_block(projects)
    update_readme(block)
