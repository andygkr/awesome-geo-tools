#!/usr/bin/env python3
"""
awesome-geo-tools Traffic Tracker
=================================
Fetches GitHub traffic data via API and stores it persistently,
since GitHub only provides a 14-day rolling window.

Usage:
  # First run — set your GitHub token:
  export GITHUB_TOKEN="ghp_your_personal_access_token"

  # Run daily to collect data:
  python3 awesome_geo_traffic.py

  # Generate a report:
  python3 awesome_geo_traffic.py --report

  # Show last 7 days summary:
  python3 awesome_geo_traffic.py --summary

Requirements:
  pip install requests

GitHub Token needs: repo scope (for private repos) or public_repo scope.
Create at: https://github.com/settings/tokens
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Missing dependency: pip install requests")
    sys.exit(1)

# Configuration
REPO_OWNER = "vibetags"
REPO_NAME = "awesome-geo-tools"
DATA_DIR = Path(__file__).parent / "traffic_data"
VIEWS_FILE = DATA_DIR / "views.json"
CLONES_FILE = DATA_DIR / "clones.json"
REFERRERS_FILE = DATA_DIR / "referrers.json"
POPULAR_FILE = DATA_DIR / "popular_paths.json"
REPORT_FILE = DATA_DIR / "TRAFFIC_REPORT.md"


def get_headers():
    """Get GitHub API headers with authentication.
    Tries GITHUB_TOKEN env var first, then falls back to `gh auth token`."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        # Try gh CLI fallback
        import subprocess
        try:
            result = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                token = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    if not token:
        print("❌ Kein GitHub Token gefunden.")
        print("   Option A: export GITHUB_TOKEN='ghp_dein_token'")
        print("   Option B: gh auth login")
        sys.exit(1)
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def safe_api_call(url: str, headers: dict, label: str):
    """Make an API call that gracefully handles 403 (missing push access)."""
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 403:
            print(f"    ⚠️  {label}: Kein Zugriff (403) — benötigt push/admin Rechte")
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"    ⚠️  {label}: Fehler — {e}")
        return None


def load_json(filepath: Path) -> dict:
    """Load existing data or return empty structure."""
    if filepath.exists():
        with open(filepath, "r") as f:
            return json.load(f)
    return {"daily": {}, "meta": {"first_collected": None, "last_collected": None}}


def save_json(filepath: Path, data: dict):
    """Save data to JSON file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_views(headers: dict) -> dict:
    """Fetch page views (14-day rolling window from GitHub)."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/traffic/views"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def fetch_clones(headers: dict) -> dict:
    """Fetch clone data (14-day rolling window from GitHub)."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/traffic/clones"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def fetch_referrers(headers: dict) -> list:
    """Fetch top referral sources (last 14 days)."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/traffic/popular/referrers"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def fetch_popular_paths(headers: dict) -> list:
    """Fetch popular content paths (last 14 days)."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/traffic/popular/paths"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def fetch_repo_stats(headers: dict) -> dict:
    """Fetch basic repo statistics."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return {
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "watchers": data.get("subscribers_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "size_kb": data.get("size", 0),
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
    }


def collect_data():
    """Main collection routine — fetches all traffic data and stores it."""
    headers = get_headers()
    now = datetime.utcnow().isoformat() + "Z"
    today = datetime.utcnow().strftime("%Y-%m-%d")

    print(f"📊 Collecting traffic data for {REPO_OWNER}/{REPO_NAME}...")

    # --- Views (requires push access) ---
    print("  → Fetching page views...")
    views_api = safe_api_call(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/traffic/views",
        headers, "Views"
    )
    views_data = load_json(VIEWS_FILE)

    if views_api:
        new_days = 0
        for entry in views_api.get("views", []):
            date_key = entry["timestamp"][:10]
            if date_key not in views_data["daily"]:
                new_days += 1
            views_data["daily"][date_key] = {
                "count": entry["count"],
                "uniques": entry["uniques"],
            }
        views_data["meta"]["last_collected"] = now
        if not views_data["meta"]["first_collected"]:
            views_data["meta"]["first_collected"] = now
        views_data["meta"]["total_14d"] = views_api.get("count", 0)
        views_data["meta"]["uniques_14d"] = views_api.get("uniques", 0)
        save_json(VIEWS_FILE, views_data)
        print(f"    ✅ {len(views_data['daily'])} Tage gespeichert ({new_days} neu)")

    # --- Clones (requires push access) ---
    print("  → Fetching clones...")
    clones_api = safe_api_call(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/traffic/clones",
        headers, "Clones"
    )
    clones_data = load_json(CLONES_FILE)

    if clones_api:
        for entry in clones_api.get("clones", []):
            date_key = entry["timestamp"][:10]
            clones_data["daily"][date_key] = {
                "count": entry["count"],
                "uniques": entry["uniques"],
            }
        clones_data["meta"]["last_collected"] = now
        if not clones_data["meta"]["first_collected"]:
            clones_data["meta"]["first_collected"] = now
        clones_data["meta"]["total_14d"] = clones_api.get("count", 0)
        clones_data["meta"]["uniques_14d"] = clones_api.get("uniques", 0)
        save_json(CLONES_FILE, clones_data)
        print(f"    ✅ {len(clones_data['daily'])} Tage gespeichert")

    # --- Referrers (requires push access) ---
    print("  → Fetching referrers...")
    referrers = safe_api_call(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/traffic/popular/referrers",
        headers, "Referrers"
    )
    ref_data = load_json(REFERRERS_FILE)

    if referrers:
        ref_data["daily"][today] = [
            {"referrer": r["referrer"], "count": r["count"], "uniques": r["uniques"]}
            for r in referrers
        ]
        ref_data["meta"]["last_collected"] = now
        if not ref_data["meta"]["first_collected"]:
            ref_data["meta"]["first_collected"] = now
        save_json(REFERRERS_FILE, ref_data)
        print(f"    ✅ {len(referrers)} Referrer gefunden")

    # --- Popular Paths (requires push access) ---
    print("  → Fetching popular paths...")
    paths = safe_api_call(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/traffic/popular/paths",
        headers, "Popular Paths"
    )
    paths_data = load_json(POPULAR_FILE)

    if paths:
        paths_data["daily"][today] = [
            {"path": p["path"], "title": p["title"], "count": p["count"], "uniques": p["uniques"]}
            for p in paths
        ]
        paths_data["meta"]["last_collected"] = now
        if not paths_data["meta"]["first_collected"]:
            paths_data["meta"]["first_collected"] = now
        save_json(POPULAR_FILE, paths_data)
        print(f"    ✅ {len(paths)} populäre Pfade")

    # --- Repo Stats ---
    print("  → Fetching repo stats...")
    stats = fetch_repo_stats(headers)

    stats_file = DATA_DIR / "repo_stats.json"
    stats_data = load_json(stats_file)
    stats_data["daily"][today] = stats
    stats_data["meta"]["last_collected"] = now
    if not stats_data["meta"]["first_collected"]:
        stats_data["meta"]["first_collected"] = now
    save_json(stats_file, stats_data)
    print(f"    ✅ ⭐ {stats['stars']} Stars | 🍴 {stats['forks']} Forks | 👀 {stats['watchers']} Watchers")

    print(f"\n✅ Daten gespeichert in: {DATA_DIR}")
    return views_data, clones_data, ref_data, paths_data, stats


def print_summary(days: int = 7):
    """Print a quick summary of the last N days."""
    views_data = load_json(VIEWS_FILE)
    clones_data = load_json(CLONES_FILE)
    stats_file = DATA_DIR / "repo_stats.json"
    stats_data = load_json(stats_file)

    if not views_data["daily"]:
        print("❌ Keine Daten vorhanden. Erst `python3 awesome_geo_traffic.py` ausführen.")
        return

    print(f"\n📊 awesome-geo-tools Traffic — Letzte {days} Tage")
    print("=" * 60)

    # Views
    sorted_dates = sorted(views_data["daily"].keys(), reverse=True)[:days]
    total_views = sum(views_data["daily"][d]["count"] for d in sorted_dates)
    total_uniques = sum(views_data["daily"][d]["uniques"] for d in sorted_dates)

    print(f"\n👁️  Page Views:     {total_views:,} total | {total_uniques:,} unique visitors")
    print(f"📅 Avg/Tag:        {total_views / max(len(sorted_dates), 1):.0f} views | {total_uniques / max(len(sorted_dates), 1):.0f} unique")

    # Per-day breakdown
    print(f"\n{'Datum':<14} {'Views':>8} {'Unique':>8} {'Bar'}")
    print("-" * 50)
    for date in sorted_dates:
        d = views_data["daily"][date]
        bar = "█" * min(d["count"], 50)
        print(f"{date:<14} {d['count']:>8} {d['uniques']:>8} {bar}")

    # Clones
    sorted_clone_dates = sorted(clones_data.get("daily", {}).keys(), reverse=True)[:days]
    if sorted_clone_dates:
        total_clones = sum(clones_data["daily"][d]["count"] for d in sorted_clone_dates)
        total_clone_uniques = sum(clones_data["daily"][d]["uniques"] for d in sorted_clone_dates)
        print(f"\n📦 Git Clones:     {total_clones:,} total | {total_clone_uniques:,} unique")

    # Stars
    latest_stats = None
    if stats_data["daily"]:
        latest_date = sorted(stats_data["daily"].keys())[-1]
        latest_stats = stats_data["daily"][latest_date]
        print(f"\n⭐ Stars:          {latest_stats['stars']:,}")
        print(f"🍴 Forks:          {latest_stats['forks']:,}")
        print(f"👀 Watchers:       {latest_stats['watchers']:,}")

    # Referrers
    ref_data = load_json(REFERRERS_FILE)
    if ref_data["daily"]:
        latest_ref_date = sorted(ref_data["daily"].keys())[-1]
        refs = ref_data["daily"][latest_ref_date]
        if refs:
            print(f"\n🔗 Top Referrer (letzte Erhebung {latest_ref_date}):")
            for r in refs[:10]:
                print(f"   {r['referrer']:<30} {r['count']:>5} views | {r['uniques']:>5} unique")

    print("\n" + "=" * 60)


def generate_report():
    """Generate a full Markdown traffic report."""
    views_data = load_json(VIEWS_FILE)
    clones_data = load_json(CLONES_FILE)
    ref_data = load_json(REFERRERS_FILE)
    paths_data = load_json(POPULAR_FILE)
    stats_file = DATA_DIR / "repo_stats.json"
    stats_data = load_json(stats_file)

    if not views_data["daily"]:
        print("❌ Keine Daten vorhanden.")
        return

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    sorted_dates = sorted(views_data["daily"].keys())
    all_views = sum(views_data["daily"][d]["count"] for d in sorted_dates)
    all_uniques = sum(views_data["daily"][d]["uniques"] for d in sorted_dates)

    # Last 7 and 30 day stats
    last_7 = sorted_dates[-7:] if len(sorted_dates) >= 7 else sorted_dates
    last_30 = sorted_dates[-30:] if len(sorted_dates) >= 30 else sorted_dates

    views_7d = sum(views_data["daily"][d]["count"] for d in last_7)
    uniques_7d = sum(views_data["daily"][d]["uniques"] for d in last_7)
    views_30d = sum(views_data["daily"][d]["count"] for d in last_30)
    uniques_30d = sum(views_data["daily"][d]["uniques"] for d in last_30)

    # Latest stats
    latest_stats = {}
    if stats_data["daily"]:
        latest_date = sorted(stats_data["daily"].keys())[-1]
        latest_stats = stats_data["daily"][latest_date]

    report = f"""# 📊 awesome-geo-tools Traffic Report
**Generiert:** {now} | **Datenbereich:** {sorted_dates[0]} bis {sorted_dates[-1]} ({len(sorted_dates)} Tage)

---

## Zusammenfassung

| Metrik | Gesamt | Letzte 30 Tage | Letzte 7 Tage |
|--------|--------|----------------|---------------|
| **Page Views** | {all_views:,} | {views_30d:,} | {views_7d:,} |
| **Unique Visitors** | {all_uniques:,} | {uniques_30d:,} | {uniques_7d:,} |
| **⌀ Views/Tag** | {all_views / max(len(sorted_dates), 1):.0f} | {views_30d / max(len(last_30), 1):.0f} | {views_7d / max(len(last_7), 1):.0f} |
| **⌀ Unique/Tag** | {all_uniques / max(len(sorted_dates), 1):.0f} | {uniques_30d / max(len(last_30), 1):.0f} | {uniques_7d / max(len(last_7), 1):.0f} |

"""

    if latest_stats:
        report += f"""### Repo-Metriken
| ⭐ Stars | 🍴 Forks | 👀 Watchers |
|----------|----------|-------------|
| {latest_stats.get('stars', 0):,} | {latest_stats.get('forks', 0):,} | {latest_stats.get('watchers', 0):,} |

"""

    # Daily table (last 30 days)
    report += "## Tägliche Views (letzte 30 Tage)\n\n"
    report += "| Datum | Views | Unique | Trend |\n"
    report += "|-------|-------|--------|-------|\n"

    max_views = max((views_data["daily"][d]["count"] for d in last_30), default=1)
    for date in reversed(last_30):
        d = views_data["daily"][date]
        bar_len = int(d["count"] / max(max_views, 1) * 20)
        bar = "█" * bar_len
        report += f"| {date} | {d['count']:,} | {d['uniques']:,} | {bar} |\n"

    # Clones
    report += "\n## Git Clones\n\n"
    if clones_data["daily"]:
        clone_dates = sorted(clones_data["daily"].keys())
        all_clones = sum(clones_data["daily"][d]["count"] for d in clone_dates)
        report += f"**Gesamt:** {all_clones:,} Clones über {len(clone_dates)} Tage\n\n"

    # Referrers
    report += "## Top Referrer\n\n"
    if ref_data["daily"]:
        latest_ref_date = sorted(ref_data["daily"].keys())[-1]
        refs = ref_data["daily"][latest_ref_date]
        if refs:
            report += f"*Stand: {latest_ref_date}*\n\n"
            report += "| Referrer | Views | Unique |\n"
            report += "|----------|-------|--------|\n"
            for r in refs:
                report += f"| {r['referrer']} | {r['count']:,} | {r['uniques']:,} |\n"
        else:
            report += "Keine Referrer-Daten verfügbar.\n"

    # Popular paths
    report += "\n## Populäre Seiten\n\n"
    if paths_data["daily"]:
        latest_path_date = sorted(paths_data["daily"].keys())[-1]
        paths = paths_data["daily"][latest_path_date]
        if paths:
            report += f"*Stand: {latest_path_date}*\n\n"
            report += "| Seite | Views | Unique |\n"
            report += "|-------|-------|--------|\n"
            for p in paths:
                report += f"| `{p['path']}` | {p['count']:,} | {p['uniques']:,} |\n"

    # Star history
    report += "\n## Star-Verlauf\n\n"
    if stats_data["daily"]:
        report += "| Datum | Stars | Forks | Watchers |\n"
        report += "|-------|-------|-------|----------|\n"
        for date in sorted(stats_data["daily"].keys())[-30:]:
            s = stats_data["daily"][date]
            report += f"| {date} | {s.get('stars', 0):,} | {s.get('forks', 0):,} | {s.get('watchers', 0):,} |\n"

    report += f"\n---\n*Report generiert mit awesome_geo_traffic.py — Daten werden täglich gesammelt und persistent gespeichert.*\n"

    save_path = REPORT_FILE
    with open(save_path, "w") as f:
        f.write(report)
    print(f"📄 Report gespeichert: {save_path}")
    return report


def main():
    parser = argparse.ArgumentParser(
        description="📊 awesome-geo-tools GitHub Traffic Tracker"
    )
    parser.add_argument(
        "--report", action="store_true", help="Generiere einen vollen Markdown-Report"
    )
    parser.add_argument(
        "--summary", action="store_true", help="Zeige eine schnelle Zusammenfassung"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Anzahl Tage für Summary (Default: 7)"
    )
    parser.add_argument(
        "--no-collect",
        action="store_true",
        help="Nur Report/Summary, keine neuen Daten sammeln",
    )

    args = parser.parse_args()

    if not args.no_collect:
        collect_data()

    if args.report:
        generate_report()
    elif args.summary:
        print_summary(args.days)
    elif not args.no_collect:
        # Default: collect + show summary
        print_summary(args.days)


if __name__ == "__main__":
    main()
