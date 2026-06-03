# Neighbourhood Page Creation Process

**Standard for anukabli.com neighbourhood pages.**
Every sentence in the HTML must map to a verified field in the research JSON.
No AI fluff. No training-data assertions. Every stat has a source note on the page.

---

## The Core Rule

> "No sentence in the page can exist without a corresponding field in the research JSON."

If you cannot find a specific stat for a claim (e.g. "great schools"), do not make the claim. Either find the actual Fraser Institute rating or omit the schools section until you can.

---

## Step 1: Live Browser Research

Open Chrome and hit these sources **in order**. Save everything to a JSON file before writing any HTML.

### Source Hierarchy

| Data Type | Primary Source | Secondary Source |
|---|---|---|
| Demographics (population, ethnicity, income, household size) | `hoodq.com/explore/brampton-on/[slug]` | StatCan Community Data |
| Boundaries, amenities, parks, restaurants | `wahi.com/ca/en/neighbourhoods/ontario/gta/brampton/[slug]` | Google Maps |
| Average sale prices | `zolo.ca/brampton-real-estate/[slug]/trends` | `realosophy.com/neighbourhood-profile/[slug]` |
| Secondary school ratings | `fraserinstitute.org` (direct) or `compareschoolrankings.org` | `zolo.ca` listing pages show ratings inline |
| GO transit schedules | `gotransit.com/routes-departures/[station]` | `news.ontario.ca` for service change announcements |
| Walk Score | `realty.ca` listing pages for neighbourhood addresses (shows area avg) | `walkscore.com` directly |
| History | `wahi.com` neighbourhood guide | City of Brampton planning documents |

### HoodQ URL Pattern
```
hoodq.com/explore/brampton-on/[neighbourhood-slug]
```
Examples:
- `hoodq.com/explore/brampton-on/northwood-park`
- `hoodq.com/explore/brampton-on/brampton-east`
- Some neighbourhoods use agent-specific URLs: `hoodq.com/[agent-name]/explore/brampton-on/vales-of-castlemore`

### Wahi URL Pattern
```
wahi.com/ca/en/neighbourhoods/ontario/gta/brampton/[slug]
```
Note: Not all Brampton neighbourhoods have Wahi pages. If 404, use Google search.

### Zolo URL Pattern
```
zolo.ca/brampton-real-estate/[slug]/trends
```
**Critical:** Zolo sometimes has two zones with similar names (e.g. "Brampton East" vs "Bram East"). Always verify which zone matches the actual neighbourhood before using price data.

### Fraser Institute School Ratings
- Search: `"[School Name]" Fraser Institute rating 2025`
- Zolo listing pages show Fraser ratings inline — reliable for confirming ratings
- Ontario provincial average: **6.0 / 10** (use as benchmark in every page)
- Rankings use 747 total Ontario secondary schools (2025 report)

---

## Step 2: Save Research JSON

**File location:** `seo-research/[neighbourhood-slug]-research.json`

### Required JSON Fields

```json
{
  "neighbourhood": "Name",
  "city": "Brampton",
  "research_date": "YYYY-MM-DD",
  "researcher": "Live browser research",

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
    "vehicle_commuters_pct": 0,
    "transit_commuters_pct": 0,
    "household_income_distribution": {},
    "source": "URL"
  },

  "home_types": {
    "single_detached_pct": 0,
    "construction_period": {},
    "source": "URL"
  },

  "market_data": {
    "period": "Month Year",
    "avg_price": 0,
    "sources": ["URL 1", "URL 2"]
  },

  "transit": {
    "go_station": {},
    "walk_score": 0,
    "transit_score": 0,
    "walk_score_source": "URL"
  },

  "schools": {
    "secondary": [
      {
        "name": "",
        "board": "",
        "type": "public|catholic",
        "fraser_rating": "X.X/10",
        "fraser_rank": "#XXX of 747",
        "fraser_year": "2025",
        "source": "URL"
      }
    ],
    "elementary": [],
    "special_programs": [],
    "source": "URL"
  },

  "parks_and_recreation": {
    "total_parks": 0,
    "named_parks": [{"name": "", "features": []}],
    "source": "URL"
  },

  "amenities": {
    "shopping": [],
    "restaurants": [],
    "source": "URL"
  },

  "history": {
    "summary": "...",
    "source": "URL"
  }
}
```

### What to Do When Data Is Unavailable

- If HoodQ returns 404: use Wahi + Google + Realosophy. Note in JSON: `"demographics_source_note": "HoodQ 404 — data unavailable at research date"`
- If Zolo has no neighbourhood page: use Realosophy + Google search snippets. Note source.
- If Fraser rating not found: mark as `"fraser_rating": "not confirmed in research"` — DO NOT use training data guesses
- If walk score not found: leave field null. Don't invent a number.

---

## Step 3: Write the HTML Page

### File location
`site/[neighbourhood-slug].html`

### Template Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <!-- Title: "Homes for Sale in [Neighbourhood] Brampton | Anu Kabli REALTOR®" -->
  <!-- Meta description: use real price stats from research JSON -->
  <!-- Canonical: https://anukabli.com/[slug] (no .html extension) -->
  <!-- RealEstateAgent schema JSON-LD -->
  <!-- FAQPage schema JSON-LD (5 FAQs minimum) -->
  <!-- Google Fonts (Playfair Display + Inter) -->
  <!-- CSS (copy from existing page) -->
</head>
<body>
  <!-- NAV (standard — links to /) -->
  <!-- HERO (h1, hero stats from research JSON, CTA buttons) -->
  <!-- PAGE-WRAP (2-col grid: content + sidebar) -->
    <!-- CONTENT:
      - About section
      - Home prices (table from research JSON)
      - Who lives here (demographics from JSON)
      - Housing stock (construction period from JSON)
      - Schools (school-card components with actual Fraser ratings)
      - Parks & Recreation (specific named parks, not generic)
      - Transit & commute (specific times, not "great transit")
      - Amenities (specific named shops/restaurants from JSON)
      - History (specific story from JSON)
      - Working with Anu
      - FAQ (5+ items matching FAQPage schema)
    -->
    <!-- SIDEBAR:
      - Contact form
      - Neighbourhood Snapshot (stats from JSON)
      - Call block
    -->
  <!-- FOOTER with neighbourhood bar (all 6 links) -->
  <!-- LEAD MAGNET SCRIPTS -->
</body>
```

### School Rating Display

Use these CSS classes for school ratings:
```css
.rating-high { /* green — above 6.5/10 */ }
.rating-mid  { /* gold — 5.5–6.5/10 */ }
.rating-low  { /* red — below 5.5/10 */ }
```

Always show:
- The actual score (X.X/10)
- Rank (#XXX of 747 Ontario secondary schools)
- Whether above or below Ontario provincial average (6.0/10)
- Source note (Fraser Institute 2025 / EQAO year)

**Never describe below-average schools as "great schools".**

### Source Notes

Every data section must end with:
```html
<p class="source-note">Source: [source name and URL]</p>
```

### Lead Magnet Config

At bottom of every page before `</body>`:
```html
<script>
  window.LEAD_MAGNET_CONFIG = {
    neighbourhood: "[Name]",
    city: "Brampton",
    minPrice: [from research market_data],
    maxPrice: [from research market_data]
  };
</script>
<script src="/lead-magnet.js"></script>
```

Price ranges: use the actual market data range — detached low to detached high. For Rosedale Village (condos), use condo low.

---

## Step 4: Update Infrastructure Files

After creating/updating each page, update:

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
  <priority>0.9</priority>
</url>
```

### site/index.html — Add to Brampton footer column
```html
<li><a href="/[neighbourhood-slug]">[Neighbourhood Name]</a></li>
```

### Footer bar on ALL existing pages
Every page must have the neighbourhood bar updated with the new page link.

---

## Step 5: Commit and Deploy

```bash
git add site/[slug].html seo-research/[slug]-research.json render.yaml site/sitemap.xml site/index.html
git commit -m "Add [Neighbourhood] page: live research-first

Sources:
- Demographics: HoodQ [URL]
- Prices: Zolo [URL]  
- Schools: Fraser Institute 2025
- Amenities: Wahi [URL]
- Walk Score: realty.ca listings"

git push origin main
```

Render auto-deploys from main branch. Verify live at `www.anukabli.com/[slug]` after ~60 seconds.

---

## Quality Checklist (Before Commit)

- [ ] Every stat in HTML has a source note on the page
- [ ] Fraser ratings include rank out of 747, year, and above/below provincial avg statement
- [ ] School names match actual school names (not training data guesses — verify against HoodQ or Peel DSB school directory)
- [ ] Price data is dated (Month Year) and source is named
- [ ] Walk Score is from a specific listing source, not estimated
- [ ] No use of: "excellent schools", "great transit", "vibrant community", "luxury lifestyle", or similar vague positive claims
- [ ] Uncomfortable truths included: below-average school ratings, car-dependency scores, pricing above/below comparisons
- [ ] History section contains specific named people/events, not generic "the area was developed in the X era" filler
- [ ] lead-magnet.js and LEAD_MAGNET_CONFIG present
- [ ] Footer neighbourhood bar includes all 6 current Brampton neighbourhood links
- [ ] Canonical URL uses clean URL (no .html)
- [ ] render.yaml has corresponding rewrite rule
- [ ] sitemap.xml updated with clean URL

---

## Current Brampton Neighbourhood Pages

| Page | URL | Research JSON | Status |
|---|---|---|---|
| Northwood Park | `/northwood-park-brampton` | `seo-research/northwood-park-research.json` | Live (research-first rewrite June 2026) |
| Castlemore | `/castlemore-brampton` | `seo-research/castlemore-research.json` | Live (research-first rewrite June 2026) |
| Brampton East | `/brampton-east-homes-for-sale` | `seo-research/brampton-east-research.json` | Live (research-first rewrite June 2026) |
| Mount Pleasant | `/mount-pleasant-brampton` | `seo-research/mount-pleasant-research.json` | Live (research-first rewrite June 2026) |
| Rosedale Village | `/rosedale-village-brampton` | `seo-research/rosedale-village-research.json` | Live (research-first rewrite June 2026) |
| Credit Valley | `/credit-valley-brampton` | `seo-research/credit-valley-research.json` | Live (original research-first build June 2026) |

---

## Neighbourhood Build Queue (Research Not Yet Done)

Priority order based on search volume and keyword difficulty:

**Brampton:**
- Downtown Brampton (KD 14, ~90 searches/mo)
- Heart Lake Brampton (KD ~12, ~50/mo)

**Mississauga:**
- Port Credit (KD 12)
- Lorne Park (KD 7)
- Cooksville, Lakeview, Applewood, Clarkson, Erin Mills, Churchill Meadows

**Oakville:**
- Glen Abbey, Old Oakville, Bronte, Joshua Creek

**Vaughan:**
- Woodbridge, Maple, Kleinburg

**Milton:**
- Harrison, Hawthorne Village, condos

**Caledon:**
- Bolton, estate homes

**Phase 2 — City Authority Pages:**
- `/top-realtor-brampton`
- `/mississauga-real-estate-agent`
- `/hindi-punjabi-speaking-real-estate-agent` (KD 0)
- `/brampton-condos-for-sale` (880/mo, KD 13)

---

## Common Pitfalls

**Wrong school names** — Training data frequently hallucinates school names. Always verify against HoodQ or `peelschools.org/school-directory`. The most common error: listing Sandalwood Heights SS for Northwood Park (it doesn't serve that area) or listing Cardinal Ambrozic for Credit Valley (it doesn't).

**Zolo zone confusion** — "Bram East" ($1.08M) and "Brampton East" ($808K) are different Zolo zones. Always check the actual neighbourhood boundary before using Zolo price data.

**HoodQ agent-specific URLs** — Some neighbourhoods only exist at `hoodq.com/[agent-name]/explore/...` not the generic path. If generic returns 404, try Google: `site:hoodq.com [neighbourhood name] brampton`.

**Fraser data year** — The 2025 Fraser Institute report is based on 2023-2024 EQAO data. Always note the data year when citing ratings. Do not cite 2024 report card numbers as "2025 ratings" — they're different.

**Walk Score variation** — Walk Scores vary by specific address. Use the area average from realty.ca listing pages (they show "average walkability score in surrounding area"). A single address at the edge of a neighbourhood may not represent the whole area.
