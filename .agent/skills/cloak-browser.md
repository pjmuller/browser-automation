# Skill: cloak-browser

When automating a website you'll run more than ~5 times, **explore the live page first via CDP, then write deterministic sync Playwright Python** — driven by **CloakBrowser** (a stealth Chromium that defeats fingerprint-based bot detection).

## When to use this skill

- Target site has stable-enough selectors (most production SaaS, LinkedIn, GitHub, Stripe dashboard, etc.).
- Same flow will run repeatedly (batched job, scheduled task).
- The target uses fingerprint detection (reCAPTCHA v3 / Cloudflare Turnstile / FingerprintJS) — CloakBrowser passes where vanilla Playwright fails.
- You want speed, zero LLM spend, and an error trace pointing at a real selector.

Skip this skill (and use an LLM-driven loop) only when the flow is one-shot, the DOM is genuinely fluid, or the task needs semantic reasoning on page content.

## One-time setup

```bash
mise install                              # Python 3.13
uv sync                                   # installs cloakbrowser + playwright
uv run python -m cloakbrowser install     # downloads the 140 MB stealth Chromium
cp .env.example .env
```

First time only — run **headed** to log in:

```bash
CLOAK_HEADED=1 uv run cloak       # opens a real Chromium window
# log in to LinkedIn / target sites inside the window, then Ctrl-C to quit
```

After that, run **headless** (the default) — no window, no focus stolen, session survives via the persistent profile at `~/.cloak-automation-profile`:

```bash
uv run cloak       # headless launcher on CDP :9222
```

## The loop

1. **Open the target page** in the running CloakBrowser window (logged in, ready to act).
2. **Write a tiny `explore.py`** that attaches over CDP, finds the open tab, and dumps the relevant DOM. Iterate. *humanize off* in explore — it adds delay you don't want when poking around.
3. **Pick selectors**, write `script.py`. *humanize on* in prod — Bézier-curve mouse + per-keystroke typing delays.

## Attach pattern (copy this)

```python
from lib.browser import attach, find_or_new, humanize

def main() -> None:
    with attach() as ctx:                                # CDP attach via lib.browser
        page = find_or_new(ctx, lambda p: "TARGET_DOMAIN" in p.url)
        humanize(page)                                   # ← prod scripts only

        # ... work here ...
```

`attach()` uses `sync_playwright` + `connect_over_cdp(CDP_URL)`, yielding the
first context. `find_or_new` finds a matching tab or opens a new one.
`humanize(page)` calls `cloakbrowser.human.patch_page(page)` — patches the
**local** Playwright objects (mouse/keyboard), not the browser. So every script
that wants stealth typing/clicks must call it after attaching.

## Explore template

```python
import json
from lib.browser import attach, find_or_new

def main() -> None:
    with attach() as ctx:
        page = find_or_new(ctx, lambda p: "TARGET_DOMAIN" in p.url)
        # NO humanize() in explore — just poke at the DOM.
        dump = page.evaluate("""(() => {
          return Array.from(document.querySelectorAll("button, a[role='button']"))
            .map(el => {
              const r = el.getBoundingClientRect();
              return {
                text: (el.textContent || "").trim().slice(0, 60),
                aria: el.getAttribute("aria-label"),
                y: Math.round(r.top),
                visible: r.width > 0 && r.height > 0,
              };
            })
            .filter(b => b.visible && b.y >= 0 && b.y < 800)
            .sort((a, b) => a.y - b.y);
        })()""")
        print(json.dumps(dump, indent=2))
```

Run it, read the output, narrow the selector, repeat. For modals/dropdowns: dump everything inside `[role='dialog']` or `[role='menu']` in **one** evaluate.

## Gotchas

- **Stay on the sync Playwright API.** `lib.browser.attach()` wraps `sync_playwright()`. Mixing `async def` / `await` on sync `Page` / `Locator` objects fails silently or with cryptic errors. Either everything's sync or everything's async — and `cloakbrowser.launch_persistent_context` (used by the launcher) takes sync `*_async` siblings if you ever need it the other way.
- **`cloakbrowser.human.patch_page` is internal** — it takes private `cfg` / `cursor` args. The public entry point is `human.patch_context(ctx, human.resolve_config())`; `lib.browser.humanize(page)` wraps it. Patching once per context covers every page in that context.
- **`humanize=True` on the launcher does NOT propagate over CDP** — the patches monkey-patch local Playwright objects. Tasks that want humanized input must call `humanize(page)` after attach. The launcher itself runs with `humanize=False`; tasks opt in per page.
- **CDP-attached pages have `viewport_size == None`** (Playwright didn't launch the browser, so it never set one). Humanized clicks need a viewport to plot a cursor path, otherwise you get `"Viewport size not available"`. `lib.browser.humanize()` handles this by copying `innerWidth/innerHeight` from the page before patching — if you ever build your own attach helper, replicate that.
- **Never call `page.bring_to_front()`** — CloakBrowser runs in a separate window from the user's daily Chrome; focus-stealing isn't justified, and the human-approval prompts already happen in the terminal where the user is.
- **`page.wait_for_timeout()` triggers reCAPTCHA v3 detection** (per CloakBrowser docs) — prefer `time.sleep()` for any flow that crosses a reCAPTCHA. For non-captcha flows `wait_for_timeout` is fine.
- **Use `page.type()` not `page.fill()` on aggressive sites** so the humanize per-keystroke delay actually fires.
- **`page.goto(..., wait_until="domcontentloaded")` hangs on LinkedIn** (and any SPA with long-poll connections). Use `wait_until="commit"` with a short timeout, then `page.wait_for_function(...)` on something you actually need.
- **`Execution context was destroyed` mid-`evaluate`** — happens when the site does a client-side redirect after your `goto` commits but before your `evaluate` runs. Catch, `wait_for_timeout(2000)`, retry the evaluate once.
- **Pass `page.evaluate` a string IIFE** (`page.evaluate("(() => { ... })()")`), not a Python lambda. The browser context doesn't see your Python helpers.
- **IIFE must end with `})()`** — the trailing `()` actually invokes it. Without it, you serialize the function expression and get `undefined`.
- **Anchor `textContent` is often the whole card** — on LinkedIn people-search, the card-wrapping `<a href="/in/...">` contains name + connection-degree + headline + company + location concatenated. Read the anchor text and regex/substring-match. There are usually two anchors per result (avatar + card); dedupe by handle, keep the longest text blob per handle.
- **Scope to `<main>` for search results** — right-rail "People you may know" suggestions also use `/in/<handle>` links and will pollute your candidate list.
- **LinkedIn profile pages lazy-load below-the-fold sections** (Experience, Education, Skills) and may *unmount* off-screen sections (virtualization). Scroll in ~300 px steps with ~400 ms gaps **before** extracting, and don't scroll back to top.
- **LinkedIn uses Server-Driven UI with `componentkey` attributes** — much more stable than hashed CSS classes. Key patterns: `componentkey*='Topcard'`, `componentkey^='entity-collection-item'`, `componentkey*='profile.skill'` (filter out `-divi` / `-endorser` / `endorsers` variants).
- **High-res profile photo (`crop_800_800`) never appears in any `<img>` tag** — LinkedIn fetches it but doesn't render it. Capture via CDP `Network.requestWillBeSent`:
  ```python
  cdp = page.context.new_cdp_session(page)
  cdp.send("Network.enable")
  urls: list[str] = []
  cdp.on("Network.requestWillBeSent",
         lambda e: e["request"]["url"].count("profile-displayphoto") and urls.append(e["request"]["url"]))
  ```
  URL-rewriting `scale_100_100` → `scale_800_800` does NOT work — the `?t=` token is path-bound.
- **LinkedIn sections lazy-load via IntersectionObserver** — if items don't appear after a full scroll, `section.scrollIntoView({ block: 'center' })` on the specific section and wait again.
- **Always have a fallback to `/in/<slug>/details/{experience,education,skills}/`** — LinkedIn sometimes serves a condensed layout that omits sections inline.
- **Extract all inline sections BEFORE any `/details/` fallback navigation.** If Experience falls back to `/details/experience/` and then you extract Education from `<main>`, you'll get the experience items as "education" because both pages render items under `<main>`. Do inline extracts first, then handle fallbacks per-section.
- **Inline vs. details-page extractors are NOT the same.** Inline must require the section anchor (e.g. `section[componentkey*='EducationTopLevel']`) — never fall back to `<main>` on the profile page, or a different section's items will leak in. The details-page variant uses `<main>` because the dedicated page doesn't wrap items in a TopLevel section.
- **UUID-componentkey fallback also catches LinkedIn's footer.** The `/details/<section>/` pages wrap footer links ("About / Accessibility / Talent Solutions / …") in UUID-keyed components that match `/^[0-9a-f-]{36}$/`. Scope to the first match's `closest("section")` and dedupe by componentkey before mapping items.
- **Profile owner appears in their own mutual-connections search** — always filter out `/in/<self-slug>` when collecting mutual-connection links.
- **First-launch Gatekeeper** is not an issue for the CloakBrowser binary downloaded by `uv run python -m cloakbrowser install` (no quarantine attribute). It *is* an issue if you ever download the binary via browser or curl — strip the quarantine with `xattr -d com.apple.quarantine ...` if so.

## Production script shape

Once selectors are known:
- `with attach() as ctx:` once at the top.
- `humanize(page)` once on the page you'll work with.
- One `page.goto()` per item (reuse the same tab — fastest, lowest memory).
- Prefer `page.get_by_role("button", name="…")` over hashed CSS classes.
- For destructive/irreversible actions, **pause for human approval** via `input(...)` between staging and committing.
- Output a status summary at the end.

See `tasks/linkedin_connect/connect.py` for a reference implementation.
