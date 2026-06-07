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

# Neighbourhood Pages Skill — anukabli.com

## Site Context

**Agent:** Anu Kabli, REALTOR® with IQI Global Real Estate  
**Languages:** English, Hindi, Punjabi, Odia  
**Markets served:** Brampton, Vaughan, King Township, Hamilton, Caledon  
**Site root:** `C:\Users\manmi\GitHub\RealEstateAgentFramework\site\`  
**Repo:** `C:\Users\manmi\GitHub\RealEstateAgentFramework`  
**Live URL:** https://anukabli.com  
**Deploy:** push to `main` → auto-redeploy

The site targets GTA real estate buyers — primarily South Asian families, Italian-Canadian communities, move-up buyers, and professionals priced out of Toronto. Anu's multilingual capability is a key differentiator, especially in Brampton and Vaughan where parents may speak Hindi/Punjabi and want to ask hard questions in their own language.

---

## Two Modes

### Mode A — REWRITE existing page
Hero copy, labels, CTAs, sidebar text, "Working With Anu" section. Do NOT touch structure, CSS, JSON-LD schema, h1 tags, data tables, forms, or schema markup.

### Mode B — CREATE new page
Full deep research first, then build complete HTML page following the established template.

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

**After every edit:** `git add [file] && git commit && git push origin main`

---

## Mode A — Rewrite Workflow

### Step 1: Diagnose
Read the page. Identify which tier it falls in:

| Tier | Problem | Pages |
|------|---------|-------|
| 3 — Critical | Pure info dump, zero aspiration, no buyer identity | Most pages before rewrite |
| 2 — Weak | Some marketing language but generic, no tribe signal | Hub pages |
| 1 — Decent | Has positioning but misses emotional hook | Good pages needing polish |

### Step 2: Apply the 8 Copywriting Techniques

**1. Identity / Tribe Marketing**
Don't describe the neighbourhood — describe the person who lives there.
- "Where Brampton's most established families live. Not where they started — where they arrived."
- "Where Brampton's South Asian families are putting down roots in 2026"
- "You spent 30 years building. This is what you earned."

**2. PAS (Problem → Agitate → Solution)**
- Problem: buyer is stuck comparing options, paralyzed by price
- Agitate: the window is closing, others are moving, this specific thing they want is rare
- Solution: this neighbourhood solves it exactly

**3. Future Pacing**
Put the buyer in the life they're buying:
- "Saturday mornings at Eldorado Park's free outdoor pool. Sunday afternoons at Teramoto Park's cricket pitch. Monday on the 5:44 AM GO to Union."
- "No more shoveling. No more mowing. No more managing contractors."

**4. Negative Reframing (turn weaknesses into features)**
- No GO Train → "built for families with two cars and a garage — wide streets, no parking stress"
- Car-dependent → "Caledon's value proposition has strengthened with hybrid work"
- Low walk score → "designed for privacy and space, not foot traffic"
- Older homes → "1950s brick on mature lots — the kind with actual trees and actual yard"

**5. Urgency / Scarcity Signals**
Use real data, not fake urgency:
- "8-day median. 50% sell in under 10 days. You have 24 hours, not a week."
- "Greenbelt protects 80% of this land permanently. The supply that doesn't exist today won't exist in 30 years."
- "0 condos active. 32 detached homes. This inventory doesn't sit."
- "In a market that hasn't been this buyer-friendly since 2019..."

**6. Social Proof / Authority Signals**
- Fraser Institute school ratings with specifics: "#130 of 747 Ontario secondary schools"
- Homeownership %: "92% of residents own" — implies stable, committed community
- Income anchors: "median HH income $141K" — tells buyer who their neighbours are
- Heritage/history: signals permanence, not a fly-by-night subdivision

**7. Specificity over Generality**
Generic: "great schools and parks"
Specific: "Bishop Tonnos Catholic Secondary, ranked #130 of 747 Ontario secondary schools (7.6/10 Fraser)"

Generic: "convenient commute"
Specific: "5:44 AM GO to Union Station — 50 minutes door to desk"

**8. The Value Gap / Comparison Frame**
Always anchor against a more expensive comparable:
- Ancaster vs Oakville: "$500K less, same school rating"
- Brampton East vs newer Brampton: "1950s brick on mature lots, $200K under what the same square footage costs two neighbourhoods over"
- Hamilton vs Brampton: "$190K less for comparable detached"
- King City vs Kleinburg: "same estate prestige, plus a GO Train Kleinburg doesn't have"

### Step 3: Per-Page Positioning Reference

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

### Step 4: "Working With Anu" Section Template

Make it specific. Not generic agent boilerplate. Each point must be hyper-relevant to that community:

```
For [neighbourhood] specifically, Anu can help you:
- [Community-specific insight — e.g., "Navigate the 8-day Schomberg market — pre-approval strategy and 24-hour offer process"]
- [Heritage/zoning specific — e.g., "Heritage Conservation District purchase process in Kleinburg — Ontario Heritage Act implications"]
- [Language-specific — e.g., "Your parents can ask the hard questions in the language they think in — Hindi, Punjabi, or Odia"]
- [Comparison framing — e.g., "Understand exactly why Ancaster at $1.1M beats Oakville at $1.6M for your specific criteria"]
- [Data-specific — e.g., "Access comparable sales across all three Bolton sub-areas for accurate offer pricing"]
```

Always end with: `Call directly: <a href="tel:+16472005779" style="color:var(--gold);">(647) 200-5779</a>`

---

## Mode B — Create New Page Workflow

### Phase 1: Deep Research (DO NOT SKIP)

Before writing a single line of HTML, gather ALL of the following. Use WebSearch and WebFetch aggressively. Cite every statistic.

**Market Data (required):**
- Average/median sold price (all types + by type: detached, townhouse, condo)
- Year-over-year price change %
- Days on market (median)
- Sell-to-list ratio
- Number of active listings by type
- % selling above asking
- Source: Zolo, TRREB, Cornerstone (Hamilton), Honestdoor, HomesFOUND

**Demographics (required):**
- Population (2021 Census + any 2024/2026 estimates)
- Homeownership rate %
- Median household income
- Average individual income
- % families with children
- Ethnic heritage breakdown (especially Italian % — critical for King/Vaughan/Caledon)
- % immigrants (first/second generation)
- Median age
- Source: Statistics Canada 2021 Census, HoodQ, Point2Homes, WorldPopulationReview

**Schools (required):**
- All secondary schools: name, board (public/Catholic), Fraser Institute rating /10, rank out of 747 Ontario secondaries
- Special programs: IB, AP, French Immersion, SHSM
- Key elementary schools
- Any private schools within 20 min
- Source: FraserInstitute.org, CompareschoolRankings.org, school board directories

**Transit (required):**
- GO Train: line, station name, travel time to Union Station, service frequency
- If no GO: nearest station + drive time
- Highway access: which highways, drive time to downtown Toronto
- Local transit: YRT / Brampton Transit / HSR routes
- Walk score / transit score if available

**Natural Features (required):**
- Conservation areas, trails, rivers, escarpment access
- Greenbelt/Moraine/Escarpment protection status (critical for supply constraint narrative)
- Parks within community

**History (required — minimum 5 facts):**
- Founding story with specific year and person
- Key historical events (floods, fires, railway, incorporation)
- Heritage buildings/landmarks
- Indigenous territory acknowledgment
- Any unusual/distinctive historical facts (film locations, notable firsts, etc.)

**Comparison Data (required):**
- 2 comparable communities at higher price points
- 2 comparable communities at lower price points
- Build a comparison table

### Phase 2: Positioning Decision

Before writing, answer these 3 questions:
1. **Who is the buyer?** (Be specific — "South Asian family, dual income $180K, wants south-facing lot near Mandir and GO" not "families")
2. **What is the one thing this neighbourhood has that nothing else at this price does?**
3. **What would make a buyer on the fence choose this over the next best option?**

The answers become the hero-label, hero-sub, and call-block copy.

### Phase 3: Page Structure

Follow this exact structure (see any existing page as template):

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <!-- meta charset, viewport, title, meta description, canonical -->
  <!-- JSON-LD: RealEstateAgent schema -->
  <!-- JSON-LD: FAQPage schema (5 FAQs minimum) -->
  <!-- Google Fonts: Playfair Display + Inter -->
  <!-- <style> block — copy from existing page, do not modify -->
</head>
<body>
  <nav> <!-- standard nav — copy exact from existing page -->

  <div class="hero">
    <div class="breadcrumb"> <!-- Home > [Parent] > [Community] -->
    <div class="hero-label"> <!-- IDENTITY HOOK — see copywriting techniques -->
    <h1>Homes for Sale in<br/><span>[Community, Ontario]</span></h1>
    <p class="hero-sub"> <!-- PAS + future pacing + urgency — 3-5 sentences -->
    <div class="hero-stats"> <!-- 4 stats: price, population/DOM, income, homeownership -->
    <div class="hero-cta"> <!-- Call button + See Listings button -->

  <div class="page-wrap"> <!-- grid: 1fr 360px sidebar -->
    <div class="content">
      <!-- h2: [Community] Real Estate Market — 2026 -->
      <!-- price table -->
      <!-- h2: Schools -->
      <!-- school cards -->
      <!-- h2: Natural Features / Key Differentiator -->
      <!-- h2: Transit & Getting Around -->
      <!-- h2: [Community] vs [Comparable] — The Comparison -->
      <!-- compare table -->
      <!-- h2: History -->
      <!-- h2: Working With Anu Kabli in [Community] --> <!-- SEE TEMPLATE ABOVE -->
      <!-- h2: Explore More Communities -->
      <!-- explore-links -->
      <!-- h2: Frequently Asked Questions -->
      <!-- faq-items (5 minimum, match JSON-LD FAQs) -->

    <div class="sidebar">
      <!-- contact form card -->
      <!-- snapshot card (info-rows) -->
      <!-- call-block --> <!-- URGENCY CTA -->

  <footer> <!-- standard footer with cross-links — update to include new page -->

  <script> window.LEAD_MAGNET_CONFIG = {...} </script>
  <script src="/lead-magnet.js"></script>
```

### Phase 4: SEO Requirements

**Title tag:** `[Community] Homes for Sale | [Parent Market] Real Estate | Anu Kabli REALTOR®`  
**Meta description:** 150–160 chars, include: community name, avg price, key stat, Anu's phone number  
**Canonical:** `https://anukabli.com/[slug]`  
**H1:** `Homes for Sale in [Community, Ontario]` — exact format, no variation  
**Slug pattern:** `[community-name]-homes-for-sale` or `[community-name]-real-estate`  
**Internal links:** Link TO this page from parent hub page. Link FROM this page to 3-5 related pages.  
**JSON-LD FAQPage:** Minimum 5 questions. Must match the FAQ section content exactly.

### Phase 5: After Creating the Page

1. Add the new page to the parent hub's neighbourhood-grid or explore-links
2. Add the new page to the footer cross-links on related pages
3. Update the LEAD_MAGNET_CONFIG with correct neighbourhood/city/price range
4. `git add site/[new-page].html [any updated files]`
5. `git commit -m "feat(seo): add [community] neighbourhood page"`
6. `git push origin main`

---

## Batch Rewrite Process

When user says "batch rewrite all pages" or "rewrite the [region] pages":

**Priority order:**
1. Tier 3 pages first (worst conversion impact)
2. Hub pages second
3. Tier 1 pages last (Working With Anu section only)

**Process:** Edit all files, then single commit with all changes. Don't commit page-by-page.

```bash
git add site/*.html
git commit -m "feat(copy): conversion-optimized hero copy across [N] pages"
git push origin main
```

---

## Quality Checklist (before committing)

- [ ] hero-label reads as identity/positioning, not category label
- [ ] hero-sub has specific data point + buyer identity + urgency signal
- [ ] No generic phrases: "great schools", "convenient commute", "vibrant community"
- [ ] call-block uses real scarcity (days on market, inventory count, price trend) not fake urgency
- [ ] "Working With Anu" section has community-specific bullets, not boilerplate
- [ ] JSON-LD schema untouched
- [ ] h1 untouched
- [ ] Forms untouched
- [ ] CSS untouched
- [ ] All statistics cited with source-note
- [ ] Internal links updated on parent/sibling pages

---

## Anu's Differentiators (use in Working With Anu sections)

- **Multilingual:** English, Hindi, Punjabi, Odia — "your parents can ask the hard questions in the language they think in"
- **IQI Global Real Estate:** international network, relevant for buyers with overseas connections
- **Full markets:** Brampton + Vaughan + King Township + Hamilton + Caledon — can compare across regions
- **Licensed REALTOR® + mortgage broker + LLQP** — can handle the full picture: mortgage, insurance, purchase
- **Phone:** (647) 200-5779 — always include, always clickable `tel:+16472005779`
- **Response time:** "Anu responds personally within the hour" — micro-commitment, sets expectation
