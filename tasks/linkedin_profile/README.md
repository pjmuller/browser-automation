# linkedin_profile

Scrape a single LinkedIn profile into a markdown file with YAML frontmatter, plus a high-res JPEG of the profile photo.

Pure Playwright over CDP via CloakBrowser — no LLM, no API keys. Walks the profile, the `/details/...` fallbacks, and the mutual-connections page in one tab.

## What it does

For one `https://www.linkedin.com/in/<slug>/` URL:

1. Navigate to the profile (`wait_until="commit"` — LinkedIn long-polls keep DCL from firing).
2. Scroll smoothly (300 px / 400 ms) to trigger lazy-loaded sections.
3. Extract topcard, about, experience, education, skills, mutual connections from `componentkey`-attributed nodes.
4. Fall back to `/in/<slug>/details/experience/`, `/details/education/`, `/details/skills/` if the inline section is the condensed layout.
5. Capture the high-res profile photo (`profile-displayphoto-crop_800_800`) via a CDP `Network.requestWillBeSent` listener — the variant never appears in any `<img>` tag.
6. Write `data/<slug>.md` (markdown + YAML frontmatter) and `data/<slug>.jpg`.

## Run

```bash
uv run cloak                                                 # start (or keep open) CloakBrowser
uv run linkedin-profile https://www.linkedin.com/in/stanalexandru/
```

The output lands in `tasks/linkedin_profile/data/<slug>.{md,jpg}` (gitignored).

## Debugging

```bash
uv run linkedin-profile-explore https://www.linkedin.com/in/stanalexandru/
```

Dumps topcard / about / experience / education / image / button structure as JSON — useful when LinkedIn changes selectors.

## Frontmatter fields

```yaml
name: …
headline: …
location: …
followers: …
connections: …
profile_url: https://www.linkedin.com/in/<slug>/
image: <slug>.jpg
image_url: https://media.licdn.com/dms/image/...
scraped: 2026-05-19T12:34:56+00:00
```
