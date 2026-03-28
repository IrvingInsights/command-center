# CMS Pipeline Automation — Setup Guide

This guide sets up the Google Apps Script that automatically runs your 4-stage content
pipeline whenever you mark a Notion Content Calendar item as "Ready to Run."

No coding required. Follow the steps in order.

---

## What you need before starting

- Your **Anthropic API key** (`sk-ant-...`) from [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
- Your **Notion integration token** (`secret_...`) — the same one you use in the pipeline app
- The Notion integration must already be **connected to both databases**:
  - *SignalWorks — Content Items* (it already is if you've used the PWA)
  - *Content Calendar* — open that database in Notion → `...` menu → Connections → add your integration

---

## Step 1 — Open Google Apps Script

1. Go to [script.google.com](https://script.google.com)
2. Click **New project**
3. Name it something like `CMS Pipeline Automation`

---

## Step 2 — Paste the script

1. Delete everything in the editor (Ctrl+A, Delete)
2. Open the file `content_automation.gs` from the `command-center` repo
3. Copy the entire contents and paste into the Apps Script editor
4. Click the **Save** icon (or Ctrl+S)

---

## Step 3 — Add your API keys

Your keys are stored securely in Apps Script's Project Properties — they are never
visible in the code or in GitHub.

1. Click the **gear icon** (Project Settings) in the left sidebar
2. Scroll down to **Script Properties**
3. Click **Add script property** and add these two rows:

| Property name       | Value                  |
|---------------------|------------------------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` (your key) |
| `NOTION_API_TOKEN`  | `secret_...` (your token) |

4. Click **Save script properties**

---

## Step 4 — Test with a dry run (no writes)

Before enabling automation, confirm the script can read your Notion databases.

1. In the Apps Script editor, open the **function dropdown** at the top (it probably says `myFunction` or `runPipeline`)
2. Select **`dryRun`**
3. Click the **Run** button (▶)
4. The first time, Google will ask for permissions — click **Review permissions** → **Allow**
5. Click **View → Logs** (or press Ctrl+Enter) to see the output

**What you should see:**
- If no items have Status = "Ready to Run": `No items found with Status = "Ready to Run"` — that's fine, it means the connection works
- If there are ready items: a list of titles, platforms, and domains
- If you see an error about authentication: double-check your Notion token in Script Properties and confirm the integration is connected to the Content Calendar database

---

## Step 5 — Set the 30-minute trigger

1. In the function dropdown, select **`createTrigger`**
2. Click **Run**
3. Check View → Logs — you should see: `Trigger created: runPipeline will run every 30 minutes`

To confirm: click the **clock icon** (Triggers) in the left sidebar. You should see
`runPipeline` listed with a "Time-driven / Every 30 minutes" schedule.

---

## Step 6 — Test a live run

1. Open your **Notion Content Calendar**
2. Find any item (or create a test one) and set its **Status → "Ready to Run"**
3. Back in Apps Script, select function **`runPipeline`** and click **Run**
4. Watch View → Logs — you should see it progress through each step
5. Check Notion: the Calendar item should now show Status = "In Review", and a new
   page should appear in *SignalWorks — Content Items* with the full pipeline output

---

## How to trigger a pipeline run going forward

That's it — just set any Content Calendar item's **Status to "Ready to Run"** in Notion.
The script checks every 30 minutes and picks it up automatically.

You don't need to do anything else. Within 30 minutes, the item will:
1. Be processed through all 4 stages (Research → Draft → Editorial → Posting Instructions)
2. Appear as a new page in *SignalWorks — Content Items* with the full output
3. Get a comment: "Pipeline complete. Open this page to review the draft."
4. Have its Calendar Status updated to "In Review"

When you're happy with the draft, open the SignalWorks page and check **Human Approved**.

---

## Pausing the automation

To pause: run function **`deleteTriggers`**
To resume: run function **`createTrigger`**

---

## If something goes wrong

**View → Logs** shows the full execution history. Common issues:

| Error in logs | Fix |
|---|---|
| `Missing API keys` | Re-check Step 3 — property names must match exactly |
| `Notion API 401` | Your Notion token is wrong or expired — replace it in Script Properties |
| `Notion API 404 on database query` | The integration isn't connected to the Content Calendar — see "What you need before starting" |
| `Anthropic API 401` | Your Anthropic key is wrong or has no credits |
| `Timeout` or very slow | The Anthropic response is taking too long. Open `content_automation.gs`, find `ANTHROPIC_MAX_TOKENS`, change `8000` to `4000`, and save |
| Item stuck on "Ready to Run" | Check logs for an error on that item. Fix the issue and it will retry next cycle |

---

## Files in this repo

| File | Purpose |
|---|---|
| `content_automation.gs` | The Google Apps Script — paste into script.google.com |
| `pipeline.html` | Browser PWA — open directly or via Netlify/GitHub Pages |
| `pipeline_server.py` | Optional Flask server for PC-based streaming |
| `content_pipeline.py` | CLI version of the pipeline |
