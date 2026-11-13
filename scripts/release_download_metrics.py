"""Count GitHub release *uploaded asset* downloads (not source archives or clones).

Runs on GitHub Actions with GITHUB_TOKEN, GITHUB_REPOSITORY and
GITHUB_STEP_SUMMARY. Uses only the Python standard library.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def fetch_releases(repository: str, token: str) -> list[dict]:
    releases = []
    for page in range(1, 101):
        url = f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}"
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "RetroRelay-release-metrics",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                batch = json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"GitHub API failed with HTTP {error.code}") from error
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected GitHub API response")
        releases.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise RuntimeError("More than 10,000 releases; pagination limit reached")
    return releases


def make_report(releases: list[dict], repository: str) -> dict:
    entries = []
    for release in releases:
        assets = [
            {
                "name": asset["name"],
                "downloads": int(asset["download_count"]),
                "url": asset["browser_download_url"],
            }
            for asset in release.get("assets", [])
        ]
        entries.append({
            "tag": release.get("tag_name", ""),
            "url": release.get("html_url", ""),
            "prerelease": bool(release.get("prerelease", False)),
            "assets": assets,
            "asset_downloads": sum(a["downloads"] for a in assets),
        })
    return {
        "repository": repository,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "measurement": "GitHub release uploaded asset download_count",
        "limitations": "Excludes GitHub-generated source ZIP/tar.gz, git clones and unique-user counts.",
        "total_asset_downloads": sum(e["asset_downloads"] for e in entries),
        "releases": entries,
    }


def render_summary(report: dict) -> str:
    lines = [
        "## RetroRelay release asset download counts",
        "",
        f"Collected (UTC): {report['collected_at_utc']}",
        "",
        "| Release | Uploaded files | Asset downloads |",
        "| --- | ---: | ---: |",
    ]
    for entry in report["releases"]:
        tag = entry["tag"].replace("|", "\\|")
        lines.append(f"| [{tag}]({entry['url']}) | {len(entry['assets'])} | {entry['asset_downloads']} |")
    if not report["releases"]:
        lines.append("| No releases found | 0 | 0 |")
    lines.extend([
        "",
        f"**Total uploaded-asset downloads across releases: {report['total_asset_downloads']}**",
        "",
        "Only uploaded release assets have these counters. GitHub-generated source code "
        "ZIP/tar.gz downloads, git clones, and unique downloaders are not counted. "
        "Repeated downloads by one person may count multiple times.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    if repository != "Cardsmageanime/RetroRelay":
        raise RuntimeError("Unexpected repository")
    report = make_report(fetch_releases(repository, token), repository)
    Path("release-download-metrics.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    summary = render_summary(report)
    print(summary)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(summary)


if __name__ == "__main__":
    main()
