---
name: rewrite-neighbourhood-pages
description: >
  Full workflow for creating new neighbourhood pages OR rewriting existing ones
  for anukabli.com — Anu Kabli's real estate website. Use this skill whenever
  the user says "rewrite [page]", "create a page for [neighbourhood]", "update
  the copy on", "batch rewrite", or mentions improving conversion on the site.
  Also triggers for: "new neighbourhood page", "add [community] to the site",
  "the [page] needs better copy", "make the pages more marketing-focused".
  This skill covers deep research, copywriting principles, HTML editing guard
  rails, and page structure. Always use it — do not attempt neighbourhood page
  work without it.
---

# Neighbourhood Pages Master Skill — anukabli.com

## Site Context

**Agent:** Anu Kabli, REALTOR® with IQI Global Real Estate  
**Languages:** English, Hindi, Punjabi, Odia  
**Markets served:** Brampton, Vaughan, King Township, Hamilton, Caledon, Mississauga, Halton Hills, Milton  
**Phone:** (647) 200-5779 — always clickable `tel:+16472005779`  
**Address:** 60 Scarsdale Rd Suite 112, North York, ON M3B 2R7  
**Site root:** `C:\Users\manmi\GitHub\RealEstateAgentFramework\site\`  
**Repo:** `C:\Users\manmi\GitHub\RealEstateAgentFramework`  
**Live URL:** https://anukabli.com  
**Deploy:** push to `main` → auto-redeploy on Render

The site targets GTA real estate buyers — primarily South Asian families, Italian-Canadian communities, move-up buyers, and professionals priced out of Toronto. Anu's multilingual capability is a key differentiator, especially in Brampton and Vaughan where parents may speak Hindi/Punjabi and want to ask hard questions in their own language.

---

## Two Modes

### Mode A — REWRITE existing page
Hero copy, labels, CTAs, sidebar text, "Working With Anu" section. Do NOT touch structure, CSS, JSON-LD schema, h1 tags, data tables, forms, or schema markup.

### Mode B — CREATE new page
Full deep research first (Steps 1–2 mandatory), then build complete HTML page following the established template.

---

## GUARD RAILS (both modes)

**NEVER touch:**
- `<script type="application/ld+json">` blocks — SEO schema, breaks Google if changed
- `<h1>` tags — SEO anchor, never rewrite
- CSS `<style>` blocks
- `<form>` elements and `window.LEAD_MAGNET_CONFIG` script
- Price tables, statistics, data tables — factual, not copy
- Footer link blocks
- `<meta>` description or `<title>` (unless explicitly asked)

**ALWAYS rewrite in Mode A:**
- `div.hero-label` — identity/positioning hook
- `p.hero-sub` — main marketing paragraph
- `div.call-block p` — urgency CTA in sidebar
- `div.sidebar-card .sub` — micro-commitment text under form header
- `h2 "Working With Anu Kabli in [X]"` section — make it specific and trust-building

---

## THE CORE RULE (applies to every sentence in every page)

> "No sentence in the page can exist without a corresponding field in the research JSON."

No AI fluff. No training-data assertions. Every stat has a source note on the page. If you cannot find a specific stat for a claim (e.g. "great schools"), do not make the claim. Either find the actual Fraser Institute rating or omit the section until you can.

---

## Step 1: Live Browser Research — MANDATORY HARD GATE (Mode B only)

**RULE: No HTML may be written until all 7 URLs below have been visited and data extracted. WebSearch summaries are NOT acceptable substitutes. Use `mcp__Claude_in_Chrome__navigate` + `mcp__Claude_in_Chrome__get_page_text` for every URL. If a URL returns 404 or no data, record that explicitly in the JSON with the URL visited and date attempted. Do not skip.**

### URLs to Visit in Order

| # | What to get | URL to visit |
|---|---|---|
| 1 | Demographics: population, income, ethnicity, ownership, families % | `https://hoodq.com/explore/[city]-on/[slug]` |
| 2 | Amenities: named restaurants, shops, parks | `https://wahi.com/ca/en/neighbourhoods/ontario/gta/[city]/[slug]` |
| 3 | Sold prices, DOM, sell-to-list, YoY %, listing counts | `https://zolo.ca/[city]-real-estate/[slug]/trends` |
| 4 | School Fraser rating + rank | `https://www.compareschoolrankings.org/secondary/[school-name-slug]` |
| 5 | Walk Score for neighbourhood | Open listing at `https://www.realtor.ca` in neighbourhood → walk score on listing page |
| 6 | GO Transit exact times | `https://www.gotransit.com/en/trip-planning` — plan trip from station to Union, note first AM departure + travel time |
| 7 | History: named founders, dates, events | `https://en.wikipedia.org/wiki/[Neighbourhood_Name,_Ontario]` |

### Source Hierarchy (by data type)

| Data Type | Primary Source | Secondary Source |
|---|---|---|
| Demographics (population, ethnicity, income, household size) | `hoodq.com/explore/[city]-on/[slug]` | StatCan Community Profile |
| Boundaries, amenities, parks, restaurants | `wahi.com/ca/en/neighbourhoods/ontario/gta/[city]/[slug]` | Google Maps |
| Average sale prices | `zolo.ca/[city]-real-estate/[slug]/trends` | `realosophy.com/neighbourhood-profile/[slug]` |
| Secondary school ratings | `compareschoolrankings.org` or `fraserinstitute.org` direct | Zolo listing pages show ratings inline |
| GO transit schedules | `gotransit.com/en/trip-planning` | `news.ontario.ca` for service changes |
| Walk Score | `realtor.ca` listing pages (shows area avg) | `walkscore.com` directly |
| History | `en.wikipedia.org/wiki/[Neighbourhood]` | City/municipality planning documents |

### HoodQ URL Patterns by City

| City | HoodQ Pattern |
|---|---|
| Brampton | `hoodq.com/explore/brampton-on/[slug]` |
| Vaughan | `hoodq.com/explore/vaughan-on/[slug]` |
| Hamilton | `hoodq.com/explore/hamilton-on/[slug]` |
| Mississauga | `hoodq.com/explore/mississauga-on/[slug]` |
| Milton | `hoodq.com/explore/milton-on/[slug]` |
| Caledon | `hoodq.com/explore/caledon-on/[slug]` |
| King Township | `hoodq.com/explore/king-on/[slug]` |
| Halton Hills | `hoodq.com/explore/halton-hills-on/[slug]` |
| Oakville | `hoodq.com/explore/oakville-on/[slug]` |

Note: Some neighbourhoods only exist at `hoodq.com/[agent-name]/explore/...` not the generic path. If generic returns 404, try: `site:hoodq.com [neighbourhood name] [city]` via Chrome.

### Wahi URL Patterns by City

| City | Wahi Pattern |
|---|---|
| Brampton | `wahi.com/ca/en/neighbourhoods/ontario/gta/brampton/[slug]` |
| Vaughan | `wahi.com/ca/en/neighbourhoods/ontario/gta/vaughan/[slug]` |
| Mississauga | `wahi.com/ca/en/neighbourhoods/ontario/gta/mississauga/[slug]` |
| Milton | `wahi.com/ca/en/neighbourhoods/ontario/gta/milton/[slug]` |
| Hamilton | `wahi.com/ca/en/neighbourhoods/ontario/hamilton/[slug]` |
| Caledon | `wahi.com/ca/en/neighbourhoods/ontario/gta/caledon/[slug]` |

Note: Not all neighbourhoods have Wahi pages. If 404, use Point2Homes.

### Zolo URL Patterns by City

| City | Zolo Trends Pattern |
|---|---|
| Brampton | `zolo.ca/brampton-real-estate/[slug]/trends` |
| Vaughan | `zolo.ca/vaughan-real-estate/[slug]/trends` |
| Hamilton | `zolo.ca/hamilton-real-estate/[slug]/trends` |
| Mississauga | `zolo.ca/mississauga-real-estate/[slug]/trends` |
| Milton | `zolo.ca/milton-real-estate/[slug]/trends` |
| Caledon | `zolo.ca/caledon-real-estate/[slug]/trends` |
| King Township | `zolo.ca/king-real-estate/[slug]/trends` |
| Halton Hills | `zolo.ca/halton-hills-real-estate/[slug]/trends` |
| Oakville | `zolo.ca/oakville-real-estate/[slug]/trends` |

**Critical:** Zolo sometimes has two zones with similar names (e.g. "Brampton East" vs "Bram East" — different price zones). Always verify which zone matches the actual neighbourhood boundary before using price data.

### Proof of Visit — Required JSON Field

Every research JSON must contain this block. If field is null, it means the URL was visited and data was unavailable — NOT that the visit was skipped:

```json
"visited_urls": [
  { "purpose": "demographics", "url": "https://hoodq.com/explore/...", "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
  { "purpose": "amenities",    "url": "https://wahi.com/...",           "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
  { "purpose": "prices",       "url": "https://zolo.ca/...",            "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
  { "purpose": "school",       "url": "https://compareschoolrankings.org/...", "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
  { "purpose": "walk_score",   "url": "https://www.realtor.ca/...",     "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
  { "purpose": "go_transit",   "url": "https://www.gotransit.com/...",  "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
  { "purpose": "history",      "url": "https://en.wikipedia.org/...",   "status": "200|404|no_data", "visited": "YYYY-MM-DD" }
]
```

### Fallback Rules (only after direct visit attempt fails)

| Scenario | Allowed fallback | NOT allowed |
|---|---|---|
| HoodQ 404 | Visit `https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/` and search community name | WebSearch summary |
| Wahi 404 | Visit `https://www.point2homes.com/CA/Real-Estate/ON/[City]/[Neighbourhood]` directly | Skip amenities section |
| Zolo no data | Visit `https://www.realosophy.com/neighbourhood-profile/` directly | Use cached/estimated prices |
| School not on compareschoolrankings | Visit `https://www.fraserinstitute.org/school-performance` directly | Training data guess |
| Walk Score not on realtor.ca | Visit `https://www.walkscore.com/score/[address]` | Invent or estimate a number |
| GO Transit page changed | Visit `https://www.gotransit.com/en/find-a-station` → click station | Use old cached data |

### Hard Stop Conditions

**Stop and flag to user if:**
- 4+ of the 7 URLs return 404 or no data → ask user whether to proceed with incomplete research
- Zolo price data is more than 6 months old → flag date to user before writing any price claims
- Fraser rating not found on compareschoolrankings OR fraserinstitute.org → school section must show "rating not confirmed — verify at fraserinstitute.org before purchase decision". Do NOT invent or use training data.

---

## Step 2: Save Research JSON

**File location:** `seo-research/[neighbourhood-slug]-research.json`

### Required JSON Fields

```json
{
  "neighbourhood": "Name",
  "city": "City",
  "research_date": "YYYY-MM-DD",
  "researcher": "Live browser research via Chrome MCP",

  "visited_urls": [
    { "purpose": "demographics", "url": "...", "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
    { "purpose": "amenities",    "url": "...", "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
    { "purpose": "prices",       "url": "...", "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
    { "purpose": "school",       "url": "...", "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
    { "purpose": "walk_score",   "url": "...", "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
    { "purpose": "go_transit",   "url": "...", "status": "200|404|no_data", "visited": "YYYY-MM-DD" },
    { "purpose": "history",      "url": "...", "status": "200|404|no_data", "visited": "YYYY-MM-DD" }
  ],

  "location": {
    "description": "...",
    "source": "URL"
  },

  "demographics": {
    "population": 0,
    "households": 0,
    "families_with_kids_pct": 0,
    "top_ethnic_origins": [{"origin": "", "pct": 0}],
    "first_gen_immigrants_pct": 0,
    "homeownership_pct": 0,
    "median_household_income": 0,
    "avg_individual_income": 0,
    "vehicle_commuters_pct": 0,
    "transit_commuters_pct": 0,
    "source": "URL"
  },

  "home_types": {
    "single_detached_pct": 0,
    "construction_period": {},
    "source": "URL"
  },

  "market_data": {
    "period": "Month Year",
    "avg_all_types": 0,
    "avg_detached": 0,
    "avg_townhouse": 0,
    "avg_condo": 0,
    "yoy_change_pct": 0,
    "median_dom": 0,
    "pct_sell_above_asking": 0,
    "pct_sell_under_10_days": 0,
    "active_listings": 0,
    "sources": ["URL 1", "URL 2"]
  },

  "transit": {
    "go_line": "",
    "go_station": "",
    "commute_union_station": "",
    "first_am_departure": "",
    "walk_score": null,
    "walk_score_source": "URL or null"
  },

  "schools": {
    "secondary": [
      {
        "name": "",
        "board": "",
        "type": "public|catholic",
        "grades": "",
        "fraser_rating": "X.X/10 or 'not confirmed in research'",
        "fraser_rank": "#XXX of 747 or null",
        "fraser_year": "2025",
        "source": "URL"
      }
    ],
    "elementary": [],
    "special_programs": [],
    "boundary_note": "",
    "ontario_provincial_avg": "6.0/10"
  },

  "parks_and_recreation": {
    "named_parks": [{"name": "", "features": []}],
    "source": "URL"
  },

  "amenities": {
    "named_restaurants": [],
    "named_shops": [],
    "source": "URL"
  },

  "history": {
    "founding_year": "",
    "founding_person": "",
    "key_events": [],
    "heritage_buildings": [],
    "indigenous_territory": "",
    "summary": "...",
    "source": "URL"
  }
}
```

### What to Do When Data Is Unavailable

- HoodQ 404 → note: `"demographics_source_note": "HoodQ 404 — used StatCan Census Profile [URL]"`
- Zolo no neighbourhood page → note source used instead
- Fraser rating not found → mark `"fraser_rating": "not confirmed in research"` — DO NOT use training data guesses
- Walk score not found → leave field `null`. Never invent a number.
- History minimal → note: `"history_source_note": "Wikipedia minimal — used [alternate source]"`

---

## Step 3: Positioning Decision (Mode B — before writing any HTML)

Answer these 3 questions. The answers become the hero-label, hero-sub, and call-block copy:

1. **Who is the buyer?** Be specific — "South Asian family, dual income $180K, wants south-facing lot near Mandir and GO" not "families"
2. **What is the one thing this neighbourhood has that nothing else at this price does?**
3. **What would make a buyer on the fence choose this over the next best option?**

---

## Step 4: The 8 Copywriting Techniques

Apply all 8 to every page. They are not optional.

### 1. Identity / Tribe Marketing
Don't describe the neighbourhood — describe the person who lives there.
- "Where Brampton's most established families live. Not where they started — where they arrived."
- "Where Brampton's South Asian families are putting down roots in 2026"
- "You spent 30 years building. This is what you earned."

### 2. PAS (Problem → Agitate → Solution)
- Problem: buyer is stuck comparing options, paralyzed by price
- Agitate: the window is closing, others are moving, this specific thing they want is rare
- Solution: this neighbourhood solves it exactly

### 3. Future Pacing
Put the buyer in the life they're buying:
- "Saturday mornings at Eldorado Park's free outdoor pool. Sunday afternoons at Teramoto Park's cricket pitch. Monday on the 5:44 AM GO to Union."
- "No more shoveling. No more mowing. No more managing contractors."

### 4. Negative Reframing (turn weaknesses into features)
- No GO Train → "built for families with two cars and a garage — wide streets, no parking stress"
- Car-dependent → "Caledon's value proposition has strengthened with hybrid work"
- Low walk score → "designed for privacy and space, not foot traffic"
- Older homes → "1950s brick on mature lots — the kind with actual trees and actual yard"

### 5. Urgency / Scarcity Signals
Use real data, not fake urgency:
- "8-day median. 50% sell in under 10 days. You have 24 hours, not a week."
- "Greenbelt protects 80% of this land permanently. The supply that doesn't exist today won't exist in 30 years."
- "0 condos active. 32 detached homes. This inventory doesn't sit."
- "In a market that hasn't been this buyer-friendly since 2019..."

### 6. Social Proof / Authority Signals
- Fraser Institute school ratings with specifics: "#130 of 747 Ontario secondary schools"
- Homeownership %: "92% of residents own" — implies stable, committed community
- Income anchors: "median HH income $141K" — tells buyer who their neighbours are
- Heritage/history: signals permanence, not a fly-by-night subdivision

### 7. Specificity over Generality
Generic: "great schools and parks"  
Specific: "Lorne Park Secondary School, ranked #130 of 747 Ontario secondary schools (7.6/10 Fraser)"

Generic: "convenient commute"  
Specific: "5:44 AM GO to Union Station — 24 minutes from Clarkson"

**Banned phrases (never use):** "excellent schools", "great transit", "vibrant community", "luxury lifestyle", "great location", "convenient amenities"

### 8. The Value Gap / Comparison Frame
Always anchor against a more expensive comparable:
- Ancaster vs Oakville: "$500K less, same school rating"
- Brampton East vs newer Brampton: "1950s brick on mature lots, $200K under what the same square footage costs two neighbourhoods over"
- Hamilton vs Brampton: "$190K less for comparable detached"
- King City vs Kleinburg: "same estate prestige, plus a GO Train Kleinburg doesn't have"

---

## Step 5: Per-Page Positioning Reference

| Page | Core Hook | Tribe | Key Data Point |
|------|-----------|-------|----------------|
| castlemore-brampton | "Where they arrived, not where they started" | Established Brampton luxury families | 92% homeownership, $1.31M |
| credit-valley-brampton | Where South Asian families are buying in 2026 | South Asian GTA families | GO access, under $1.1M, cricket pitch |
| mount-pleasant-brampton | Only Brampton neighbourhood walkable to GO | GO commuters wanting neighbourhood feel | Walk to GO, $950K, 50 min Union |
| northwood-park-brampton | Near GO. Under $950K. Proper lot. | Value-focused families near transit | 35 min Kitchener line to Union |
| rosedale-village-brampton | You earned this | Retirees selling the big house | Gated, golf, pool, $300K–$1.25M |
| brampton-east-homes | Value hiding in plain sight | First-time buyers, value hunters | 1950s brick, $808K, mature lots |
| king-city-homes | Only estate community with a GO Train | Vaughan move-ups, Italian-Canadian | 35.1% Italian, 50 min GO, Moraine |
| schomberg-homes | Fastest market, most affordable entry | King Twp value hunters | 8-day median, condos from $499K |
| kleinburg-homes | Village with a soul vs suburb with lower prices | Affluent Italian-Canadian families | Heritage Conservation District, +10% YoY |
| nobleton-homes | 25 min to Pearson — the arithmetic Kleinburg can't match | Airport-adjacent professionals | <30 min Pearson, 10% sell above asking |
| bolton-homes | Positive growth while GTA corrects | Brampton escapees, Italian roots | +4.2% YoY, $831K–$1.02M |
| vaughan-real-estate | Only 905 city with subway running now | Transit-forward buyers, diverse families | VMC Line 1, condos from $513K |
| hamilton-homes | $190K less than Brampton. Buyer's market. | GTA buyers priced out of Brampton+ | $828K detached avg, 45 DOM |
| caledon-real-estate | Greenbelt supply cap is the point | Space seekers, Brampton escapees | 688 km², 89% homeownership |
| ancaster-homes | Oakville schools. Hamilton prices. | Oakville/Burlington refugees | #130/747 ON schools, $1.1M avg |
| king-township-real-estate | Doesn't correct like other markets | Vaughan move-ups, luxury buyers | Moraine + Greenbelt supply lock |
| mississauga-real-estate | 26 neighbourhoods. One agent who knows all of them. | Mississauga upgraders + newcomers | $982K avg, buyer's market, 27 DOM |
| port-credit-homes | 27-min GO + lakefront village Mississauga can't replicate | Young professionals, downsizers | $1.29M avg, 26% families — verify before buying |
| lorne-park-homes | School boundary is the investment thesis | Executive families, $300K+ HHI | LPSS 7.6/10 #130/747, $1.85M avg sold |
| halton-hills-real-estate | 87% ownership. Georgetown GO. $955K. | Brampton move-ups, small-town seekers | 87% ownership, 55-65 min GO |
| georgetown-homes | Credit River, GO train, $955K avg | Halton Hills family buyers | Georgetown GO Kitchener line |
| milton-real-estate | Fastest-growing municipality. Buyer's market. Now. | Young families, value seekers | $974K avg, -9% YoY, Niagara Escarpment |
| condos-for-sale-milton | $480K 1-bed. Milton GO. Escarpment views. | First-time buyers, downsizers | $598K avg, -17.7% YoY, 129 active |

---

## Step 6: Page Structure (Mode B — HTML Template)

Follow this exact structure. See any existing page (e.g. `site/kleinburg-homes-for-sale.html`) as living template.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <!-- Title: "[Community] Homes for Sale | [Parent Market] Real Estate | Anu Kabli REALTOR®" -->
  <!-- Meta description: 150–160 chars, include community name, avg price, key stat, phone -->
  <!-- Canonical: https://anukabli.com/[slug] (NO .html extension) -->
  <!-- JSON-LD: RealEstateAgent schema — NEVER MODIFY after creation -->
  <!-- JSON-LD: FAQPage schema (5 FAQs minimum) — NEVER MODIFY after creation -->
  <!-- Google Fonts: Playfair Display + Inter -->
  <!-- <style> block — copy from existing page, do not modify -->
</head>
<body>
  <nav> <!-- standard nav — copy exact from existing page -->

  <div class="hero">
    <div class="breadcrumb"> <!-- Home > [Parent Pillar] > [Community] -->
    <div class="hero-label"> <!-- IDENTITY HOOK — technique #1, not category label -->
    <h1>Homes for Sale in<br/><span>[Community, Ontario]</span></h1>
    <p class="hero-sub"> <!-- PAS + future pacing + urgency — 3–5 sentences, specific data -->
    <div class="hero-stats"> <!-- 4 stats: avg price, DOM or population, income or ownership, key differentiator -->
    <div class="hero-cta"> <!-- Call button + See Listings button -->

  <div class="page-wrap"> <!-- grid: 1fr 360px -->
    <div class="content">
      <h2>[Community] Real Estate Market — 2026</h2>
      <!-- price table from research JSON -->
      <p class="source-note">Source: [exact URL visited]</p>

      <h2>Who Lives in [Community]</h2>
      <!-- demographics from JSON — income, ownership %, ethnicity, families % -->
      <p class="source-note">Source: [exact URL visited]</p>

      <h2>Housing Stock: What You're Buying</h2>
      <!-- construction period, home types, sub-communities -->
      <p class="source-note">Source: [exact URL visited]</p>

      <h2>Schools Serving [Community]</h2>
      <!-- school-cards with Fraser rating, rank/747, above/below 6.0 avg -->
      <!-- uncomfortable truth if below average: state it plainly -->
      <p class="source-note">Source: [exact URL visited]</p>

      <h2>Transit &amp; Getting Around</h2>
      <!-- GO line, station, exact commute time to Union, first AM departure -->
      <!-- if car-dependent: negative reframe technique #4 -->
      <p class="source-note">Source: [exact URL visited]</p>

      <h2>Parks &amp; Natural Features</h2>
      <!-- named parks only — from research JSON, not training data -->
      <p class="source-note">Source: [exact URL visited]</p>

      <h2>[Community] vs [Comparable] — The Numbers</h2>
      <!-- comparison table — value gap technique #8 -->

      <h2>History</h2>
      <!-- specific named people, years, events — min 3 facts -->
      <!-- never: "the area was developed in the X era" filler -->
      <p class="source-note">Source: [exact URL visited]</p>

      <h2>Working With Anu Kabli in [Community]</h2>
      <!-- see Working With Anu template below -->

      <h2>Explore More Communities</h2>
      <!-- explore-grid with 4 related pages -->

      <h2>Frequently Asked Questions</h2>
      <!-- 5 faq-items — must match FAQPage JSON-LD exactly -->

    <div class="sidebar">
      <!-- contact form (formspree REPLACE_WITH_FORM_ID) -->
      <!-- neighbourhood snapshot (info-rows from research JSON) -->
      <!-- call-block (real scarcity signal from data — DOM, YoY, inventory) -->

  <footer>
    <!-- comprehensive footer with ALL city sections — see footer template -->

  <script>window.LEAD_MAGNET_CONFIG = {
    neighbourhood: "[Name]",
    city: "[City]",
    minPrice: [from research — detached low or condo low],
    maxPrice: [from research — detached high]
  };</script>
  <script src="/lead-magnet.js"></script>
```

### School Rating CSS Classes

```css
.rating-high { /* green — Fraser above 6.5/10 */ }
.rating-mid  { /* gold  — Fraser 5.5–6.5/10 */ }
.rating-low  { /* red   — Fraser below 5.5/10 */ }
```

Always show in school card:
- Actual score (X.X/10)
- Rank (#XXX of 747 Ontario secondary schools)
- Whether above or below Ontario provincial average (6.0/10)
- Source note (Fraser Institute 2025 — data year is 2023–2024 EQAO)

**Never describe below-average schools as "great schools".**

### Source Notes

Every data section must end with:
```html
<p class="source-note">Source: [source name and exact URL visited]</p>
```

---

## Step 7: SEO Requirements

**Title:** `[Community] Homes for Sale | [Parent Market] Real Estate | Anu Kabli REALTOR®`  
**Meta description:** 150–160 chars, include community name, avg price, key stat, Anu's phone  
**Canonical:** `https://anukabli.com/[slug]` — NO .html extension  
**H1:** `Homes for Sale in [Community, Ontario]` — exact format, no variation  
**Slug pattern:** `[community-name]-homes-for-sale` or `[community-name]-real-estate`  
**Internal links:** Link TO this page from parent pillar page. Link FROM this page to 3–5 related pages.  
**JSON-LD FAQPage:** Minimum 5 questions. Must match FAQ section content exactly.

---

## Step 8: "Working With Anu" Section Template

Make it specific. Not generic agent boilerplate. Each point must be hyper-relevant to that community:

```
For [neighbourhood] specifically, Anu can help you:
- [Community-specific market insight — e.g., "Navigate the 8-day Schomberg market — pre-approval strategy and 24-hour offer process"]
- [Heritage/zoning specific — e.g., "Heritage Conservation District purchase process in Kleinburg — Ontario Heritage Act implications"]
- [Language-specific — e.g., "Your parents can ask the hard questions in the language they think in — Hindi, Punjabi, or Odia"]
- [Comparison framing — e.g., "Understand exactly why Ancaster at $1.1M beats Oakville at $1.6M for your specific criteria"]
- [Data-specific — e.g., "Access comparable sales across all three Bolton sub-areas for accurate offer pricing"]
```

Always end with: `Call directly: <a href="tel:+16472005779" style="color:var(--gold);">(647) 200-5779</a>`

---

## Step 9: Infrastructure Updates (after every new page)

### render.yaml — Add URL rewrite

```yaml
- type: rewrite
  source: /[neighbourhood-slug]
  destination: /[neighbourhood-slug].html
```

### site/sitemap.xml — Add URL entry

```xml
<url>
  <loc>https://anukabli.com/[neighbourhood-slug]</loc>
  <lastmod>YYYY-MM-DD</lastmod>
  <changefreq>monthly</changefreq>
  <priority>0.9</priority>  <!-- 0.95 for city pillar pages -->
</url>
```

### Footer on ALL existing pages

Every page must link to the new page in the footer. Footer structure:

```html
<strong>CITY NAME:</strong>
<a href="/page-slug">Page Name</a>
```

City sections in footer: VAUGHAN | KING TOWNSHIP | BRAMPTON | MISSISSAUGA | HALTON HILLS | CALEDON | HAMILTON | MILTON

### Parent pillar page

Add new neighbourhood to the parent city pillar's explore-grid and neighbourhood list.

---

## Step 10: Commit and Deploy

```bash
git add site/[slug].html seo-research/[slug]-research.json render.yaml site/sitemap.xml
git commit -m "feat(seo): add [Community] neighbourhood page — live browser research

Sources visited:
- Demographics: [HoodQ URL]
- Prices: [Zolo URL]
- Schools: [compareschoolrankings URL]
- Transit: [gotransit URL]"

git push origin main
```

Render auto-deploys from main. Verify live at `anukabli.com/[slug]` after ~60 seconds.

---

## Mode A — Rewrite Workflow

### Step 1: Diagnose

Read the page. Identify tier:

| Tier | Problem | Action |
|------|---------|--------|
| 3 — Critical | Pure info dump, zero aspiration, no buyer identity | Full rewrite of all Mode A elements |
| 2 — Weak | Some marketing language but generic, no tribe signal | Rewrite hero-label + hero-sub + call-block |
| 1 — Decent | Has positioning but misses emotional hook | Working With Anu section only |

### Step 2: Apply the 8 Copywriting Techniques

See techniques 1–8 above. Apply specifically to:
- `div.hero-label` — identity/positioning hook (Technique 1)
- `p.hero-sub` — PAS + future pacing + urgency (Techniques 2, 3, 5)
- `div.call-block p` — real scarcity signal (Technique 5)
- `div.sidebar-card .sub` — micro-commitment (Technique 6)
- "Working With Anu" section — specificity + comparison frame (Techniques 7, 8)

### Step 3: After Rewrite

```bash
git add site/[file].html
git commit -m "feat(copy): rewrite [Community] hero + positioning"
git push origin main
```

---

## Batch Rewrite Process

When user says "batch rewrite all pages" or "rewrite the [region] pages":

**Priority order:**
1. Tier 3 pages first (worst conversion impact)
2. Hub pages second
3. Tier 1 pages last (Working With Anu section only)

Edit all files, then single commit:

```bash
git add site/*.html
git commit -m "feat(copy): conversion-optimized hero copy across [N] pages"
git push origin main
```

---

## Quality Checklist (before every commit)

**Research (Mode B):**
- [ ] `visited_urls` array present in research JSON with status for all 7 URLs
- [ ] Every stat in HTML maps to a field in research JSON
- [ ] Price data is dated (Month Year) and exact source URL named
- [ ] Fraser ratings include rank out of 747, year, above/below 6.0 avg
- [ ] School names verified against HoodQ or school board directory (not training data)
- [ ] Walk Score from specific visited source, or null — never estimated
- [ ] History section has specific named people/events/years — no generic filler
- [ ] Uncomfortable truths included: below-average schools, car-dependency, price comparisons

**Copy (both modes):**
- [ ] hero-label reads as identity/positioning, not category label ("Vaughan's Only Heritage Village" not "Kleinburg Real Estate")
- [ ] hero-sub has: specific data point + buyer identity + urgency signal
- [ ] No generic phrases: "great schools", "excellent transit", "vibrant community", "luxury lifestyle"
- [ ] call-block uses real scarcity (DOM, inventory count, YoY trend) not fake urgency
- [ ] "Working With Anu" has community-specific bullets, not boilerplate
- [ ] Value gap / comparison present (technique 8)
- [ ] Future pacing present (technique 3)

**Infrastructure (Mode B):**
- [ ] JSON-LD schema untouched (if rewriting) or complete (if new)
- [ ] h1 untouched (if rewriting)
- [ ] Forms untouched
- [ ] CSS untouched
- [ ] render.yaml updated
- [ ] sitemap.xml updated
- [ ] Footer on ALL existing pages updated with new page link
- [ ] LEAD_MAGNET_CONFIG present with correct prices
- [ ] Canonical URL uses clean slug (no .html)

---

## Anu's Differentiators (use in Working With Anu sections)

- **Multilingual:** English, Hindi, Punjabi, Odia — "your parents can ask the hard questions in the language they think in"
- **IQI Global Real Estate:** international network, relevant for buyers with overseas connections
- **Full markets:** Brampton + Vaughan + King Township + Hamilton + Caledon + Mississauga + Halton Hills + Milton — can compare across regions
- **Licensed REALTOR® + mortgage broker + LLQP** — handles the full picture: mortgage, insurance, purchase
- **Phone:** (647) 200-5779 — always include, always clickable `tel:+16472005779`
- **Response time:** "Anu responds personally within the hour"

---

## Current Pages — Status Tracker

| Page | URL | Research JSON | Research Method | Copy Tier |
|---|---|---|---|---|
| Brampton homes | `/brampton-homes-for-sale` | — | — | Pillar |
| Northwood Park | `/northwood-park-brampton` | `seo-research/northwood-park-research.json` | WebSearch | Needs rewrite |
| Castlemore | `/castlemore-brampton` | `seo-research/castlemore-research.json` | WebSearch | Needs rewrite |
| Brampton East | `/brampton-east-homes-for-sale` | `seo-research/brampton-east-research.json` | WebSearch | Needs rewrite |
| Mount Pleasant | `/mount-pleasant-brampton` | `seo-research/mount-pleasant-research.json` | WebSearch | Needs rewrite |
| Rosedale Village | `/rosedale-village-brampton` | `seo-research/rosedale-village-research.json` | WebSearch | Needs rewrite |
| Credit Valley | `/credit-valley-brampton` | `seo-research/credit-valley-research.json` | WebSearch | Needs rewrite |
| Vaughan | `/vaughan-real-estate` | — | — | Pillar |
| Kleinburg | `/kleinburg-homes-for-sale` | — | WebSearch | Needs rewrite |
| King Township | `/king-township-real-estate` | — | — | Pillar |
| King City | `/king-city-homes-for-sale` | — | WebSearch | Needs rewrite |
| Nobleton | `/nobleton-homes-for-sale` | — | WebSearch | Needs rewrite |
| Schomberg | `/schomberg-homes-for-sale` | — | WebSearch | Needs rewrite |
| Hamilton | `/hamilton-homes-for-sale` | — | WebSearch | Needs rewrite |
| Ancaster | `/ancaster-homes-for-sale` | — | WebSearch | Needs rewrite |
| Caledon | `/caledon-real-estate` | — | — | Pillar |
| Bolton | `/bolton-homes-for-sale` | — | WebSearch | Needs rewrite |
| Mississauga | `/mississauga-real-estate` | `seo-research/mississauga-real-estate-research.json` | WebSearch | Needs rewrite |
| Port Credit | `/port-credit-homes-for-sale` | `seo-research/port-credit-research.json` | WebSearch | Needs rewrite |
| Lorne Park | `/lorne-park-homes-for-sale` | `seo-research/lorne-park-research.json` | WebSearch | ❌ Build |
| Halton Hills | `/halton-hills-real-estate` | `seo-research/halton-hills-real-estate-research.json` | WebSearch | ❌ Build |
| Georgetown | `/georgetown-homes-for-sale` | `seo-research/georgetown-research.json` | WebSearch | ❌ Build |
| Milton | `/milton-real-estate` | `seo-research/milton-real-estate-research.json` | WebSearch | ❌ Build |
| Milton Condos | `/condos-for-sale-milton` | `seo-research/condos-for-sale-milton-research.json` | WebSearch | ❌ Build |

**Research Method legend:**
- `Live browser` = Chrome MCP direct visits, `visited_urls` JSON field populated ✅
- `WebSearch` = Google summaries only — research JSON needs `visited_urls` field + data gaps need live verification before page is considered complete

---

## Build Queue — Priority Order

### Phase 1 — Build Now (pages not yet created)

| # | Page | URL | Research Status |
|---|---|---|---|
| 1 | Lorne Park | `/lorne-park-homes-for-sale` | JSON exists (WebSearch) — needs live browser verification |
| 2 | Halton Hills pillar | `/halton-hills-real-estate` | JSON exists (WebSearch) — needs live browser verification |
| 3 | Georgetown | `/georgetown-homes-for-sale` | JSON exists (WebSearch) — needs live browser verification |
| 4 | Milton pillar | `/milton-real-estate` | JSON exists (WebSearch) — needs live browser verification |
| 5 | Milton Condos | `/condos-for-sale-milton` | JSON exists (WebSearch) — needs live browser verification |

### Phase 2 — Rewrite Existing (copy tier upgrade)

Priority: Northwood Park → Castlemore → Brampton East → Mount Pleasant → Rosedale Village → Credit Valley → Kleinburg → King City → Nobleton → Schomberg → Bolton → Hamilton → Ancaster

### Phase 3 — New Builds (research + create)

| Neighbourhood | Keyword | Vol | KD | URL |
|---|---|---|---|---|
| Woodbridge | woodbridge homes for sale | 480 | 15 | /woodbridge-homes-for-sale |
| Thornhill | thornhill homes for sale | 390 | 15 | /thornhill-homes-for-sale |
| Stoney Creek | stoney creek homes for sale | 590 | 14 | /stoney-creek-homes-for-sale |
| Mimico | mimico homes for sale | 210 | 14 | /mimico-homes-for-sale |
| Palgrave | palgrave homes for sale | 170 | 10 | /palgrave-homes-for-sale |
| Streetsville | streetsville homes for sale | 140 | 14 | /streetsville-homes-for-sale |
| Dundas | dundas ontario homes for sale | 210 | 14 | /dundas-ontario-homes-for-sale |
| Glen Abbey | glen abbey homes for sale | 90 | 13 | /glen-abbey-homes-for-sale |
| Acton | acton ontario homes for sale | 90 | 14 | /acton-homes-for-sale |

### Phase 4 — Conversion Pages

| Page | Keyword | Vol | KD |
|---|---|---|---|
| /condos-for-sale-brampton | condos for sale in brampton | 880 | 13 |
| /hindi-punjabi-speaking-real-estate-agent | hindi punjabi realtor GTA | est. 200+ | 0 |
| /ontario-land-transfer-tax-calculator | land transfer tax ontario calculator | 2,000 | 25 |
| /sell-my-home-brampton | sell my home brampton | est. 300+ | low |

---

## School Boards by City

| City | Public Board | Catholic Board |
|---|---|---|
| Brampton / Mississauga | Peel District School Board (PDSB) | Dufferin-Peel CDSB |
| Hamilton | Hamilton-Wentworth DSB | Hamilton-Wentworth CDSB |
| Vaughan / King / Newmarket | York Region DSB | York Catholic DSB |
| Halton (Georgetown / Oakville / Milton) | Halton DSB | Halton CDSB |
| Scarborough / Etobicoke | Toronto DSB | Toronto CDSB |

**Fraser Institute data year:** 2025 report is based on 2023–2024 EQAO data. Always note the data year when citing. Do not cite 2024 report card numbers as "2025 ratings."

---

## Common Pitfalls

**Wrong school names** — Training data frequently hallucinates school names. Always verify against HoodQ or school board directory. Most common errors: listing Sandalwood Heights SS for Northwood Park (wrong boundary); Cardinal Ambrozic for Credit Valley (wrong boundary).

**Zolo zone confusion** — "Bram East" ($1.08M) and "Brampton East" ($808K) are different Zolo zones. Always check actual neighbourhood boundary.

**HoodQ agent-specific URLs** — Some neighbourhoods only exist at `hoodq.com/[agent-name]/explore/...`. If generic returns 404, search: `site:hoodq.com [neighbourhood] [city]`.

**Walk Score variation** — Scores vary by specific address. Use area average from realtor.ca listing pages. A single address at neighbourhood edge may not represent whole area.

**Fraser data year** — 2025 Fraser report = 2023–2024 EQAO data. Do not mix years.

---

## Directory Profiles — Anu Must Create (Critical for Local SEO)

NAP must be identical everywhere: **Anu Kabli | (647) 200-5779 | 60 Scarsdale Rd Suite 112, North York, ON M3B 2R7 | anukabli.com**

| Platform | URL | Priority |
|---|---|---|
| Google Business Profile | https://business.google.com/create | 🔴 #1 |
| rankmyagent.com | https://www.rankmyagent.com/realtors/sign-up | 🔴 Today |
| ratemyagent.ca | https://www.ratemyagent.ca/real-estate-agents/create-profile | 🔴 Today |
| realtor.ca agent profile | https://www.realtor.ca/agentprofile | 🔴 Verify |
| zillow.com/professionals | https://www.zillow.com/agent-profile/ | 🟠 This week |
| HomeStars | https://homestars.com/join | 🟠 This week |
| YP.ca | https://www.yp.ca/add-update-business | 🟠 This week |
