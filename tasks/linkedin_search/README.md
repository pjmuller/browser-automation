# linkedin_search

Find LinkedIn handles for a CSV of (full name, optional company) rows. Picks a single match when confident, falls back to multiple candidates when ambiguous.

Pure Playwright over CDP — no LLM, no API keys. Uses `/search/results/people/?keywords=…` and reads `a[href*='/in/']` anchors from the results pane.

## What it does

For each row in `input.csv`:
1. If `linked_in_url` is already set → status `skipped`, URL passed through, no search.
2. Otherwise navigate to `https://www.linkedin.com/search/results/people/?keywords={name + company}`.
3. If that returns zero hits, retry name-only (LinkedIn's keyword search can over-constrain — e.g. `"Alex Casals Taclia"` → 0 results, `"Alex Casals"` → him at #1).
4. Collect every unique `/in/<handle>` anchor inside `<main>` (dedupe avatar vs. card anchors by keeping the longest text blob per handle).
5. Score each candidate: name-token hits, first+last adjacency bonus, title-token hits, company stem hits.
6. Classify: `confident` / `ambiguous` / `none` / `skipped` / `error` and write to `input.results.csv`.

## Scoring

| Signal | Points |
| --- | --- |
| Each name token present | +1 each |
| First & last name appear adjacently | +2 |
| Each title token present (e.g. `founder`, `ceo`) | +1 each |
| Any company stem present | +3 plus +1 per extra stem |

`companyStems("Datawarehouse.io")` → `["datawarehouse"]` (TLD stripped). `Inc / LLC / Corp / The` are dropped.

**Status:**
- `confident` — top score ≥5 with company match, OR single candidate that hits the full name, OR (no-company case) score ≥4 with a 3-point lead over #2.
- `ambiguous` — multiple plausible matches; top result still goes in `handle`, runners-up land in `alt_handles`.
- `none` — no candidate had a name-token hit.

## Run

```bash
uv run cloak                  # start (or keep open) the CloakBrowser
uv run linkedin-search        # defaults to input.csv in this folder
uv run linkedin-search path/to/other.csv
uv run linkedin-search input.csv 5    # only run the first 5 non-skipped rows (for testing)
```

## CSV format

**Input** (`input.csv`):

```csv
full_name,title,company,linked_in_url
James Elmer,Co-Founder & CEO,Datawarehouse.io,
Jane Smith,,,
Alex Casals,Founder & CEO,Taclia,https://www.linkedin.com/in/alexcasals
```

`title`, `company`, and `linked_in_url` are all optional. Either `full_name` or `name` is accepted as a column header. Rows with `linked_in_url` already set are passed through unchanged (status `skipped`).

**Output** (`input.results.csv`):

```csv
full_name,title,company,status,handle,profile_url,headline,score,alt_handles,notes
James Elmer,Co-Founder & CEO,Datawarehouse.io,confident,james-b-elmer,https://www.linkedin.com/in/james-b-elmer/,Co-Founder & CEO at Datawarehouse.io...,8,,
```

## Debugging

`explore.py` dumps the matched anchors for one query — useful when LinkedIn changes the DOM:

```bash
uv run linkedin-search-explore "James Elmer Datawarehouse.io"
```
