"""Scrape a LinkedIn profile into a structured markdown file.

Synchronous Playwright only — no asyncio. The user's real Chrome is attached
over CDP via lib.browser.attach(), and we never call page.bring_to_front().

Non-obvious bits worth preserving:
  * Profile image URLs are captured via a raw CDP Network session, NOT via
    page.route(): LinkedIn lazy-loads the avatar through code paths that
    bypass Playwright's request interception in some cases. We listen for
    Network.requestWillBeSent and pick the largest profile-displayphoto
    variant by its `{width}_{height}` suffix.
  * Navigation uses wait_until="commit". LinkedIn keeps long-poll requests
    open, so "domcontentloaded" / "load" can hang indefinitely.
  * Selectors target [componentkey] attributes — those are stable; the
    hashed CSS class names are not.
  * Lazy sections (Experience, Education, Skills) need a stepped scroll of
    ~300px to trigger LinkedIn's IntersectionObserver-based loaders. We do
    NOT scroll back to the top afterwards — it re-triggers loaders and
    sometimes wipes already-rendered DOM.
  * safe_eval retries on "context was destroyed" — a stray LinkedIn redirect
    (e.g. login wall) can kill the execution context mid-evaluate.
  * If a section is missing inline (condensed layout), fall back to the
    /details/<section>/ page.
  * Skills: ignore -divider / -endorser / endorsers entries and dedupe by
    componentkey.
  * Mutual connections: scope to <main>, dedupe by normalised href, and
    drop any link back to the searched-for person.
"""

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from lib.browser import attach, find_or_new, humanize


# ── helpers ────────────────────────────────────────────────────────────────


def safe_eval(page, expr: str, arg: Any = None, retries: int = 2) -> Any:
    """Evaluate JS with retry on context-destroyed errors.

    LinkedIn occasionally redirects mid-evaluate (e.g. when an auth ping
    fails), which destroys the JS execution context. A short sleep and
    retry is usually enough to recover on the post-redirect page.
    """
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            if arg is None:
                return page.evaluate(expr)
            return page.evaluate(expr, arg)
        except Exception as e:
            last_err = e
            if "context was destroyed" not in str(e) and "Execution context was destroyed" not in str(e):
                raise
            page.wait_for_timeout(2000)
    assert last_err is not None
    raise last_err


def goto(page, url: str, wait_selector: str | None = None) -> None:
    """Navigate with custom waits.

    Uses wait_until="commit" because LinkedIn's long-poll requests stop
    "domcontentloaded" / "load" from ever firing reliably.
    """
    try:
        page.goto(url, wait_until="commit", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(3000)
    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=8000)
        except Exception:
            pass
    page.wait_for_timeout(1500)


def pick_best_photo_url(urls: list[str]) -> str | None:
    """Score profile photo URLs by pixel size and return the largest."""
    scored: list[tuple[int, str]] = []
    for u in urls:
        m = re.search(r"profile-displayphoto-(?:scale|shrink|crop)_(\d+)_(\d+)", u)
        size = int(m.group(1)) if m else 0
        scored.append((size, u))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[0][1]


def format_entry(lines: list[str]) -> str:
    """Format a section entry — first line bold (title), rest below."""
    if not lines:
        return ""
    title, *rest = lines
    if not rest:
        return f"**{title}**"
    return f"**{title}**\n" + "\n".join(rest)


# ── JS snippets (kept as constants for readability) ────────────────────────


GET_P_TEXTS_JS = r"""
function getPTexts(el) {
  return Array.from(el.querySelectorAll("p")).map(p => {
    const c = p.childNodes;
    return (c.length === 1 && c[0].nodeType === 3) ? c[0].textContent.trim() : null;
  }).filter(Boolean);
}
"""


SCROLL_STEPPED_JS = r"""
(() => {
  return new Promise(resolve => {
    let y = 0;
    const step = () => {
      y += 300;
      window.scrollTo(0, y);
      if (y < document.body.scrollHeight) setTimeout(step, 400);
      else resolve(null);
    };
    step();
  });
})()
"""


EXPAND_ABOUT_JS = r"""
(() => {
  const aboutSection = document.querySelector("section[componentkey$='About']") ||
    Array.from(document.querySelectorAll("section")).find(s => {
      const h = s.querySelector("h2");
      return h && h.textContent.toLowerCase().includes("about");
    });
  if (!aboutSection) return;
  const btn = Array.from(aboutSection.querySelectorAll("button")).find(b => {
    const t = (b.getAttribute("aria-label") || b.textContent || "").toLowerCase();
    return t.includes("see more") || t.includes("show more");
  });
  if (btn) btn.click();
})()
"""


SCROLL_EXPERIENCE_INTO_VIEW_JS = r"""
(() => {
  const s = document.querySelector("section[componentkey*='ExperienceTopLevel']");
  if (s) s.scrollIntoView({ block: 'center' });
})()
"""


TOPCARD_JS = r"""
(() => {
  const tc = document.querySelector("[componentkey*='Topcard']");
  if (!tc) return null;

  const name = (tc.querySelector("h1, h2")?.textContent || "").trim();

  const pTexts = Array.from(tc.querySelectorAll("p")).map(p => {
    const c = p.childNodes;
    return (c.length === 1 && c[0].nodeType === 3) ? c[0].textContent.trim() : null;
  }).filter(Boolean);

  let headline = "", location = "";
  for (const t of pTexts) {
    if (t.startsWith("·") || t.includes("follower") || t.includes("connection") || t.includes("Premium")) continue;
    if (!headline) { headline = t; continue; }
    if (!location) { location = t; break; }
  }

  const followers = pTexts.find(t => t.includes("follower")) || "";
  const connections = pTexts.find(t => t.includes("connection")) || "";

  const mutualA = Array.from(tc.querySelectorAll("a")).find(a =>
    (a.textContent || "").replace(/\s+/g, " ").toLowerCase().includes("mutual connection")
  );
  const mutualText = mutualA ? (mutualA.textContent || "").replace(/\s+/g, " ").trim() : "";
  const mutualHref = mutualA ? mutualA.href : "";

  return { name, headline, location, followers, connections, mutualText, mutualHref };
})()
"""


ABOUT_JS = r"""
(() => {
  const s = document.querySelector("section[componentkey$='About']") ||
    Array.from(document.querySelectorAll("section")).find(s => {
      const h = s.querySelector("h2");
      return h && h.textContent.toLowerCase().includes("about");
    });
  if (!s) return "";
  const box = s.querySelector("[data-testid='expandable-text-box']");
  if (box) return (box.textContent || "").replace(/\s+/g, " ").trim();
  return (s.textContent || "").replace(/\s+/g, " ").trim().replace(/^About\s*/, "");
})()
"""


# Inline extractors require the specific TopLevel section — they must NOT
# fall back to <main>, or we get garbage when called from a /details/<other>/
# page (e.g. running EDUCATION on the /details/experience/ page returns the
# experience items because they live under <main>).
EXTRACT_EXPERIENCE_INLINE_JS = f"""(() => {{
  {GET_P_TEXTS_JS}
  const s = document.querySelector("section[componentkey*='ExperienceTopLevel']");
  if (!s) return [];
  return Array.from(s.querySelectorAll("[componentkey^='entity-collection-item']"))
    .map(item => getPTexts(item));
}})()"""


EXTRACT_EDUCATION_INLINE_JS = f"""(() => {{
  {GET_P_TEXTS_JS}
  const s = document.querySelector("section[componentkey*='EducationTopLevel']");
  if (!s) return [];
  const UUID_RE = /^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$/;
  const entityItems = Array.from(s.querySelectorAll("[componentkey^='entity-collection-item']"));
  if (entityItems.length) return entityItems.map(item => getPTexts(item));
  const uuidItems = Array.from(s.querySelectorAll("[componentkey]")).filter(el =>
    UUID_RE.test(el.getAttribute("componentkey") || "")
  );
  return uuidItems.map(item => getPTexts(item));
}})()"""


# Details-page extractors use <main> — required because the dedicated
# /details/{experience,education}/ pages don't wrap items in a TopLevel
# section, but <main> only contains the relevant items there.
EXTRACT_EXPERIENCE_DETAILS_JS = f"""(() => {{
  {GET_P_TEXTS_JS}
  const s = document.querySelector("main");
  if (!s) return [];
  return Array.from(s.querySelectorAll("[componentkey^='entity-collection-item']"))
    .map(item => getPTexts(item));
}})()"""


EXTRACT_EDUCATION_DETAILS_JS = f"""(() => {{
  {GET_P_TEXTS_JS}
  const main = document.querySelector("main");
  if (!main) return [];
  const UUID_RE = /^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$/;
  const entityItems = Array.from(main.querySelectorAll("[componentkey^='entity-collection-item']"));
  if (entityItems.length) return entityItems.map(item => getPTexts(item));
  // UUID-componentkey fallback: scope to the nearest <section> of the first
  // UUID item, otherwise <main> also matches the footer's UUID items.
  const allUuid = Array.from(main.querySelectorAll("[componentkey]")).filter(el =>
    UUID_RE.test(el.getAttribute("componentkey") || "")
  );
  if (!allUuid.length) return [];
  const scope = allUuid[0].closest("section") || allUuid[0].parentElement;
  if (!scope) return [];
  const seen = new Set();
  const scoped = Array.from(scope.querySelectorAll("[componentkey]")).filter(el => {{
    const ck = el.getAttribute("componentkey") || "";
    if (!UUID_RE.test(ck)) return false;
    if (seen.has(ck)) return false;
    seen.add(ck);
    return true;
  }});
  return scoped.map(item => getPTexts(item));
}})()"""


SKILLS_JS = r"""
(() => {
  const main = document.querySelector("main") || document.body;
  const seen = new Set();

  const items = Array.from(main.querySelectorAll("[componentkey*='profile.skill']")).filter(el => {
    const ck = el.getAttribute("componentkey") || "";
    // Drop divider / endorser / endorsers entries — they're not skills.
    if (ck.includes("-divi") || ck.includes("-endorser") || ck.includes("endorsers")) return false;
    if (seen.has(ck)) return false;
    seen.add(ck);
    return true;
  });

  return items.map(el => {
    let name = "";
    for (const child of el.querySelectorAll("p, span")) {
      const c = child.childNodes;
      if (c.length === 1 && c[0].nodeType === 3) {
        const t = c[0].textContent.trim();
        if (t && !t.toLowerCase().includes("endorse") && !t.includes("colleague")) {
          name = t;
          break;
        }
      }
    }
    const endorseMatch = (el.textContent || "").match(/(\d+)\s*endorsement/);
    return { name, endorsements: endorseMatch ? parseInt(endorseMatch[1]) : 0 };
  }).filter(s => s.name);
})()
"""


MUTUAL_JS = r"""
(selfSlug) => {
  const main = document.querySelector("main") || document.body;
  const seen = new Set();
  return Array.from(main.querySelectorAll("a[href*='/in/']"))
    .filter(a => {
      const r = a.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    })
    .reduce((acc, a) => {
      const normalised = a.href.split("?")[0].replace(/\/+$/, "");
      if (seen.has(normalised)) return acc;
      seen.add(normalised);
      if (normalised.includes(`/in/${selfSlug}`)) return acc;
      const rawName = (a.textContent || "").replace(/\s+/g, " ").trim();
      const name = rawName.split("•")[0].trim();
      if (name.length < 2) return acc;
      acc.push({ name, url: normalised });
      return acc;
    }, []);
}
"""


FETCH_IMAGE_JS = r"""
async (url) => {
  const res = await fetch(url);
  const buf = await res.arrayBuffer();
  return Array.from(new Uint8Array(buf));
}
"""


# ── main flow ──────────────────────────────────────────────────────────────


def wait_for_experience_items(page, timeout_ms: int) -> bool:
    try:
        page.wait_for_selector(
            "section[componentkey*='ExperienceTopLevel'] [componentkey^='entity-collection-item']",
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


def attach_photo_capture(page) -> list[str]:
    """Subscribe to CDP Network events and collect profile-displayphoto URLs.

    We deliberately use a raw CDP session here instead of page.route(): some
    LinkedIn lazy-load paths bypass Playwright's interceptor, but every HTTP
    request still surfaces as a Network.requestWillBeSent event over CDP.
    """
    photo_requests: list[str] = []
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.enable")

    def on_request(event):
        try:
            url = event.get("request", {}).get("url", "")
        except Exception:
            url = ""
        if url and "profile-displayphoto" in url:
            photo_requests.append(url)

    cdp.on("Network.requestWillBeSent", on_request)
    return photo_requests


def scrape(profile_url: str, slug: str, output_dir: Path) -> None:
    with attach() as ctx:
        page = find_or_new(ctx, lambda p: "linkedin.com" in p.url)
        # humanize() must run once at start — it patches the page's mouse /
        # typing primitives. Idempotent re-application is not guaranteed.
        page = humanize(page)

        print(f"Scraping: {profile_url} → {slug}")

        photo_requests = attach_photo_capture(page)

        # ── 1. Load profile ─────────────────────────────────────────────
        goto(page, profile_url, "[componentkey*='Topcard']")
        print(f"After goto: {page.url}")

        topcard_present = bool(
            page.evaluate("!!document.querySelector(\"[componentkey*='Topcard']\")")
        )
        if not topcard_present:
            print("  Topcard missing after initial load — reloading...")
            try:
                page.reload(wait_until="commit", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            try:
                page.wait_for_selector("[componentkey*='Topcard']", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(1500)

        # Stepped scroll wakes LinkedIn's IntersectionObserver loaders. Do
        # NOT scroll back to the top — it can wipe already-rendered DOM.
        safe_eval(page, SCROLL_STEPPED_JS)

        exp_ready = wait_for_experience_items(page, 4000)
        if not exp_ready:
            safe_eval(page, SCROLL_EXPERIENCE_INTO_VIEW_JS)
            page.wait_for_timeout(1000)
            exp_ready = wait_for_experience_items(page, 3000)
        page.wait_for_timeout(300)

        # Expand About if it has a "see more" button.
        safe_eval(page, EXPAND_ABOUT_JS)
        page.wait_for_timeout(300)

        # ── 2. Topcard ──────────────────────────────────────────────────
        print("Extracting topcard...")
        topcard = safe_eval(page, TOPCARD_JS) or {}

        # ── 3. About ────────────────────────────────────────────────────
        print("Extracting about...")
        about = safe_eval(page, ABOUT_JS) or ""

        # ── 4. Experience + Education (inline) ──────────────────────────
        # Extract both inline BEFORE any /details/ navigation. If we extract
        # education after navigating to /details/experience/, the education
        # extractor would see the experience items under <main>.
        print("Extracting experience...")
        experience = safe_eval(page, EXTRACT_EXPERIENCE_INLINE_JS) or []
        print("Extracting education...")
        education = safe_eval(page, EXTRACT_EDUCATION_INLINE_JS) or []

        # Fall back to dedicated /details/<section>/ pages for whichever
        # section was empty inline (condensed layout / A-B test variant).
        if not experience:
            print("  (none inline — trying /details/experience/)")
            goto(page, f"https://www.linkedin.com/in/{slug}/details/experience/")
            experience = safe_eval(page, EXTRACT_EXPERIENCE_DETAILS_JS) or []

        if not education:
            print("  (none inline — trying /details/education/)")
            goto(page, f"https://www.linkedin.com/in/{slug}/details/education/")
            education = safe_eval(page, EXTRACT_EDUCATION_DETAILS_JS) or []

        # ── 6. Skills ───────────────────────────────────────────────────
        print("Loading skills details page...")
        goto(page, f"https://www.linkedin.com/in/{slug}/details/skills/")
        # Stepped scroll for skills — they lazy-load past the fold too.
        safe_eval(page, SCROLL_STEPPED_JS)
        skills = safe_eval(page, SKILLS_JS) or []

        # ── 7. Mutual connections ───────────────────────────────────────
        mutual_connections: list[dict] = []
        mutual_href = topcard.get("mutualHref") if topcard else None

        if mutual_href:
            print("Loading mutual connections...")
            goto(page, mutual_href)
            safe_eval(page, SCROLL_STEPPED_JS)
            mutual_connections = safe_eval(page, MUTUAL_JS, slug) or []

        # ── 8. Download profile image ───────────────────────────────────
        image_url = pick_best_photo_url(photo_requests)
        image_saved = False
        if image_url:
            variant = re.search(r"profile-displayphoto-\w+_\d+_\d+", image_url)
            variant_str = variant.group(0) if variant else "unknown"
            print(f"Downloading profile image ({variant_str})...")
            try:
                # Fetch from inside the page — credentialed CDN URLs work
                # because the browser already has the session cookies.
                image_buffer = page.evaluate(FETCH_IMAGE_JS, image_url)
                image_path = output_dir / f"{slug}.jpg"
                with open(image_path, "wb") as f:
                    f.write(bytes(image_buffer))
                image_saved = True
                print(f"Image saved: {image_path}")
            except Exception as e:
                print(f"Image download failed: {e}")
        else:
            print("No profile-displayphoto URL observed.")

        # ── 9. Build markdown ───────────────────────────────────────────
        write_markdown(
            slug=slug,
            profile_url=profile_url,
            output_dir=output_dir,
            topcard=topcard,
            about=about,
            experience=experience,
            education=education,
            skills=skills,
            mutual_connections=mutual_connections,
            image_url=image_url,
            image_saved=image_saved,
        )


def write_markdown(
    *,
    slug: str,
    profile_url: str,
    output_dir: Path,
    topcard: dict,
    about: str,
    experience: list[list[str]],
    education: list[list[str]],
    skills: list[dict],
    mutual_connections: list[dict],
    image_url: str | None,
    image_saved: bool,
) -> None:
    name = topcard.get("name") or slug
    headline = topcard.get("headline", "")
    location = topcard.get("location", "")
    followers = topcard.get("followers", "")
    connections = topcard.get("connections", "")
    mutual_text = topcard.get("mutualText", "")

    md_parts: list[str] = [
        f"# {name}\n",
        "## About\n",
        about or "_No about section._",
        "\n---\n\n## Mutual Connections\n",
    ]

    if mutual_text:
        md_parts.append(f"> {mutual_text}\n")

    if mutual_connections:
        md_parts.extend(
            f"- [{m['name']}]({m['url']})" for m in mutual_connections
        )
    else:
        md_parts.append("_None found or not connected._")

    md_parts.extend(
        [
            "\n---\n\n## Experience\n",
            "\n\n".join(format_entry(lines) for lines in experience if lines)
            or "_None._",
            "\n---\n\n## Education\n",
            "\n\n".join(format_entry(lines) for lines in education if lines)
            or "_None._",
            "\n---\n\n## Skills\n",
        ]
    )

    if skills:
        skill_lines = [
            f"- **{s['name']}** _({s['endorsements']} endorsements)_"
            if s.get("endorsements", 0) > 0
            else f"- {s['name']}"
            for s in skills
        ]
        md_parts.append("\n".join(skill_lines))
    else:
        md_parts.append("_No skills found._")

    md_parts.append("\n---\n")

    frontmatter = {
        "name": name,
        "headline": headline,
        "location": location,
        "followers": followers,
        "connections": connections,
        "profile_url": profile_url,
        "image": f"{slug}.jpg" if image_saved else "",
        "image_url": image_url or "",
        "scraped": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    md = "---\n" + yaml.dump(frontmatter, default_flow_style=False, sort_keys=False) + "---\n\n"
    md += "\n".join(md_parts)

    md_path = output_dir / f"{slug}.md"
    with open(md_path, "w") as f:
        f.write(md)
    print(f"Markdown saved: {md_path}")


def main() -> None:
    output_dir = Path(__file__).parent / "data"
    output_dir.mkdir(exist_ok=True)

    if len(sys.argv) >= 2:
        # Single URL mode
        profile_url = sys.argv[1]
        slug_match = re.search(r"linkedin\.com/in/([^/?#]+)", profile_url)
        if not slug_match:
            print("Invalid LinkedIn profile URL (expected /in/<slug>)")
            sys.exit(1)
        slug = slug_match.group(1)
        scrape(profile_url, slug, output_dir)
    else:
        # CSV mode
        csv_path = Path(__file__).parent / "input_2026.csv"
        if not csv_path.exists():
            print(f"CSV file not found: {csv_path}")
            sys.exit(1)

        rows = []
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("LinkedIn URL", "").strip()
                if url:
                    rows.append((row.get("Name", ""), url))

        print(f"Found {len(rows)} profiles with URLs in CSV")

        for i, (name, profile_url) in enumerate(rows):
            print(f"\n{'='*60}")
            print(f"[{i+1}/{len(rows)}] {name}")
            print(f"{'='*60}")

            slug_match = re.search(r"linkedin\.com/in/([^/?#]+)", profile_url)
            if not slug_match:
                print(f"  Skipping: Invalid URL format")
                continue

            slug = slug_match.group(1)
            try:
                scrape(profile_url, slug, output_dir)
            except Exception as e:
                print(f"  Error: {e}")

            if i < len(rows) - 1:
                wait_time = 8
                print(f"\nWaiting {wait_time}s before next profile...")
                time.sleep(wait_time)


if __name__ == "__main__":
    main()
