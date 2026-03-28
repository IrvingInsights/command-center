/**
 * content_automation.gs
 * ======================
 * Daniel Irving's CMS Pipeline Automation — Google Apps Script
 *
 * WHAT THIS DOES:
 *   Every 30 minutes, checks the Notion Content Calendar for items with
 *   Status = "Ready to Run". For each one, runs the full 4-stage content
 *   pipeline via the Anthropic API, saves the output to SignalWorks Content
 *   Items, posts a review comment, and flips the Calendar item to "In Review".
 *
 * ─── SETUP (do this once) ──────────────────────────────────────────────────
 *
 *  1. PASTE this file into Google Apps Script (script.google.com → New project)
 *
 *  2. ADD API KEYS:
 *     Project Settings (gear icon) → Script Properties → Add a row:
 *       Property: ANTHROPIC_API_KEY   Value: sk-ant-...
 *       Property: NOTION_API_TOKEN    Value: secret_...
 *
 *  3. TEST FIRST (read-only, no writes):
 *     Run menu → Run function → dryRun
 *     Check View → Logs to see what items would be processed.
 *     Fix any permission errors before enabling the trigger.
 *
 *  4. SET THE TRIGGER (after dryRun passes):
 *     Run menu → Run function → createTrigger
 *     OR manually: Triggers (clock icon) → Add Trigger →
 *       Function: runPipeline | Time-driven | Minutes timer | Every 30 minutes
 *
 *  5. TEST A LIVE RUN:
 *     Set one Notion Calendar item Status → "Ready to Run"
 *     Run menu → Run function → runPipeline
 *     Check View → Logs to confirm it processed. Check Notion for the new page.
 *
 *  6. PAUSE AUTOMATION:
 *     Run menu → Run function → deleteTriggers
 *
 * ─── TIMEOUT NOTE ──────────────────────────────────────────────────────────
 *   Apps Script's URL fetch has a ~60 second deadline. Generating 8,000 tokens
 *   from claude-opus-4-6 takes 60–120 seconds and MAY time out. If you see
 *   "Timeout" errors in the logs, lower ANTHROPIC_MAX_TOKENS to 4000. The
 *   pipeline output will be shorter but the four stages will still complete.
 * ───────────────────────────────────────────────────────────────────────────
 */

// ─── Configuration ──────────────────────────────────────────────────────────

var CONTENT_CALENDAR_DB = '1cf41623-f9ca-80d3-ab77-f010748efaa2';
var SIGNALWORKS_DB      = '0a6ba029-ce7b-403e-8212-ad94aa3b396f';
var NOTION_VERSION      = '2022-06-28';
var ANTHROPIC_MODEL     = 'claude-opus-4-6';
var ANTHROPIC_MAX_TOKENS = 8000;  // Lower to 4000 if you see timeout errors
var NOTION_BASE         = 'https://api.notion.com/v1';
var ANTHROPIC_URL       = 'https://api.anthropic.com/v1/messages';

var PLATFORM_CHANNELS = {
  'LinkedIn': ['LinkedIn'],
  'Substack': ['Substack'],
  'X':        ['X'],
  'YouTube':  ['YouTube']
};

// ─── Prompts ─────────────────────────────────────────────────────────────────

var SYSTEM_PROMPT = [
  "You are Daniel Irving's CMS Overseer for a single content pipeline run.",
  "Your job is to take one content item from idea to post-ready in this session —",
  "research it, draft it, edit it, and hand off a clean posting instruction at the end.",
  "",
  "Do not ask for clarification unless something is genuinely ambiguous.",
  "Make reasonable decisions and flag them.",
  "Move through all stages sequentially and show your work at each stage before proceeding."
].join("\n");

function buildUserMessage_(title, platform, domain, notes) {
  return [
    "CONTENT ITEM:",
    "- Title/Idea: " + title,
    "- Platform: " + platform,
    "- Domain: " + domain,
    "- Notes: " + notes,
    "",
    "---",
    "",
    "DANIEL'S IDENTITY (do not ask — this is fixed context):",
    "- Principal Consultant, Irving Insights Consulting — operational strategy and values-based planning for mission-driven nonprofits",
    "- Author-in-progress: \"A Human Childhood in the Era of AI\" — experiential education, formation theory, AI's impact on childhood",
    "- 30+ years in camp-based experiential education, 12 as Camp Sisol director",
    "- Authorial stance: witness/practitioner — not pundit, not policy advocate",
    "- Voice models: Scott Galloway (direct, provokes thought) meets bell hooks (grounded, relational, honest)",
    "- Philosophy: skeptical of tech solutionism; believes human formation > digital optimization",
    "- Avoid: buzzwords, listicles, \"In today's world\", \"As we navigate\", corporate hedging, AI-sounding prose",
    "",
    "---",
    "",
    "## STAGE 1 — RESEARCH",
    "Research the topic. Produce a Research Brief with:",
    "1. Key Findings — 3–5 bullets of what's true, current, and relevant",
    "2. Best Angles for Daniel — 3 numbered angles ranked by fit with his voice and authority",
    "3. Anchor — the single best story, example, or statistic to build around",
    "4. Sources — any links worth citing",
    "5. Recommended Angle — which of the 3 and why (1 sentence)",
    "Then say: \"Research complete. Proceeding to draft.\"",
    "",
    "## STAGE 2 — DRAFT",
    "Write a complete first draft using the recommended angle.",
    "Platform specs:",
    "- LinkedIn: 150–300 words. No headers. Paragraph breaks every 2–3 lines. End with one question or reflection. No hashtags yet.",
    "- Substack: 600–1,200 words. Open with a personal scene. 3 sections. Reflective close.",
    "- X thread: 6–9 tweets. Hook under 200 chars. Number them (1/, 2/, etc.).",
    "- YouTube script: 800–1,500 words. Conversational. Open with a question. Two [PAUSE] markers.",
    "Write the full draft. Do not truncate. Then say: \"Draft complete. Proceeding to editorial pass.\"",
    "",
    "## STAGE 3 — EDITORIAL PASS",
    "Fix directly (do not just flag):",
    "1. Hook — does the first sentence earn the second? Rewrite if not.",
    "2. Voice — cut or rewrite any AI-sounding phrases.",
    "3. Specificity — at least one concrete detail, story, or number. Add one if missing.",
    "4. Length — cut anything not earning its place.",
    "5. Ending — must land with a point of view.",
    "6. Platform fit — adjust format/length if needed.",
    "Output the final polished version in full. Below it: 2-sentence editorial note (what changed and why).",
    "Suggest up to 3 hashtags for LinkedIn or X only.",
    "Then say: \"Final copy ready. Proceeding to posting instructions.\"",
    "",
    "## STAGE 4 — POSTING INSTRUCTIONS",
    "Output a clean posting block:",
    "---",
    "POSTING INSTRUCTIONS",
    "Platform: " + platform,
    "Action: Navigate to the URL below, open the composer, paste the final copy exactly as written.",
    "",
    "Platform URLs:",
    "- LinkedIn: https://www.linkedin.com/feed/ → click \"Start a post\"",
    "- Substack: https://substack.com/publish/post/new",
    "- X / Twitter: https://x.com/compose/tweet",
    "- YouTube: https://studio.youtube.com/",
    "",
    "Hashtags to append (LinkedIn/X only): [list or \"none\"]",
    "Visibility: Public",
    "",
    "After posting:",
    "1. Copy the URL of the published post",
    "2. Log it in Notion: " + title + " → Status: Published, Post URL: [paste]",
    "---",
    "Session complete."
  ].join("\n");
}

// ─── Public functions ────────────────────────────────────────────────────────

/**
 * Main entry point. Called by the time trigger every 30 minutes.
 * Processes all "Ready to Run" items in the Content Calendar.
 */
function runPipeline() {
  var props        = PropertiesService.getScriptProperties();
  var anthropicKey = props.getProperty('ANTHROPIC_API_KEY');
  var notionToken  = props.getProperty('NOTION_API_TOKEN');

  if (!anthropicKey || !notionToken) {
    Logger.log('ERROR: Missing API keys. Open Project Settings → Script Properties and add ' +
               'ANTHROPIC_API_KEY and NOTION_API_TOKEN.');
    return;
  }

  var items = getReadyItems_(notionToken);
  if (!items.length) {
    // Silent exit — nothing to do
    return;
  }

  Logger.log('Found ' + items.length + ' item(s) with Status = "Ready to Run".');

  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    try {
      processItem_(item, anthropicKey, notionToken);
    } catch (e) {
      // Log and continue — don't let one failure block the rest
      Logger.log('ERROR processing "' + item.title + '": ' + e.toString());
    }
  }

  Logger.log('runPipeline complete.');
}

/**
 * Dry run — read-only. Lists all "Ready to Run" items and what would happen.
 * No writes to Notion, no Anthropic API calls. Run this first to test credentials.
 */
function dryRun() {
  var props       = PropertiesService.getScriptProperties();
  var notionToken = props.getProperty('NOTION_API_TOKEN');

  if (!notionToken) {
    Logger.log('ERROR: NOTION_API_TOKEN not set in Script Properties.');
    return;
  }

  Logger.log('=== DRY RUN (read-only) ===');

  var items = getReadyItems_(notionToken);

  if (!items.length) {
    Logger.log('No items found with Status = "Ready to Run" in the Content Calendar.');
    Logger.log('To trigger a run: open a Notion Content Calendar item and set Status → "Ready to Run".');
    return;
  }

  Logger.log('Found ' + items.length + ' item(s) that would be processed:');
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    Logger.log('');
    Logger.log('  [' + (i + 1) + '] ' + item.title);
    Logger.log('       Platform : ' + item.platform);
    Logger.log('       Domain   : ' + item.domain);
    Logger.log('       Notes    : ' + (item.notes.length > 80 ? item.notes.slice(0, 80) + '…' : item.notes));
    Logger.log('       Page ID  : ' + item.id);
  }
  Logger.log('');
  Logger.log('No writes performed. Run runPipeline() when ready to process for real.');
}

/**
 * Creates the 30-minute time-based trigger for runPipeline.
 * Run once after setup. Removes any existing runPipeline triggers first.
 */
function createTrigger() {
  // Remove existing triggers to avoid duplicates
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'runPipeline') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }

  ScriptApp.newTrigger('runPipeline')
    .timeBased()
    .everyMinutes(30)
    .create();

  Logger.log('Trigger created: runPipeline will run every 30 minutes.');
  Logger.log('To pause: run deleteTriggers().');
}

/**
 * Removes all runPipeline triggers. Use to pause the automation.
 */
function deleteTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  var removed  = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'runPipeline') {
      ScriptApp.deleteTrigger(triggers[i]);
      removed++;
    }
  }
  Logger.log('Removed ' + removed + ' trigger(s). Automation is now paused.');
}

// ─── Internal pipeline steps ─────────────────────────────────────────────────

function processItem_(item, anthropicKey, notionToken) {
  Logger.log('--- Processing: "' + item.title + '" [' + item.platform + '] ---');

  // Step 1: Run the 4-stage pipeline via Anthropic
  Logger.log('  Calling Anthropic API…');
  var output = callAnthropicPipeline_(item, anthropicKey);
  Logger.log('  Pipeline output: ' + output.length + ' characters.');

  // Step 2: Save to SignalWorks Content Items
  Logger.log('  Creating SignalWorks page…');
  var newPageId = createSignalWorksPage_(item, output, notionToken);
  Logger.log('  Created page: ' + newPageId);

  // Step 3: Post completion comment
  Logger.log('  Posting completion comment…');
  postCompletionComment_(newPageId, notionToken);

  // Step 4: Update Content Calendar status
  Logger.log('  Updating Calendar status → "In Review"…');
  updateCalendarStatus_(item.id, 'In Review', notionToken);

  Logger.log('  Done: "' + item.title + '"');
}

function getReadyItems_(notionToken) {
  var response = notionRequest_(
    'POST',
    '/databases/' + CONTENT_CALENDAR_DB + '/query',
    notionToken,
    {
      filter: {
        property: 'Status',
        select: { equals: 'Ready to Run' }
      }
    }
  );

  var results = response.results || [];
  var items   = [];

  for (var i = 0; i < results.length; i++) {
    var page  = results[i];
    var props = page.properties;
    var title = richTextToString_(props['Title'] && props['Title'].title);

    if (!title) continue; // skip untitled rows

    items.push({
      id:       page.id,
      title:    title,
      platform: (props['Platform'] && props['Platform'].select) ? props['Platform'].select.name : 'LinkedIn',
      domain:   (props['Domain']   && props['Domain'].select)   ? props['Domain'].select.name   : 'Irving Insights',
      notes:    richTextToString_(props['Notes'] && props['Notes'].rich_text) || 'none'
    });
  }

  return items;
}

function callAnthropicPipeline_(item, apiKey) {
  var payload = {
    model:      ANTHROPIC_MODEL,
    max_tokens: ANTHROPIC_MAX_TOKENS,
    system:     SYSTEM_PROMPT,
    messages:   [{ role: 'user', content: buildUserMessage_(item.title, item.platform, item.domain, item.notes) }]
  };

  var options = {
    method:          'post',
    contentType:     'application/json',
    headers: {
      'x-api-key':          apiKey,
      'anthropic-version':  '2023-06-01'
    },
    payload:            JSON.stringify(payload),
    muteHttpExceptions: true
  };

  var response = UrlFetchApp.fetch(ANTHROPIC_URL, options);
  var code     = response.getResponseCode();
  var body;

  try {
    body = JSON.parse(response.getContentText());
  } catch (e) {
    throw new Error('Anthropic returned non-JSON (code ' + code + '): ' + response.getContentText().slice(0, 200));
  }

  if (code !== 200) {
    var msg = (body.error && body.error.message) ? body.error.message : response.getContentText().slice(0, 300);
    throw new Error('Anthropic API error ' + code + ': ' + msg);
  }

  // Collect all text blocks (skip thinking blocks if any)
  var content    = body.content || [];
  var textBlocks = content.filter(function(b) { return b.type === 'text'; });

  if (!textBlocks.length) {
    throw new Error('Anthropic response had no text content. Full response: ' + JSON.stringify(body).slice(0, 300));
  }

  return textBlocks.map(function(b) { return b.text; }).join('');
}

function createSignalWorksPage_(item, output, notionToken) {
  var channels = (PLATFORM_CHANNELS[item.platform] || [item.platform]).map(function(n) {
    return { name: n };
  });

  var response = notionRequest_(
    'POST',
    '/pages',
    notionToken,
    {
      parent: { database_id: SIGNALWORKS_DB },
      properties: {
        'Content Item':   { title:        [{ text: { content: item.title } }] },
        'Stage':          { select:        { name: 'Drafting' } },
        'Master Copy':    { rich_text:     chunkRichText_(output) },
        'Notes':          { rich_text:     chunkRichText_(item.notes === 'none' ? '' : item.notes) },
        'Channels':       { multi_select:  channels },
        'Human Approved': { checkbox:      false }
      }
    }
  );

  return response.id;
}

function postCompletionComment_(pageId, notionToken) {
  notionRequest_(
    'POST',
    '/comments',
    notionToken,
    {
      parent:    { page_id: pageId },
      rich_text: [{ text: { content: 'Pipeline complete. Open this page to review the draft. Check Human Approved when ready to post.' } }]
    }
  );
}

function updateCalendarStatus_(pageId, status, notionToken) {
  notionRequest_(
    'PATCH',
    '/pages/' + pageId,
    notionToken,
    {
      properties: {
        'Status': { select: { name: status } }
      }
    }
  );
}

// ─── Notion API helpers ───────────────────────────────────────────────────────

function notionRequest_(method, path, token, body) {
  var options = {
    method:             method.toLowerCase(),
    contentType:        'application/json',
    headers: {
      'Authorization':  'Bearer ' + token,
      'Notion-Version': NOTION_VERSION
    },
    muteHttpExceptions: true
  };

  if (body) {
    options.payload = JSON.stringify(body);
  }

  var response = UrlFetchApp.fetch(NOTION_BASE + path, options);
  var code     = response.getResponseCode();
  var parsed;

  try {
    parsed = JSON.parse(response.getContentText());
  } catch (e) {
    throw new Error('Notion returned non-JSON (code ' + code + '): ' + response.getContentText().slice(0, 200));
  }

  if (code < 200 || code >= 300) {
    var msg = parsed.message || response.getContentText().slice(0, 300);
    throw new Error('Notion API ' + code + ' [' + method + ' ' + path + ']: ' + msg);
  }

  return parsed;
}

/**
 * Splits text into 1999-character chunks for Notion rich_text properties.
 * Notion enforces a 2000-character limit per rich_text element.
 */
function chunkRichText_(text) {
  if (!text) return [{ text: { content: '' } }];
  var chunks = [];
  for (var i = 0; i < text.length; i += 1999) {
    chunks.push({ text: { content: text.slice(i, i + 1999) } });
  }
  return chunks;
}

/** Joins an array of Notion rich_text objects into a plain string. */
function richTextToString_(arr) {
  if (!arr || !arr.length) return '';
  return arr.map(function(t) { return t.plain_text || ''; }).join('');
}
