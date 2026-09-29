# linkedin_connect

Send personalized LinkedIn connection requests from a CSV, fully autonomously.

Pure Playwright over CDP — no LLM, no API keys. Uses LinkedIn's `preload/custom-invite/?vanityName=…` deeplink to skip the Follow / More menu dance entirely.

## What it does

For each row in `profiles.csv`:
1. Navigate to `https://www.linkedin.com/preload/custom-invite/?vanityName={slug}` (slug extracted from the profile URL).
2. Wait for the invitation modal; click **Add a note**.
3. Fill the textarea (`#custom-message`) with the message (newlines preserved).
4. Click **Send invitation** and wait for the modal to close.
5. Sleep a random 5–15s before the next row; every 10th row sleep 45–90s.

The run is autonomous — no per-row confirmation. To abort, Ctrl-C the process and re-run later with a trimmed CSV.

Failure handling:
- Invitation modal missing within 8s → `skipped:no_invite_dialog` (already connected, can't invite, etc.).
- Page handle goes stale ("Target page, context or browser has been closed") → script auto-reacquires a LinkedIn tab from the live CDP context and retries that row once.
- Empty `url` rows are silently dropped at load time.
- Messages > 300 chars are flagged in the preflight summary and return `error:message_too_long`.

## Run

```bash
uv run cloak                      # start (or keep open) the CloakBrowser
uv run linkedin-connect          # in another terminal
```

Point at a different CSV:
```bash
uv run linkedin-connect path/to/other.csv
```

## CSV format

```csv
url,message
https://www.linkedin.com/in/someone,"Hi Someone, short personal note."
```

- Messages must be ≤ 300 characters (LinkedIn invitation limit).
- Quote messages containing commas.
- `profiles.csv` is gitignored; `profiles.example.csv` is the template.

## Lessons learned (2026-05 batch of 29)

- **CSV columns must be exactly `url,message`.** Spreadsheet exports often have `LinkedIn URL,LinkedIn Connect Message` — rename before running. `csv.DictReader` strips enclosing quotes and preserves multi-line cells, so `\n\n` between paragraphs survives into `textarea.fill()`.
- **Always run unbuffered.** When stdout is redirected to a file, `print()` buffers until the process exits. Use `PYTHONUNBUFFERED=1` or `print(..., flush=True)` (the script now does the latter).
- **Page handles go stale around ~25 rows.** LinkedIn occasionally replaces or closes the tab mid-session. The "Target page, context or browser has been closed" error is recoverable — the browser is still alive over CDP, we just need a fresh `Page` from `ctx.pages`. The script now auto-recovers once per failure.
- **Pacing seemed safe.** 5–15s jitter between rows + 45–90s every 10th gave 29 attempts with zero LinkedIn-side throttling. Probably the floor for this volume; don't go faster without observing first.
- **`skipped:no_invite_dialog` is normal.** ~3% rate is healthy — those targets are usually already connected or not invitable. Investigate the profile in the browser before assuming a script bug.

## Lessons learned (2026-05-19 batch of 35)

- **`humanize()` is partially broken on cloakbrowser 0.3.28.** Two distinct failures showed up:
  1. The patched `goto` (`_patch_frames_sync.<locals>._frame_aware_goto`) has the wrong signature — *every* `page.goto(url, wait_until=...)` raises `takes 1 positional argument but 2 were given`. Hard blocker on any task that navigates.
  2. The patched typing produced scrambled characters in the very first row's `textarea.fill()` (Gerard), though the same code typed cleanly across the 29-row 2026-05 batch and across the remaining 30 rows of this batch once `humanize` was off. So the typing patch is *flaky*, not dead — possibly tied to a freshly-attached page that hasn't fully settled.
  Workaround used today: drop the `humanize(page)` call inside `reacquire_page()` so `linkedin_connect` runs on plain Playwright. LinkedIn isn't fingerprint-gated for a logged-in session, so this is safe for this task. **Do not strip humanize globally** — other tasks (anything hitting Cloudflare/reCAPTCHA) still need it, and the typing patch was fine on the previous batch. Re-evaluate after the next cloakbrowser release; consider a `humanize(page, wait_for_settle=True)` kind of guard for the typing patch.
- **Stuck-dialog cascade poisons all subsequent rows.** When one row leaves a modal open (we hit this after a partial send), the next row's `page.get_by_role("dialog")` matches *two* elements and every `Locator.wait_for` throws `strict mode violation: get_by_role("dialog") resolved to 2 elements`. The existing recovery only catches `"target page, context or browser has been closed"`, so strict-mode errors propagate untouched and the rest of the batch fails. Fixes worth trying: scope the locator (`page.get_by_role("dialog").last` or filter on the invitation heading), and add a "close stray dialogs / `page.reload()`" branch to the recovery loop.
- **"Add a note" / "Send" click timeouts ≈ 30s usually mean "can't invite this profile".** Today both `philippwolf` (already connected, probably) and `pieterjanmuller` (the operator's own profile) hit 30 s `Locator.click` timeouts. Worth a preflight check that skips your own vanity slug, plus a faster fail than 30 s — e.g. probe for the button with a 5 s `wait_for` before clicking.
- **A failed row may still have sent.** If the `message staged: "..."` line printed before the error, `textarea.fill()` and the "Send invitation" click already happened; the error is in the post-send dialog-close check. Verify on LinkedIn's Sent Invitations before re-running these rows, or you'll spam the same person.
- **Relative CSV paths resolve against `tasks/linkedin_connect/`, not cwd.** `uv run linkedin-connect tasks/linkedin_connect/foo.csv` looks for `tasks/linkedin_connect/tasks/linkedin_connect/foo.csv` and crashes with `FileNotFoundError`. Pass just the basename (`uv run linkedin-connect foo.csv`) or an absolute path.

## Debugging

`tasks/linkedin_connect/explore.py` is a standalone script that exercises the same flow against a single profile and dumps the dialog/textarea/button structure. Useful when LinkedIn changes selectors:

```bash
uv run linkedin-connect-explore stanalexandru   # vanity name as arg
```
