# linkedin_connect

Send personalized LinkedIn connection requests from a CSV, with a human approval gate before each send.

Pure Playwright over CDP — no LLM, no API keys. Uses LinkedIn's `preload/custom-invite/?vanityName=…` deeplink to skip the Follow / More menu dance entirely.

## What it does

For each row in `profiles.csv`:
1. Navigate to `https://www.linkedin.com/preload/custom-invite/?vanityName={slug}` (slug extracted from the profile URL).
2. Wait for the invitation modal; click **Add a note**.
3. Fill the textarea (`#custom-message`) with your personalized message.
4. **Pause** — `ENTER` to send, `s` to skip, `q` to quit.
5. On send, click **Send invitation** and wait for the modal to close.

If the invitation modal doesn't appear within 8s (already connected, can't invite, etc.), the row is skipped.

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

## Debugging

`tasks/linkedin_connect/explore.py` is a standalone script that exercises the same flow against a single profile and dumps the dialog/textarea/button structure. Useful when LinkedIn changes selectors:

```bash
uv run linkedin-connect-explore stanalexandru   # vanity name as arg
```
