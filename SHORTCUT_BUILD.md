# Build The Arc Shortcut

This is the practical Shortcuts action list for turning Arc into a working Shortcut.

Best current architecture:

```text
Cloudflare Worker
  -> scrape configured RSS feeds
  -> parse and rank stories
  -> serve /arc.edition.json
iOS Shortcut
  -> Open URLs: Cloudflare Arc app
```

This keeps scraping/parsing on Cloudflare and gives the Shortcut a stable HTTPS URL.

Current live URL:

```text
https://arc-news.oneplus2x69.workers.dev/
```

The Worker generates fresh reader data at:

```text
https://arc-news.oneplus2x69.workers.dev/arc.edition.json
```

Use this as the `ArcURL` variable in Shortcuts.

The older Apple Intelligence flow is still useful as an optional fallback or experiment: gather RSS, ask Apple Intelligence to produce Arc edition JSON, URL-encode that JSON, and open Arc with `?edition=`.

## Requirements

- iPhone with Shortcuts.
- Live Cloudflare Worker URL.
- The text from `arc.config.json` field `apple_intelligence_prompt` only if using the optional Apple Intelligence route.

## Mac-Local Shortcut Name

```text
Open Arc Briefing
```

## Mac-Local Actions

### 1. Core Preview: Scrape, Build Edition, Open Arc

This no-AI core preview is working now. It proves:

```text
local RSS scrape -> parsed Arc edition JSON -> encoded Arc URL -> hosted Arc reader
```

Action: `Run Shell Script`

Shell:

```text
/bin/zsh
```

Input:

```text
None
```

Script:

```sh
python3 /Users/hoanghuuquoc/Downloads/arc-handoff-package/scripts/arc_open_core.py
```

This prints exactly one URL to stdout and opens Arc. The current preview edition is intentionally compact: 3 categories, 2 stories each.

## Apple Intelligence Version

Once the core preview is confirmed, replace the basic edition builder with Apple Intelligence:

### 1. Scrape RSS Locally

Action: `Run Shell Script`

Shell:

```text
/bin/zsh
```

Input:

```text
None
```

Script:

```sh
python3 /Users/hoanghuuquoc/Downloads/arc-handoff-package/scripts/arc_scrape_rss.py >/tmp/arc_scrape_status.txt
cat /Users/hoanghuuquoc/Downloads/arc-handoff-package/arc.ai-input.txt
```

This returns Apple Intelligence-ready text from the current RSS feeds.

### 2. Combine Prompt And Scraped Text

Action: `Text`

Paste:

```text
[contents of shortcut-apple-intelligence-prompt.txt]

Input RSS bundle:
Shortcut Input
```

In Shortcuts, replace `Shortcut Input` with the output from the previous shell action.

### 3. Generate Edition JSON

Action: `Use Model`

Recommended model:

```text
Private Cloud Compute
```

Input:

```text
Text
```

Action: `Get Text from Input`

Action: `Set Variable`

```text
EditionJSON
```

### 4. Validate JSON

Action: `Get Dictionary from Input`

Input:

```text
EditionJSON
```

If this fails, temporarily add `Show Result` after `EditionJSON` to inspect what Apple Intelligence returned.

### 5. Make Hosted Arc URL

Action: `Run Shell Script`

Shell:

```text
/bin/zsh
```

Input:

```text
EditionJSON
```

Script:

```sh
python3 /Users/hoanghuuquoc/Downloads/arc-handoff-package/scripts/arc_make_url.py
```

### 6. Open Arc

Action: `Open URLs`

Input:

```text
Run Shell Script Result
```

## iPhone-Only Shortcut Name

```text
Open Arc Briefing
```

## Actions

### 1. Set Arc URL

Action: `Text`

```text
https://arc-news.oneplus2x69.workers.dev/
```

Action: `Set Variable`

```text
ArcURL
```

### 2. Set AI Prompt

Action: `Text`

Paste the value of `apple_intelligence_prompt` from `arc.config.json`.

Action: `Set Variable`

```text
ArcPrompt
```

### 3. Build RSS Input

Action: `Text`

```text
Generated at: Current Date
Locale: en-US

RSS STORIES
```

Action: `Set Variable`

```text
RSSInput
```

Then add the following block once per source you want in the first version.

Action: `Text`

```text
World | BBC News — World | https://feeds.bbci.co.uk/news/world/rss.xml
```

Action: `Split Text`

Separator:

```text
|
```

Action: `Get Item from List`

Get item 1 as `Category`.

Action: `Get Item from List`

Get item 2 as `SourceName`.

Action: `Get Item from List`

Get item 3 as `FeedURL`.

Action: `Get Contents of URL`

URL:

```text
FeedURL
```

Method:

```text
GET
```

Action: `Text`

```text

CATEGORY: Category
SOURCE: SourceName
URL: FeedURL
RAW RSS:
Contents of URL

---
```

Action: `Add to Variable`

Variable:

```text
RSSInput
```

Repeat this source block for each feed you want. Start with 3 to 5 feeds while testing.

Suggested first feeds:

```text
World | BBC News — World | https://feeds.bbci.co.uk/news/world/rss.xml
Business | BBC News — Business | https://feeds.bbci.co.uk/news/business/rss.xml
Technology | Ars Technica | https://feeds.arstechnica.com/arstechnica/index
Science | NASA — News Releases | https://www.nasa.gov/news-release/feed/
Vietnam | Google News — Vietnam | https://news.google.com/rss/headlines/section/geo/Vietnam?hl=en&gl=VN&ceid=VN%3Aen
```

### 4. Ask Apple Intelligence For Arc JSON

Action: `Text`

```text
ArcPrompt

Input RSS bundle:
RSSInput
```

Action: `Use Model`

Model:

```text
Private Cloud Compute
```

Input:

```text
Text
```

Action: `Get Text from Input`

Action: `Set Variable`

```text
EditionJSON
```

### 5. Validate JSON

Action: `Get Dictionary from Input`

Input:

```text
EditionJSON
```

If this action fails, the model did not return strict JSON. In that case, temporarily add a `Show Result` action after `EditionJSON` to inspect the model output.

### 6. Open Arc

Action: `URL Encode`

Input:

```text
EditionJSON
```

Action: `Text`

```text
ArcURL?edition=URL Encoded Text
```

Action: `Open URLs`

Input:

```text
Text
```

## Testing Order

1. Run with only one feed first.
2. Confirm Arc opens and shows live cards.
3. Add 2 to 4 more feeds.
4. If the URL becomes too long or Safari fails to open it, switch to the large-edition route below.

## Large-Edition Route

Use this only if `?edition=` becomes too large.

The Shortcut should:

1. Get the contents of `index.html` as text.
2. Replace the first `<script>` with:

```html
<script id="arc-edition-data" type="application/json">
EditionJSON
</script>
<script>
```

3. Save the result as:

```text
Arc Today.html
```

4. Open the saved file.

The hosted URL route is more reliable on iPhone, so use this only after the hosted route proves too large.

## Notes

- Do not use `window.Arc.loadEdition(...)` in the Shortcut. That API is for JavaScript-capable wrappers, not normal iOS Shortcuts.
- `Open URLs` with `?edition=` is the simplest iOS Shortcut bridge.
- `Get Dictionary from Input` is the sanity check that prevents Arc from opening with broken model output.
