const DEFAULT_MAX_CATEGORIES = 12;
const DEFAULT_MAX_PER_CATEGORY = 3;
const EDITION_CACHE_VERSION = "images-v1";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/arc.edition.json") {
      return handleEdition(request, env, ctx);
    }

    if (url.pathname === "/health") {
      return json({ ok: true, generated_at: new Date().toISOString() });
    }

    return env.ASSETS.fetch(request);
  },
};

async function handleEdition(request, env, ctx) {
  const cache = caches.default;
  const cacheKey = new Request(new URL(`/arc.edition.json?cache=${EDITION_CACHE_VERSION}`, request.url), request);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const config = await loadConfig(request, env);
  const edition = await buildEdition(config);
  const response = json(edition, {
    "Cache-Control": `public, max-age=${Number(env.EDITION_CACHE_SECONDS || 900)}`,
  });
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

async function loadConfig(request, env) {
  const configUrl = new URL("/arc.config.json", request.url);
  const response = await env.ASSETS.fetch(new Request(configUrl, request));
  if (!response.ok) throw new Error("arc.config.json not found");
  return response.json();
}

async function buildEdition(config) {
  const settings = config.settings || {};
  const maxPerFeed = Number(settings.maximum_items_per_feed || 10);
  const maxPerCategory = Number(settings.maximum_stories_per_category || DEFAULT_MAX_PER_CATEGORY);
  const lookbackHours = Number(settings.lookback_hours || 30);
  const cutoff = Date.now() - lookbackHours * 60 * 60 * 1000;
  const categories = [];

  for (const category of config.categories || []) {
    if (category.enabled === false) continue;
    const stories = [];
    const sources = category.sources || [];

    for (const source of sources) {
      try {
        const feed = await fetchFeed(source.url);
        const items = parseFeed(feed, category.name, source).slice(0, maxPerFeed);
        for (const item of items) {
          if (item.published_at && safeTime(item.published_at) < cutoff) continue;
          stories.push(item);
        }
      } catch (error) {
        console.warn(`Feed failed: ${category.name} / ${source.name}: ${error.message}`);
      }
    }

    const selected = dedupe(stories)
      .sort(selectionSort)
      .slice(0, maxPerCategory)
      .map(toStory);

    if (selected.length) {
      categories.push({ name: category.name, stories: selected });
    }

    if (categories.length >= DEFAULT_MAX_CATEGORIES) break;
  }

  return {
    generated_at: new Date().toISOString(),
    locale: settings.locale || "en-US",
    categories,
  };
}

async function fetchFeed(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "ArcNewsWorker/1.0 (+https://arc-news.workers.dev)",
      Accept: "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    },
    cf: { cacheTtl: 600, cacheEverything: true },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}

function parseFeed(xml, category, source) {
  const blocks = [
    ...matches(xml, /<item\b[\s\S]*?<\/item>/gi),
    ...matches(xml, /<entry\b[\s\S]*?<\/entry>/gi),
  ];

  return blocks
    .map((block) => {
      const headline = normalizeTitle(readTag(block, "title"));
      const url = readTag(block, "link") || readLinkHref(block);
      const summary = clean(readTag(block, "description") || readTag(block, "summary") || readTag(block, "content:encoded") || readTag(block, "content"));
      const dateText = readTag(block, "pubDate") || readTag(block, "published") || readTag(block, "updated") || readTag(block, "dc:date");
      const publishedAt = parseDate(dateText);
      const imageUrl = readImageUrl(block);
      if (!headline) return null;
      return {
        id: stableId(`${category}|${source.name}|${url || headline}`),
        category,
        source: source.name || "",
        source_type: source.type || "",
        headline,
        summary,
        url,
        published_at: publishedAt,
        image_url: imageUrl,
        image_alt: imageUrl ? headline : null,
      };
    })
    .filter(Boolean);
}

function toStory(item) {
  const summary = clamp(item.summary || item.headline, 160);
  const briefing = clamp(item.summary || item.headline, 320);
  return {
    id: `${slug(item.category)}-${slug(item.headline)}`,
    headline: item.headline,
    summary,
    briefing,
    publisher: item.source,
    published_at: item.published_at,
    reading_minutes: 1,
    url: item.url,
    image_url: item.image_url,
    image_alt: item.image_alt,
    topics: [],
    developing: false,
    sources: item.url ? [{ publisher: item.source, url: item.url }] : [],
  };
}

function selectionSort(a, b) {
  const rank = { primary: 0, publisher: 1, aggregator: 2 };
  const ar = rank[a.source_type] ?? 3;
  const br = rank[b.source_type] ?? 3;
  if (ar !== br) return ar - br;
  return safeTime(b.published_at) - safeTime(a.published_at);
}

function parseDate(value) {
  const time = safeTime(clean(value));
  return time ? new Date(time).toISOString() : null;
}

function safeTime(value) {
  if (!value) return 0;
  const time = Date.parse(value);
  return Number.isNaN(time) ? 0 : time;
}

function dedupe(items) {
  const seen = new Set();
  const out = [];
  for (const item of items) {
    const key = item.headline.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(/\s+/).slice(0, 12).join(" ");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

function readTag(block, tag) {
  const escaped = tag.replace(":", "\\:");
  const re = new RegExp(`<${escaped}\\b[^>]*>([\\s\\S]*?)<\\/${escaped}>`, "i");
  const found = block.match(re);
  return found ? clean(found[1]) : "";
}

function readLinkHref(block) {
  const found = block.match(/<link\b[^>]*href=["']([^"']+)["'][^>]*>/i);
  return found ? clean(found[1]) : "";
}

function readImageUrl(block) {
  const candidates = [
    readTagAttr(block, "media:content", "url"),
    readTagAttr(block, "media:thumbnail", "url"),
    readTagAttr(block, "image", "url"),
    readTagAttr(block, "itunes:image", "href"),
    readTagAttr(block, "enclosure", "url", /type=["']image\//i),
    readTagAttr(block, "img", "src"),
  ].filter(Boolean);
  const image = candidates.find((candidate) => !/rss-pixel|tracking|\/pixel[.?/]/i.test(candidate));
  return image ? normalizeImageUrl(image) : null;
}

function readTagAttr(block, tag, attr, requiredPattern = null) {
  const escaped = tag.replace(":", "\\:");
  const tagRe = new RegExp(`<${escaped}\\b[^>]*>`, "gi");
  for (const [rawTag] of block.matchAll(tagRe)) {
    if (requiredPattern && !requiredPattern.test(rawTag)) continue;
    const attrRe = new RegExp(`${attr}=["']([^"']+)["']`, "i");
    const found = rawTag.match(attrRe);
    if (found) return clean(found[1]);
  }
  return "";
}

function normalizeImageUrl(url) {
  return clean(url)
    .replace(/([?&])width=\d+/i, "$1width=1200")
    .replace(/\/standard\/240\//i, "/standard/1024/");
}

function clean(value = "") {
  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeTitle(value) {
  return clean(value).replace(/\s[-|]\s[^-|]{2,80}$/, "").trim();
}

function clamp(value, length) {
  const cleanValue = clean(value);
  return cleanValue.length > length ? `${cleanValue.slice(0, length - 1).trim()}…` : cleanValue;
}

function slug(value) {
  return clean(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 90) || "story";
}

function stableId(value) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0).toString(16);
}

function matches(value, regex) {
  return Array.from(value.matchAll(regex), (match) => match[0]);
}

function json(data, headers = {}) {
  return new Response(JSON.stringify(data, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...headers,
    },
  });
}
