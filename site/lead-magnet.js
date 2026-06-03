/**
 * Neighbourhood Lead Magnet Popup
 * Usage: include this script on any neighbourhood page.
 * Set window.LEAD_MAGNET_CONFIG before this script loads:
 *   window.LEAD_MAGNET_CONFIG = {
 *     neighbourhood: "Northwood Park",
 *     city: "Brampton",
 *     minPrice: 650000,
 *     maxPrice: 1350000
 *   };
 */
(function () {
  'use strict';

  const cfg = window.LEAD_MAGNET_CONFIG || {};
  const neighbourhood = cfg.neighbourhood || 'this neighbourhood';
  const city = cfg.city || 'Brampton';
  const minPrice = cfg.minPrice || 600000;
  const maxPrice = cfg.maxPrice || 1500000;

  /* ── Trigger: show popup after 25s OR when user scrolls 55% down ── */
  let shown = false;
  function showPopup() {
    if (shown) return;
    shown = true;
    document.getElementById('lm-overlay').style.display = 'flex';
    setTimeout(() => document.getElementById('lm-overlay').classList.add('lm-visible'), 10);
  }

  window.addEventListener('load', function () {
    setTimeout(showPopup, 25000);
    window.addEventListener('scroll', function onScroll() {
      const scrolled = window.scrollY / (document.body.scrollHeight - window.innerHeight);
      if (scrolled > 0.55) { showPopup(); window.removeEventListener('scroll', onScroll); }
    });
  });

  /* ── Inject CSS ── */
  const style = document.createElement('style');
  style.textContent = `
    #lm-overlay {
      display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.82);
      z-index: 9999; align-items: center; justify-content: center;
      padding: 20px; opacity: 0; transition: opacity .3s;
    }
    #lm-overlay.lm-visible { opacity: 1; }
    #lm-box {
      background: #141414; border: 1px solid rgba(201,168,76,0.3);
      border-radius: 8px; max-width: 520px; width: 100%; padding: 36px 32px;
      position: relative; font-family: 'Inter', sans-serif;
    }
    #lm-close {
      position: absolute; top: 14px; right: 16px; background: none; border: none;
      color: rgba(255,255,255,0.3); font-size: 22px; cursor: pointer; line-height: 1;
    }
    #lm-close:hover { color: #fff; }
    #lm-eyebrow {
      font-size: 11px; letter-spacing: .12em; color: #c9a84c;
      text-transform: uppercase; margin-bottom: 10px;
    }
    #lm-box h2 { font-family: 'Playfair Display', serif; font-size: 24px; color: #fff; margin: 0 0 6px; }
    #lm-sub { font-size: 13px; color: rgba(255,255,255,0.45); margin-bottom: 24px; }
    #lm-form label { display: block; font-size: 12px; color: rgba(255,255,255,0.5); margin-bottom: 5px; }
    #lm-form select, #lm-form input[type=text], #lm-form input[type=email], #lm-form input[type=tel] {
      width: 100%; background: #1e1e1e; border: 1px solid rgba(255,255,255,0.1);
      color: #fff; padding: 10px 12px; border-radius: 4px; font-size: 14px;
      margin-bottom: 14px; box-sizing: border-box; outline: none;
    }
    #lm-form select:focus, #lm-form input:focus { border-color: rgba(201,168,76,0.5); }
    .lm-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    #lm-submit {
      width: 100%; background: #c9a84c; color: #000; border: none; padding: 14px;
      font-size: 15px; font-weight: 700; border-radius: 4px; cursor: pointer;
      letter-spacing: .02em; margin-top: 4px; transition: background .2s;
    }
    #lm-submit:hover { background: #d4b86a; }
    #lm-submit:disabled { background: #555; color: #888; cursor: not-allowed; }
    #lm-privacy { font-size: 10px; color: rgba(255,255,255,0.2); margin-top: 10px; text-align: center; }
    /* Loading state */
    #lm-loading { display: none; text-align: center; padding: 20px 0; }
    #lm-loading .lm-spinner {
      width: 40px; height: 40px; border: 3px solid rgba(201,168,76,0.2);
      border-top-color: #c9a84c; border-radius: 50%; animation: lm-spin .8s linear infinite;
      margin: 0 auto 16px;
    }
    @keyframes lm-spin { to { transform: rotate(360deg); } }
    #lm-loading p { color: rgba(255,255,255,0.5); font-size: 13px; }
    #lm-loading .lm-dots::after { content: ''; animation: lm-dots 1.5s steps(3, end) infinite; }
    @keyframes lm-dots { 0%,100%{content:'.'} 33%{content:'..'} 66%{content:'...'} }
    /* Results state */
    #lm-results { display: none; }
    #lm-results h3 { font-family: 'Playfair Display', serif; color: #c9a84c; font-size: 18px; margin: 0 0 16px; }
    .lm-listing {
      background: #1a1a1a; border: 1px solid rgba(255,255,255,0.08);
      border-radius: 6px; padding: 16px; margin-bottom: 12px;
    }
    .lm-listing-price { font-size: 20px; font-weight: 700; color: #fff; }
    .lm-listing-addr { font-size: 13px; color: rgba(255,255,255,0.5); margin: 3px 0 8px; }
    .lm-listing-badges { display: flex; gap: 8px; flex-wrap: wrap; }
    .lm-badge {
      font-size: 11px; background: rgba(201,168,76,0.12); color: #c9a84c;
      border: 1px solid rgba(201,168,76,0.25); border-radius: 3px; padding: 3px 8px;
    }
    #lm-results-cta {
      width: 100%; background: #c41e3a; color: #fff; border: none; padding: 14px;
      font-size: 14px; font-weight: 700; border-radius: 4px; cursor: pointer; margin-top: 4px;
    }
    #lm-results-cta:hover { background: #d42040; }
    #lm-results-note { font-size: 11px; color: rgba(255,255,255,0.25); text-align: center; margin-top: 8px; }
    @media (max-width: 520px) {
      #lm-box { padding: 24px 18px; }
      #lm-box h2 { font-size: 20px; }
      .lm-row { grid-template-columns: 1fr; gap: 0; }
    }
  `;
  document.head.appendChild(style);

  /* ── Inject HTML ── */
  const priceMin = Math.round(minPrice / 100000) * 100000;
  const priceMax = Math.round(maxPrice / 100000) * 100000;

  const overlay = document.createElement('div');
  overlay.id = 'lm-overlay';
  overlay.innerHTML = `
    <div id="lm-box" role="dialog" aria-modal="true" aria-labelledby="lm-title">
      <button id="lm-close" aria-label="Close">×</button>

      <!-- Step 1: Preferences form -->
      <div id="lm-step1">
        <div id="lm-eyebrow">🏡 ${neighbourhood} · ${city}</div>
        <h2 id="lm-title">See 3 homes matched to you</h2>
        <p id="lm-sub">Tell us what you're looking for. We'll curate a shortlist from active listings in ${neighbourhood} — right now.</p>
        <form id="lm-form" novalidate>
          <div class="lm-row">
            <div>
              <label>Bedrooms</label>
              <select name="beds" required>
                <option value="">Any</option>
                <option value="2">2 bed</option>
                <option value="3">3 bed</option>
                <option value="4">4 bed</option>
                <option value="5">5+ bed</option>
              </select>
            </div>
            <div>
              <label>Home type</label>
              <select name="type">
                <option value="">Any</option>
                <option value="detached">Detached</option>
                <option value="semi-detached">Semi-detached</option>
                <option value="townhouse">Townhouse</option>
                <option value="condo">Condo</option>
              </select>
            </div>
          </div>
          <div class="lm-row">
            <div>
              <label>Min budget</label>
              <select name="min_price">
                ${priceOptions(priceMin, priceMax, 'min')}
              </select>
            </div>
            <div>
              <label>Max budget</label>
              <select name="max_price">
                ${priceOptions(priceMin, priceMax, 'max')}
              </select>
            </div>
          </div>
          <label>Must-have features (optional)</label>
          <input type="text" name="features" placeholder="e.g. basement suite, double garage, south-facing yard">
          <label>Timeline to buy</label>
          <select name="timeline">
            <option value="asap">ASAP / already looking</option>
            <option value="1-3mo">1–3 months</option>
            <option value="3-6mo">3–6 months</option>
            <option value="6mo+">Just exploring</option>
          </select>
          <label>Your email <span style="color:#c41e3a">*</span></label>
          <input type="email" name="email" placeholder="you@example.com" required>
          <div class="lm-row">
            <div>
              <label>First name <span style="color:#c41e3a">*</span></label>
              <input type="text" name="first_name" placeholder="First name" required>
            </div>
            <div>
              <label>Phone (optional)</label>
              <input type="tel" name="phone" placeholder="(647) 000-0000">
            </div>
          </div>
          <button type="submit" id="lm-submit">Show me 3 homes in ${neighbourhood} →</button>
          <p id="lm-privacy">No spam. Anu will send your curated list within minutes. <a href="/privacy" style="color:rgba(201,168,76,0.4)">Privacy Policy</a></p>
        </form>
      </div>

      <!-- Step 2: Loading / curating animation -->
      <div id="lm-loading">
        <div class="lm-spinner"></div>
        <p>Searching active listings in ${neighbourhood}<span class="lm-dots"></span></p>
        <p style="font-size:11px;color:rgba(255,255,255,0.2);margin-top:6px;">Filtering by your preferences</p>
      </div>

      <!-- Step 3: Results -->
      <div id="lm-results">
        <h3>Your ${neighbourhood} shortlist</h3>
        <div id="lm-listings-container"></div>
        <button id="lm-results-cta">📞 Talk to Anu about these homes</button>
        <p id="lm-results-note">Full MLS details + showing bookings available. Call or text (647) 200-5779.</p>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  /* ── Price option helpers ── */
  function priceOptions(min, max, which) {
    const steps = [];
    for (let p = 400000; p <= 3000000; p += (p < 1000000 ? 50000 : 100000)) steps.push(p);
    return steps.map(p => {
      const sel = (which === 'min' && p === min) || (which === 'max' && p === max) ? ' selected' : '';
      return `<option value="${p}"${sel}>${fmtPrice(p)}</option>`;
    }).join('');
  }
  function fmtPrice(p) {
    return p >= 1000000 ? `$${(p/1000000).toFixed(p%1000000===0?0:1)}M` : `$${(p/1000).toFixed(0)}K`;
  }

  /* ── Close button ── */
  document.getElementById('lm-close').addEventListener('click', function () {
    overlay.classList.remove('lm-visible');
    setTimeout(() => { overlay.style.display = 'none'; }, 300);
  });
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) document.getElementById('lm-close').click();
  });

  /* ── Form submit ── */
  document.getElementById('lm-form').addEventListener('submit', function (e) {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd.entries());

    // Basic validation
    if (!data.email || !data.first_name) {
      alert('Please enter your name and email.');
      return;
    }

    // Show loading
    document.getElementById('lm-step1').style.display = 'none';
    document.getElementById('lm-loading').style.display = 'block';

    // Call backend
    fetch('/api/curate-homes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        neighbourhood,
        city,
        ...data
      })
    })
    .then(r => r.json())
    .then(res => {
      document.getElementById('lm-loading').style.display = 'none';
      document.getElementById('lm-results').style.display = 'block';

      const container = document.getElementById('lm-listings-container');
      if (res.listings && res.listings.length) {
        container.innerHTML = res.listings.map(renderListing).join('');
      } else {
        // Fallback: no live listings found → show helpful message
        container.innerHTML = `
          <div class="lm-listing">
            <div class="lm-listing-price">Market Update</div>
            <div class="lm-listing-addr">${neighbourhood}, ${city}</div>
            <p style="font-size:13px;color:rgba(255,255,255,0.5);margin:8px 0 0;">
              Inventory in ${neighbourhood} moves fast — often 5–15 active listings at any time.
              Anu will send you a curated list matching your criteria within the hour.
            </p>
          </div>`;
      }
    })
    .catch(() => {
      // Network error fallback — still capture the lead
      document.getElementById('lm-loading').style.display = 'none';
      document.getElementById('lm-results').style.display = 'block';
      document.getElementById('lm-listings-container').innerHTML = `
        <div class="lm-listing">
          <div class="lm-listing-price">Thanks, ${data.first_name}!</div>
          <div class="lm-listing-addr">${neighbourhood} · Your shortlist is being prepared</div>
          <p style="font-size:13px;color:rgba(255,255,255,0.5);margin:8px 0 0;">
            Anu will send your curated ${neighbourhood} listings to ${data.email} within the hour.
          </p>
        </div>`;
    });
  });

  function renderListing(l) {
    const badges = [
      l.beds ? `${l.beds} bed` : null,
      l.baths ? `${l.baths} bath` : null,
      l.sqft ? `${l.sqft.toLocaleString()} sqft` : null,
      l.type || null,
      l.dom !== undefined ? `${l.dom} days on market` : null,
    ].filter(Boolean);
    return `
      <div class="lm-listing">
        <div class="lm-listing-price">${l.price ? '$' + l.price.toLocaleString() : 'Price on request'}</div>
        <div class="lm-listing-addr">${l.address || neighbourhood + ', ' + city}</div>
        <div class="lm-listing-badges">${badges.map(b => `<span class="lm-badge">${b}</span>`).join('')}</div>
        ${l.highlight ? `<p style="font-size:12px;color:rgba(255,255,255,0.4);margin:8px 0 0;">${l.highlight}</p>` : ''}
      </div>`;
  }

  /* ── Results CTA ── */
  document.getElementById('lm-results-cta').addEventListener('click', function () {
    window.location.href = 'tel:+16472005779';
  });

})();
