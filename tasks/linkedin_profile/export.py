"""Export LinkedIn profile frontmatter to CSV."""

import csv
from pathlib import Path

import yaml


def main() -> None:
    here = Path(__file__).parent
    data_dir = here / "data"
    output_csv = here / "profiles.csv"

    md_files = sorted(data_dir.glob("*.md"))
    if not md_files:
        print(f"No .md files found in {data_dir}")
        return

    rows = []
    for md_path in md_files:
        try:
            text = md_path.read_text()
            _, fm, _ = text.split("---", 2)
            frontmatter = yaml.safe_load(fm) or {}
            rows.append(frontmatter)
        except Exception as e:
            print(f"  ! Error parsing {md_path.name}: {e}")

    if not rows:
        print("No valid frontmatter found.")
        return

    # Collect all unique keys across all rows
    all_keys = set()
    for row in rows:
        all_keys.update(row.keys())

    fieldnames = sorted(all_keys)

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} profiles to {output_csv}")


if __name__ == "__main__":
    main()
