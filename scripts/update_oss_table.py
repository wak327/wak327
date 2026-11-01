#!/usr/bin/env python3
"""Regenerate the open-source contributions table in Readme.md.

Lists the merged pull requests I authored in repos I don't own, grouped by
project. Runs daily in CI (.github/workflows/update-oss-prs.yml) and locally;
needs the gh CLI authenticated (GH_TOKEN in CI).

Everything between the OSS-PRS markers in Readme.md is overwritten.
"""
import html
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

AUTHOR = os.environ.get("GITHUB_REPOSITORY_OWNER", "wak327")
# Owners whose repos are mine (or private), so their PRs are not "upstream".
EXCLUDED = [f"user:{AUTHOR}", "org:soft-track", "org:The-Educare-Online", "org:QuantaDev-io"]
README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Readme.md")
START, END = "<!-- OSS-PRS:START -->", "<!-- OSS-PRS:END -->"
RECENT = 3
TITLE_MAX = 72
# Short subtitles per project (repo descriptions are too noisy to show). A project
# without an entry here just shows its owner, so new projects need no edit.
BLURBS = {
    "docling-project/docling": "Document parsing for gen AI",
    "canonical/cloud-init": "Cloud instance initialization",
    "domjudge/domjudge": "Programming contest jury system",
    "canonical/subiquity": "Ubuntu Server installer",
    "canonical/microcloud": "Private cloud on LXD, Ceph and OVN",
    "itbench-hub/itbench": "Benchmarking for IT automation",
    "canonical/lxd-ui": "Browser interface for LXD",
    "ibm/unitxt": "AI evaluation library",
    "canonical/react-components": "Vanilla Framework components",
    "canonical/curtin": "Ubuntu storage and install backend",
    "canonical/microcloud-cluster-manager": "Entry point for MicroClouds",
}


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def merged_prs():
    query = f"is:pr is:merged author:{AUTHOR} " + " ".join(f"-{e}" for e in EXCLUDED)
    out = gh(
        "api", "-X", "GET", "search/issues",
        "-f", f"q={query}", "-f", "per_page=100", "--paginate",
        "--jq", '.items[] | {repo: (.repository_url | ltrimstr("https://api.github.com/repos/")), '
                "number, title, url: .html_url, merged_at: (.pull_request.merged_at // .closed_at)}",
    )
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def clip(text, limit):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def md(text):
    """Make text safe inside a table cell or link label."""
    return re.sub(r"([\[\]|])", r"\\\1", html.escape(text, quote=False))


def build_block():
    by_repo = defaultdict(list)
    for pr in merged_prs():
        by_repo[pr["repo"]].append(pr)

    projects = []
    for repo, prs in by_repo.items():
        info = json.loads(gh("api", f"repos/{repo}"))
        if info.get("private"):
            continue
        prs.sort(key=lambda p: p["merged_at"], reverse=True)
        projects.append((info["stargazers_count"], repo, prs))
    if not projects:
        sys.exit("No merged upstream PRs found; refusing to wipe the table.")
    projects.sort(key=lambda p: (-p[0], p[1].lower()))

    total = sum(len(p[2]) for p in projects)
    lines = [
        f"<sub>**{total} merged pull requests across {len(projects)} upstream projects** I don't own. "
        "Updated daily by a GitHub Action; each count links to the full list on GitHub.</sub>",
        "",
        "| Project | Stars | Merged | Latest merged PRs |",
        "|---|---|--:|---|",
    ]
    for _, repo, prs in projects:
        owner, name = repo.split("/")
        blurb = BLURBS.get(repo.lower())
        subtitle = f"{owner} · {blurb}" if blurb else owner
        recent = "<br>".join(
            f"• [{md(clip(p['title'], TITLE_MAX))}]({p['url']})" for p in prs[:RECENT]
        )
        if len(prs) > RECENT:
            recent += f"<br><sub>and {len(prs) - RECENT} more</sub>"
        pulls = f"https://github.com/{repo}/pulls?q=is%3Apr+is%3Amerged+author%3A{AUTHOR}"
        lines.append(
            f"| [**{name}**](https://github.com/{repo})<br><sub>{subtitle}</sub> "
            f"| ![stars](https://img.shields.io/github/stars/{repo}?style=flat-square) "
            f"| [{len(prs)}]({pulls}) | {recent} |"
        )
    return "\n".join(lines)


def main():
    with open(README, encoding="utf-8") as f:
        text = f.read()
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        sys.exit(f"Markers {START} / {END} not found in Readme.md")
    block = build_block()
    new = pattern.sub(lambda _: f"{START}\n{block}\n{END}", text)
    if new != text:
        with open(README, "w", encoding="utf-8") as f:
            f.write(new)
        print("Readme.md updated")
    else:
        print("Readme.md already up to date")


if __name__ == "__main__":
    main()
