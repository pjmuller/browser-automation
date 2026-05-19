"""Find LinkedIn handles for a CSV of (full_name, optional company/title) rows.

Writes <input>.results.csv next to the input.

    uv run linkedin-search                    # uses input.csv in this folder
    uv run linkedin-search path/to/other.csv

Env:
    LIMIT             max rows to actually search (skipped rows don't count)
    DELAY_SECONDS     pause between rows (default 1.5)
    COOLDOWN_SECONDS  cool-off when rate-limit suspected (default 60)
"""

import csv
import math
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import TypedDict
from urllib.parse import quote

from playwright.sync_api import Page

from lib.browser import attach, find_or_new, humanize


HERE = Path(__file__).parent


class InputRow(TypedDict, total=False):
    full_name: str
    company: str
    title: str
    linked_in_url: str


class Candidate(TypedDict):
    handle: str
    url: str
    text: str
    score: int


class ResultRow(TypedDict):
    full_name: str
    title: str
    company: str
    status: str  # confident | ambiguous | none | error | skipped
    handle: str
    profile_url: str
    headline: str
    score: str
    alt_handles: str
    notes: str


RESULT_FIELDS = [
    "full_name",
    "title",
    "company",
    "status",
    "handle",
    "profile_url",
    "headline",
    "score",
    "alt_handles",
    "notes",
]


def load_input(path: Path) -> list[InputRow]:
    rows: list[InputRow] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            row: InputRow = {
                "full_name": (r.get("full_name") or r.get("name") or "").strip(),
                "company": (r.get("company") or r.get("company_name") or "").strip(),
                "title": (r.get("title") or "").strip(),
                "linked_in_url": (r.get("linked_in_url") or "").strip(),
            }
            rows.append(row)
    return rows


def normalize(s: str) -> str:
    """Lowercase, strip diacritics, drop non-alnum, collapse whitespace."""
    s = s.lower()
    # NFKD then drop combining marks (diacritics).
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def name_tokens(name: str) -> list[str]:
    return [t for t in normalize(name).split(" ") if len(t) >= 2]


def company_stems(company: str) -> list[str]:
    """'Datawarehouse.io' -> ['datawarehouse'], 'Acme Inc.' -> ['acme']."""
    if not company:
        return []
    cleaned = company.lower()
    cleaned = re.sub(r"\.(io|com|net|org|co|ai|app|dev)\b", " ", cleaned)
    cleaned = re.sub(
        r"\b(inc|llc|ltd|gmbh|sa|corp|corporation|company|the)\b", " ", cleaned
    )
    return [t for t in normalize(cleaned).split(" ") if len(t) >= 3]


def score_candidate(text: str, row: InputRow) -> tuple[int, list[str]]:
    lower = text.lower()
    tokens = name_tokens(row.get("full_name", ""))
    reasons: list[str] = []
    score = 0

    name_hits = sum(1 for t in tokens if t in lower)
    if name_hits == 0:
        return 0, ["no name token"]
    score += name_hits
    if name_hits == len(tokens):
        reasons.append("all name tokens")
    else:
        reasons.append(f"{name_hits}/{len(tokens)} name tokens")

    if len(tokens) >= 2:
        adj = f"{tokens[0]} {tokens[-1]}"
        if adj in lower:
            score += 2
            reasons.append("first+last adjacent")

    title = row.get("title") or ""
    if title:
        title_toks = name_tokens(title)
        title_hits = sum(1 for t in title_toks if t in lower)
        if title_hits > 0:
            score += title_hits
            reasons.append(f"title: {title_hits}/{len(title_toks)}")

    stems = company_stems(row.get("company") or "")
    if stems:
        company_hits = sum(1 for s in stems if s in lower)
        if company_hits > 0:
            score += 3 + company_hits
            reasons.append("company matched")
        else:
            reasons.append("company missing")

    return score, reasons


def extract_headline(text: str, name: str) -> str:
    """'James Elmer • 2ndCo-Founder & CEO at ...' -> 'Co-Founder & CEO at ...'"""
    t = text.strip()
    lower_name = name.lower()
    if t.lower().startswith(lower_name):
        t = t[len(name):].strip()
    t = re.sub(r"^[•·\-—]\s*", "", t)
    t = re.sub(r"^(1st|2nd|3rd\+?|Following|Connect|Message)\s*", "", t, flags=re.I)
    return t[:200]


def clean_query(s: str) -> str:
    """Parens, brackets, ampersands confuse LinkedIn's people-search parser."""
    s = re.sub(r"[()\[\]{}<>&]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# JS snippet to collect /in/<handle> anchors from <main>, keeping the
# longest-text anchor per handle.
COLLECT_ANCHORS_JS = r"""(() => {
  const main = document.querySelector("main") || document.body;
  const anchors = Array.from(main.querySelectorAll("a[href*='/in/']"));
  const byHandle = new Map();
  for (const a of anchors) {
    const href = a.getAttribute("href") || "";
    const m = href.match(/\/in\/([^\/\?#]+)/);
    if (!m) continue;
    const handle = decodeURIComponent(m[1]);
    const text = (a.textContent || "").trim().replace(/\s+/g, " ");
    const prev = byHandle.get(handle);
    if (!prev || text.length > prev.text.length) {
      byHandle.set(handle, { handle, url: `https://www.linkedin.com/in/${handle}/`, text });
    }
  }
  return Array.from(byHandle.values());
})()"""


WAIT_FOR_RESULTS_JS = (
    r"""() => document.querySelector("main a[href*='/in/']") """
    r"""|| /No results|did not match/i.test(document.body.innerText || "")"""
)


def search_linkedin(
    page: Page, row: InputRow, query_override: str | None = None
) -> tuple[list[Candidate], int]:
    """Run a people-search and return (scored candidates desc, raw anchor count)."""
    raw_query = query_override if query_override is not None else " ".join(
        filter(None, [row.get("full_name", ""), row.get("company", "")])
    ).strip()
    query = clean_query(raw_query)
    url = f"https://www.linkedin.com/search/results/people/?keywords={quote(query)}"
    print(f'  searching: "{query}"')

    try:
        # `commit` waits for nav to be committed; `domcontentloaded` can hang
        # on LinkedIn because of long-poll connections.
        page.goto(url, wait_until="commit", timeout=15000)
    except Exception:
        pass

    try:
        page.wait_for_function(WAIT_FOR_RESULTS_JS, timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(1000)

    try:
        raw = page.evaluate(COLLECT_ANCHORS_JS)
    except Exception as err:
        # LinkedIn sometimes does a client-side redirect mid-poll, destroying
        # the execution context. Wait briefly and try once more.
        if "Execution context was destroyed" not in str(err):
            raise
        page.wait_for_timeout(2000)
        raw = page.evaluate(COLLECT_ANCHORS_JS)

    scored: list[Candidate] = []
    for r in raw:
        s, _ = score_candidate(r["text"], row)
        if s > 0:
            scored.append({
                "handle": r["handle"],
                "url": r["url"],
                "text": r["text"],
                "score": s,
            })
    scored.sort(key=lambda c: c["score"], reverse=True)

    print(f"  {len(raw)} unique profile links · {len(scored)} matched name")
    return scored, len(raw)


def classify(candidates: list[Candidate], has_company: bool) -> str:
    if not candidates:
        return "none"
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    clear_lead = (second is None) or (top["score"] - second["score"] >= 3)
    # Strong: name + company both matched (>=5) with a clear gap.
    if has_company and top["score"] >= 5 and clear_lead:
        return "confident"
    # Only one candidate and at least the full name tokens hit.
    if len(candidates) == 1 and top["score"] >= 2:
        return "confident"
    # Without a company we need a clean run on the name to call it confident.
    if not has_company and top["score"] >= 4 and clear_lead:
        return "confident"
    return "ambiguous"


def process_row(page: Page, row: InputRow) -> tuple[ResultRow, int]:
    candidates, anchors_raw = search_linkedin(page, row)
    max_anchors_raw = anchors_raw
    fallback_used = False
    # LinkedIn's keyword search can over-constrain when both name and company
    # are present. Retry name-only when we got nothing; scoring still uses the
    # company stem.
    if not candidates and row.get("company"):
        print("  ↻ no results — retrying with name-only")
        page.wait_for_timeout(1000)
        retry_candidates, retry_raw = search_linkedin(page, row, row["full_name"])
        candidates = retry_candidates
        max_anchors_raw = max(max_anchors_raw, retry_raw)
        fallback_used = True

    has_company = bool(row.get("company"))
    status = classify(candidates, has_company)
    top = candidates[0] if candidates else None
    alt_handles = " | ".join(
        f"{c['handle']} (score={c['score']})" for c in candidates[1:4]
    )
    if not candidates:
        notes = "no name match in results"
    elif fallback_used:
        notes = "name-only fallback"
    else:
        notes = ""

    result: ResultRow = {
        "full_name": row.get("full_name", ""),
        "title": row.get("title", "") or "",
        "company": row.get("company", "") or "",
        "status": status,
        "handle": top["handle"] if top else "",
        "profile_url": top["url"] if top else "",
        "headline": extract_headline(top["text"], row.get("full_name", "")) if top else "",
        "score": str(top["score"]) if top else "",
        "alt_handles": alt_handles,
        "notes": notes,
    }
    return result, max_anchors_raw


def write_results(path: Path, results: list[ResultRow]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writeheader()
        for r in results:
            w.writerow(r)


def _resolve_input_path(arg: str) -> Path:
    """Bare filename (no separator) → resolve against script dir; paths with
    `/` or starting with `~` are used as given (after expansion)."""
    if arg.startswith("~") or "/" in arg:
        return Path(arg).expanduser().resolve()
    return (HERE / arg).resolve()


def main() -> None:
    input_arg = sys.argv[1] if len(sys.argv) > 1 else "input.csv"
    input_path = _resolve_input_path(input_arg)
    # Match TS basename(inputPath, ".csv") + ".results.csv" precisely.
    stem = input_path.stem
    output_path = input_path.parent / f"{stem}.results.csv"

    rows = load_input(input_path)

    limit_env = os.environ.get("LIMIT")
    limit = int(limit_env) if limit_env else math.inf
    delay_ms = int(float(os.environ.get("DELAY_SECONDS", "1.5")) * 1000)
    cooldown_ms = int(float(os.environ.get("COOLDOWN_SECONDS", "60")) * 1000)

    searched = 0
    zero_anchor_streak = 0  # circuit breaker — likely rate-limit signal
    results: list[ResultRow] = []

    with attach() as ctx:
        page = find_or_new(ctx, lambda p: "linkedin.com" in p.url)
        page = humanize(page)

        try:
            for i, row in enumerate(rows):
                label = row["full_name"] + (f" @ {row['company']}" if row.get("company") else "")
                print(f"\n[{i + 1}/{len(rows)}] {label}")

                # Skip if LinkedIn URL already present.
                if row.get("linked_in_url"):
                    url = row["linked_in_url"]
                    print(f"  ⊘ skipping (url already provided: {url})")
                    m = re.search(r"/in/([^/?#]+)", url)
                    results.append({
                        "full_name": row.get("full_name", ""),
                        "title": row.get("title", "") or "",
                        "company": row.get("company", "") or "",
                        "status": "skipped",
                        "handle": m.group(1) if m else "",
                        "profile_url": url,
                        "headline": "",
                        "score": "",
                        "alt_handles": "",
                        "notes": "provided",
                    })
                    continue

                if searched >= limit:
                    print(f"  ⊘ LIMIT={limit} reached — stopping")
                    break

                try:
                    r, max_anchors_raw = process_row(page, row)
                    results.append(r)
                    searched += 1
                    suffix = f" {r['handle']} (score={r['score']})" if r["handle"] else ""
                    print(f"  → {r['status']}{suffix}")
                    if r["alt_handles"]:
                        print(f"     alts: {r['alt_handles']}")
                    if max_anchors_raw == 0:
                        zero_anchor_streak += 1
                    else:
                        zero_anchor_streak = 0
                except Exception as err:
                    msg = str(err).split("\n")[0]
                    print(f"  ✗ {msg}")
                    results.append({
                        "full_name": row.get("full_name", ""),
                        "title": row.get("title", "") or "",
                        "company": row.get("company", "") or "",
                        "status": "error",
                        "handle": "",
                        "profile_url": "",
                        "headline": "",
                        "score": "",
                        "alt_handles": "",
                        "notes": msg,
                    })
                    searched += 1

                # Circuit breaker: 2+ zero-anchor responses in a row almost
                # always means LinkedIn served a login wall / rate-limit page.
                # Cool off before the next attempt.
                if zero_anchor_streak >= 2:
                    print(
                        f"  ⏸  {zero_anchor_streak} consecutive zero-anchor rows"
                        f" — cooling off {cooldown_ms / 1000}s"
                    )
                    page.wait_for_timeout(cooldown_ms)
                    zero_anchor_streak = 0
                else:
                    page.wait_for_timeout(delay_ms)
        finally:
            write_results(output_path, results)
            print(f"\n✓ Wrote {len(results)} rows → {output_path}")


if __name__ == "__main__":
    main()
