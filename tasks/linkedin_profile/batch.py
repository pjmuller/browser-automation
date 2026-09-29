"""Batch-scrape LinkedIn profiles from a CSV.

Reads `input_2026.csv` (header: Name, Title, Company, LinkedIn URL),
skips rows without a URL, skips slugs already present in data/, calls
scrape() per profile with a pause between, and bails out loudly if a
captcha/wall is detected (heuristic: topcard.name fell back to the slug).
"""

import csv
import re
import sys
import time
from pathlib import Path

import yaml

from tasks.linkedin_profile.scrape import scrape

PAUSE_BETWEEN_PROFILES_SEC = 30


def slug_from_url(url: str) -> str | None:
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url)
    return m.group(1) if m else None


def looks_like_captcha_output(md_path: Path, slug: str) -> bool:
    """A scrape that hit a captcha writes frontmatter where name == slug.

    The real scrape always pulls the human-readable name from the topcard;
    only the fallback path uses the slug. Treat that as a signal that the
    page didn't render and the markdown is junk.
    """
    if not md_path.exists():
        return True
    try:
        text = md_path.read_text()
        _, fm, _ = text.split("---", 2)
        data = yaml.safe_load(fm) or {}
    except Exception:
        return True
    name = (data.get("name") or "").strip()
    return name == slug or not name


def main() -> None:
    here = Path(__file__).parent
    csv_path = here / "input_2026.csv"
    output_dir = here / "data"
    output_dir.mkdir(exist_ok=True)

    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    todo: list[tuple[str, str, str]] = []  # (name, slug, url)
    skipped_no_url: list[str] = []
    skipped_existing: list[str] = []

    for r in rows:
        name = (r.get("Name") or "").strip()
        url = (r.get("LinkedIn URL") or "").strip()
        if not url:
            skipped_no_url.append(name)
            continue
        slug = slug_from_url(url)
        if not slug:
            print(f"  ! invalid URL for {name}: {url}")
            continue
        md_path = output_dir / f"{slug}.md"
        if md_path.exists() and not looks_like_captcha_output(md_path, slug):
            skipped_existing.append(slug)
            continue
        todo.append((name, slug, url))

    print(f"To scrape: {len(todo)}")
    print(f"Skipped (no URL)  : {len(skipped_no_url)}  {skipped_no_url}")
    print(f"Skipped (already) : {len(skipped_existing)}")

    for i, (name, slug, url) in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {name} → {slug}")
        try:
            scrape(url, slug, output_dir)
        except Exception as e:
            print(f"  ! scrape raised: {e}")
            print("  Aborting batch — investigate before resuming.")
            sys.exit(2)

        md_path = output_dir / f"{slug}.md"
        if looks_like_captcha_output(md_path, slug):
            print(f"  ! {slug}.md looks empty (no name extracted) — likely a captcha/wall.")
            # Delete the junk files so a future run will retry.
            for ext in (".md", ".jpg"):
                p = output_dir / f"{slug}{ext}"
                if p.exists():
                    p.unlink()
            print("  Aborting batch — solve the challenge in the visible CloakBrowser, then re-run.")
            sys.exit(3)

        if i < len(todo):
            print(f"  Sleeping {PAUSE_BETWEEN_PROFILES_SEC}s before next profile...")
            time.sleep(PAUSE_BETWEEN_PROFILES_SEC)

    print(f"\nDone. Scraped {len(todo)} profile(s).")


if __name__ == "__main__":
    main()
