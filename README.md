# command-center

Irving Insights personal command center — a web dashboard and content tooling hub.

## Content Pipeline

**`content_pipeline.py`** — Daniel Irving's CMS Overseer. Takes a content item from idea to post-ready through four stages: Research → Draft → Editorial Pass → Posting Instructions. Powered by Claude (claude-opus-4-6) via the Anthropic API.

**`pipeline.html`** — Web UI version. Fill in 4 fields, get a fully-constructed Claude prompt with all placeholders replaced. Copy to clipboard and paste into claude.ai.

### Setup

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

### Usage — CLI (runs the full pipeline via API)

```bash
# Interactive — prompts for all 4 inputs
python content_pipeline.py

# Fully specified
python content_pipeline.py \
    --title "Why Camps Beat Apps" \
    --platform LinkedIn \
    --domain "Irving Insights" \
    --notes "Lead with the Camp Sisol formation example"

# Skip saving output to file
python content_pipeline.py --no-save
```

**Platforms:** `LinkedIn` · `Substack` · `X` · `YouTube`
**Domains:** `Irving Insights` · `Book` · `TBK` · `SubSignal` · `Personal`

Output is saved to `outputs/YYYY-MM-DD_<slug>.md`.

### Usage — Web UI (generates prompt for claude.ai)

Open `pipeline.html` in a browser (or click the CMS Overseer card in the command center). Fill in the four fields, click **Generate Prompt**, copy, and paste into claude.ai.

Recent runs are saved in localStorage for quick reloading.

## Other Tools

**`notion_google_sync.py`** — One-way sync from Notion Tasks database to Google Calendar.

### Required environment variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key for content_pipeline.py |
| `NOTION_API_TOKEN` | Notion integration secret |
| `NOTION_TASKS_DB_ID` | 32-character Notion database ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON string for Google service account |
| `DOMAIN_CALENDAR_MAPPING` | JSON mapping of Notion domains → Calendar IDs |
