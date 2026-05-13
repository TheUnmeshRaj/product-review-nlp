// content.js — Direct in-page injector for Amazon product pages

(async () => {
  await waitForScraper();

  const product = await waitForProduct();
  if (!product) return;

  injectTriggerButton(product);
})();

const BACKEND_URL = 'http://localhost:8000';
const MAX_REVIEWS = 300;
let activeSessionId = 0;

async function waitForScraper(timeoutMs = 8000) {
  if (window.ReviewScraper) return;

  const startedAt = Date.now();
  while (!window.ReviewScraper && Date.now() - startedAt < timeoutMs) {
    await sleep(100);
  }
}

async function waitForProduct(timeoutMs = 8000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const product = getProductFromPage();
    if (product) return product;
    await sleep(250);
  }
  return getProductFromPage();
}

function getProductFromPage() {
  const detectProduct = window.ReviewScraper?.detectProduct?.bind(window.ReviewScraper);
  const product = detectProduct?.();
  if (product) return product;

  const asin = getAsinFromUrl();
  if (!asin) return null;

  const titleEl = document.getElementById('productTitle') || document.querySelector('h1 span') || document.querySelector('h1');
  const name = titleEl?.textContent?.trim() || 'Unknown Product';
  const domainMatch = location.hostname.match(/amazon\.(in|com|co\.uk)/i);
  const domain = domainMatch ? `amazon.${domainMatch[1].toLowerCase()}` : location.hostname;

  return {
    asin,
    domain,
    name,
    url: location.href,
  };
}

function getAsinFromUrl() {
  const patterns = [
    /\/dp\/([A-Z0-9]{10})(?:[/?#]|$)/i,
    /\/gp\/product\/([A-Z0-9]{10})(?:[/?#]|$)/i,
    /\/product-reviews\/([A-Z0-9]{10})(?:[/?#]|$)/i,
  ];

  for (const pattern of patterns) {
    const match = location.href.match(pattern);
    if (match?.[1]) return match[1].toUpperCase();
  }

  return null;
}

function injectTriggerButton(product) {
  if (document.getElementById('review-intel-btn')) return;

  // Inject Google Fonts for modern typography
  if (!document.getElementById('ri-fonts')) {
    const fontLink = document.createElement('link');
    fontLink.id = 'ri-fonts';
    fontLink.rel = 'stylesheet';
    fontLink.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap';
    document.head.appendChild(fontLink);
  }

  const btn = document.createElement('div');
  btn.id = 'review-intel-btn';
  btn.setAttribute('role', 'button');
  btn.setAttribute('tabindex', '0');
  btn.setAttribute('aria-label', 'Analyze Amazon reviews');
  btn.innerHTML = `
    <div id="ri-fab">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12c-2.4 0-4.6-1.1-6.2-3.1C13.2 6.9 12 4.7 12 2c0 2.7-1.2 4.9-2.8 6.9C7.6 10.9 5.4 12 3 12c2.4 0 4.6 1.1 6.2 3.1 1.6 2 2.8 4.2 2.8 6.9 0-2.7 1.2-4.9 2.8-6.9 1.6-2 3.8-3.1 6.2-3.1z"/>
      </svg>
      <span>Analyze Reviews</span>
    </div>
  `;

  const launch = () => mountInlineIntel(product);
  btn.addEventListener('click', launch);
  btn.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      launch();
    }
  });

  const target =
    document.getElementById('averageCustomerReviews') ||
    document.getElementById('reviews-medley') ||
    document.querySelector('#reviewsMedley') ||
    document.body;

  target.parentNode?.insertBefore(btn, target) || document.body.appendChild(btn);
}

function mountInlineIntel(product) {
  document.getElementById('review-intel-overlay')?.remove();

  const shell = document.createElement('section');
  shell.id = 'review-intel-overlay';
  shell.setAttribute('aria-label', 'Review Intel analysis section');
  shell.innerHTML = buildInlineHTML(product);

  const anchor = getInlineAnchor();
  if (anchor?.parentNode) {
    anchor.parentNode.insertBefore(shell, anchor);
  } else {
    document.body.appendChild(shell);
  }

  shell.querySelector('#ri-close')?.addEventListener('click', () => closeInlineIntel(shell));

  runPipeline(product, shell).catch(() => {});
}

function closeInlineIntel(shell) {
  activeSessionId++;
  shell?.remove();
}

function getInlineAnchor() {
  return (
    document.getElementById('reviews-medley') ||
    document.getElementById('averageCustomerReviews') ||
    document.getElementById('customerReviews') ||
    document.querySelector('#reviewsMedley') ||
    document.querySelector('#productDetails_feature_div') ||
    document.querySelector('#feature-bullets') ||
    document.body
  );
}

function buildInlineHTML(product) {
  return `
    <div id="ri-panel" class="ri-inline-shell">
      <div id="ri-header" class="ri-inline-header">
        <div>
          <div id="ri-title">Review Intelligence</div>
          <div id="ri-subtitle">${escHtml(truncate(product.name, 76))}</div>
        </div>
        <button id="ri-close" class="ri-inline-close" type="button" aria-label="Remove analysis section">Hide</button>
      </div>
      <div id="ri-status" class="ri-status ri-status--scraping">Preparing analysis…</div>
      <div id="ri-dashboard" style="display:none"></div>
    </div>
  `;
}

async function runPipeline(product, overlay) {
  const sessionId = ++activeSessionId;
  const setStatusSafe = (type, message) => {
    if (sessionId !== activeSessionId) return false;
    setStatus(overlay, type, message);
    return true;
  };

  if (!setStatusSafe('scraping', `Holistically scraping reviews for ${product.name}…`)) return;

  let scraped;
  try {
    scraped = await window.ReviewScraper.scrapeHolistic(() => {
      setStatusSafe('scraping', 'Scraping reviews…');
    });
  } catch (error) {
    setStatusSafe('error', `Scraping failed: ${error.message}`);
    return;
  }

  const uniqueReviews = dedupeReviews(scraped.reviews || []).slice(0, MAX_REVIEWS);
  if (!uniqueReviews.length) {
    setStatusSafe('error', 'No reviews found. Open an Amazon product page with visible review data.');
    return;
  }

  if (!setStatusSafe('analyzing', `Analyzing holistic reviews with NLP…`)) return;

  let analytics;
  try {
    const response = await chrome.runtime.sendMessage({
      type: 'ANALYZE_REVIEWS',
      payload: { product, reviews: uniqueReviews }
    });

    if (!response || !response.success) {
      throw new Error(response?.error || 'No response from background script');
    }

    analytics = response.data;
  } catch (error) {
    setStatusSafe('error', `Backend error: ${error.message}. Is FastAPI running on :8000?`);
    return;
  }

  if (sessionId !== activeSessionId) return;

  renderDashboard(overlay, analytics, { product, reviews: uniqueReviews, aspects: scraped.aspects || [] });
  chrome.runtime?.sendMessage?.({ type: 'ANALYSIS_COMPLETE', asin: product.asin });
}

function setStatus(overlay, type, message) {
  const statusEl = overlay.querySelector('#ri-status');
  if (!statusEl) return;
  statusEl.className = `ri-status ri-status--${type}`;
  statusEl.textContent = message;
}

function renderDashboard(overlay, analytics, scraped) {
  const status = overlay.querySelector('#ri-status');
  if (status) status.style.display = 'none';

  const dash = overlay.querySelector('#ri-dashboard');
  if (!dash) return;
  dash.style.display = 'block';

  const total = Math.max(analytics.total_reviews || 0, 1);
  const sentimentDistribution = analytics.sentiment_distribution || { positive: 0, neutral: 0, negative: 0 };
  const posPct = Math.round(sentimentDistribution.positive / total * 100);
  const negPct = Math.round(sentimentDistribution.negative / total * 100);
  const neuPct = Math.max(0, 100 - posPct - negPct);
  const reviewStats = computeReviewStats(scraped.reviews || []);
  const topStars = summarizeStars(reviewStats.stars);

  // Build praised/complained features
  const aspects = analytics.aspect_sentiments || {};
  const praised = Object.entries(aspects)
    .filter(([_, scores]) => (scores?.positive || 0) > 60)
    .sort((a, b) => (b[1]?.positive || 0) - (a[1]?.positive || 0));
  const complained = Object.entries(aspects)
    .filter(([_, scores]) => (scores?.negative || 0) > 40)
    .sort((a, b) => (b[1]?.negative || 0) - (a[1]?.negative || 0));

  dash.innerHTML = `
    <!-- TOP ANCHOR SECTION: Large 4-column grid with main charts -->
    <div class="ri-anchor-section">
      <div class="ri-anchor-grid">
        <section class="ri-anchor-card">
          <div class="ri-section-title">Overall Sentiment</div>
          ${renderDonutChart({ positive: sentimentDistribution.positive || 0, neutral: sentimentDistribution.neutral || 0, negative: sentimentDistribution.negative || 0 })}
        </section>
        <section class="ri-anchor-card">
          <div class="ri-section-title">Star Distribution</div>
          ${renderStarBars(reviewStats.stars, topStars)}
        </section>
        <section class="ri-anchor-card">
          <div class="ri-section-title">Sentiment Breakdown</div>
          ${renderSentimentTrendChart(sentimentDistribution)}
        </section>
        <section class="ri-anchor-card">
          <div class="ri-section-title">Top Keywords</div>
          ${renderKeywordCloud(analytics.keywords || [])}
        </section>
      </div>
    </div>

    <!-- KEY METRICS STRIP -->
    <div class="ri-metrics">
      <div class="ri-metric">
        <div class="ri-metric-label">Reviews</div>
        <div class="ri-metric-val">${analytics.total_reviews || scraped.reviews.length}</div>
      </div>
      <div class="ri-metric">
        <div class="ri-metric-label">Positive</div>
        <div class="ri-metric-val ri-green">${posPct}%</div>
      </div>
      <div class="ri-metric">
        <div class="ri-metric-label">Negative</div>
        <div class="ri-metric-val ri-red">${negPct}%</div>
      </div>
      <div class="ri-metric">
        <div class="ri-metric-label">Neutral</div>
        <div class="ri-metric-val ri-gray">${neuPct}%</div>
      </div>
      <div class="ri-metric">
        <div class="ri-metric-label">Peak Rating</div>
        <div class="ri-metric-val ri-small">${topStars}★</div>
      </div>
    </div>

    <!-- PRAISED FEATURES SECTION -->
    ${praised.length ? `
      <div class="ri-section">
        <div class="ri-section-title">Praised Features (${praised.length})</div>
        <div class="ri-feature-grid">
          ${praised.map(([feature, scores]) => renderFeatureCard('praised', feature, scores, scraped.reviews, analytics.reviews)).join('')}
        </div>
      </div>
    ` : ''}

    <!-- COMPLAINED FEATURES SECTION -->
    ${complained.length ? `
      <div class="ri-section">
        <div class="ri-section-title">Complained Features (${complained.length})</div>
        <div class="ri-feature-grid">
          ${complained.map(([feature, scores]) => renderFeatureCard('complained', feature, scores, scraped.reviews, analytics.reviews)).join('')}
        </div>
      </div>
    ` : ''}

    <!-- DEEPER INSIGHTS -->
    <div class="ri-section">
      <div class="ri-section-title">Insights & Summary</div>
      <div class="ri-insights-container">
        <div class="ri-insight-box">
          <strong>Verdict:</strong> ${escHtml(analytics.verdict || 'Product analysis complete.')}
        </div>
        <div class="ri-insight-box">
          <strong>Summary:</strong> ${escHtml(analytics.summary || 'No detailed summary available.')}
        </div>
        ${analytics.common_complaints?.length ? `
          <div class="ri-insight-box">
            <strong>Common Complaints:</strong>
            <div class="ri-tags">
              ${analytics.common_complaints.map(item => `<span class="ri-tag ri-tag-neg">${escHtml(item)}</span>`).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    </div>

  `;

  overlay.querySelector('#ri-close')?.focus?.();
}

function renderSentimentTrendChart(sentimentDistribution) {
  const total = Math.max(1, (sentimentDistribution.positive || 0) + (sentimentDistribution.neutral || 0) + (sentimentDistribution.negative || 0));
  const posPct = Math.round((sentimentDistribution.positive || 0) / total * 100);
  const neuPct = Math.round((sentimentDistribution.neutral || 0) / total * 100);
  const negPct = Math.max(0, 100 - posPct - neuPct);

  const bars = [
    { label: 'Positive', pct: posPct, count: sentimentDistribution.positive || 0, color: 'green' },
    { label: 'Neutral', pct: neuPct, count: sentimentDistribution.neutral || 0, color: 'gray' },
    { label: 'Negative', pct: negPct, count: sentimentDistribution.negative || 0, color: 'red' }
  ];

  return `
    <div class="ri-sentiment-trend">
      ${bars.map(bar => `
        <div class="ri-trend-bar-group">
          <div class="ri-trend-label">${bar.label}</div>
          <div class="ri-trend-container">
            <div class="ri-trend-fill ri-trend-${bar.color}" style="width:${Math.max(5, bar.pct)}%" aria-hidden="true"></div>
          </div>
          <div class="ri-trend-stat">${bar.pct}% (${bar.count})</div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderKeywordCloud(keywords) {
  if (!keywords?.length) return '<div class="ri-empty">No keywords extracted.</div>';

  const sorted = keywords.slice(0, 12);
  const max = sorted.length;
  const sizes = sorted.map((_, i) => {
    const weight = Math.floor(((max - i) / max) * 100);
    return Math.max(0.8, Math.min(1.4, weight / 100));
  });

  return `
    <div class="ri-keyword-cloud">
      ${sorted.map((kw, i) => `<span class="ri-keyword" style="font-size:${sizes[i]}rem">${escHtml(kw)}</span>`).join(' ')}
    </div>
  `;
}

function renderFeatureCard(type, feature, scores, allReviews, backendReviews) {
  const positive = clampPercent(scores?.positive || 0);
  const negative = clampPercent(scores?.negative || 0);
  const total = Math.max(1, (scores?.total || 1));
  const isPraised = type === 'praised';
  
  // Find reviews mentioning this feature
  const mentionCount = (backendReviews || allReviews || []).filter(r => {
    if (!Array.isArray(r.aspects)) return false;
    return r.aspects.some(a => a.toLowerCase() === feature.toLowerCase());
  }).length;

  // Get a sample of positive/negative reviews for this aspect
  const sample = (backendReviews || allReviews || [])
    .filter(r => Array.isArray(r.aspects) && r.aspects.some(a => a.toLowerCase() === feature.toLowerCase()))
    .slice(0, 2);

  const sampleText = sample.length ? truncate(sample[0].body || sample[0].title || '', 120) : 'No sample available';

  return `
    <div class="ri-feature-card ri-feature-${isPraised ? 'praised' : 'complained'}">
      <div class="ri-feature-header">
        <div class="ri-feature-name">${escHtml(feature)}</div>
        <div class="ri-feature-badge ${isPraised ? 'ri-badge-praised' : 'ri-badge-complained'}">
          ${isPraised ? '👍' : '👎'}
        </div>
      </div>

      <!-- Chart 1: Sentiment Bar -->
      <div class="ri-feature-chart">
        <div class="ri-micro-title">Sentiment Split</div>
        <div class="ri-feature-bar">
          <div class="ri-feature-bar-pos" style="width:${positive}%" title="Positive ${positive}%"></div>
          <div class="ri-feature-bar-neg" style="width:${negative}%" title="Negative ${negative}%"></div>
        </div>
        <div class="ri-feature-pct">${isPraised ? positive : negative}% ${isPraised ? 'positive' : 'negative'}</div>
      </div>

      <!-- Chart 2: Mention Count & Stats -->
      <div class="ri-feature-stats">
        <div class="ri-stat-item">
          <div class="ri-stat-label">Mentions</div>
          <div class="ri-stat-value">${mentionCount}</div>
        </div>
        <div class="ri-stat-item">
          <div class="ri-stat-label">Score</div>
          <div class="ri-stat-value">${total} reviews</div>
        </div>
      </div>

      <!-- Chart 3: Sample Review Snippet -->
      ${sample.length ? `
        <div class="ri-feature-sample">
          <div class="ri-micro-title">Sample</div>
          <div class="ri-sample-text" title="${escHtml(sample[0].body || sample[0].title || '')}">"${escHtml(sampleText)}…"</div>
        </div>
      ` : ''}
    </div>
  `;
}

function renderDonutChart(counts) {
  const total = Math.max(1, (counts.positive || 0) + (counts.neutral || 0) + (counts.negative || 0));
  const posPct = Math.round((counts.positive || 0) / total * 100);
  const neuPct = Math.round((counts.neutral || 0) / total * 100);
  const negPct = Math.max(0, 100 - posPct - neuPct);

  return `
    <div class="ri-donut-wrap">
      <div class="ri-donut" style="--ri-donut-positive:${posPct}%;--ri-donut-neutral:${neuPct}%;--ri-donut-negative:${negPct}%" aria-hidden="true">
        <div class="ri-donut-center">
          <div class="ri-donut-label">${posPct}%</div>
          <div class="ri-donut-sub">positive</div>
        </div>
      </div>
      <div class="ri-donut-legend">
        <div><span class="ri-dot ri-dot-green"></span>Positive ${counts.positive || 0}</div>
        <div><span class="ri-dot ri-dot-gray"></span>Neutral ${counts.neutral || 0}</div>
        <div><span class="ri-dot ri-dot-red"></span>Negative ${counts.negative || 0}</div>
      </div>
    </div>
  `;
}

function renderStarBars(stars, topStars) {
  const rows = [5, 4, 3, 2, 1].map(star => {
    const value = stars[star] || 0;
    const max = Math.max(...Object.values(stars), 1);
    const width = Math.max(4, Math.round((value / max) * 100));
    return `
      <div class="ri-star-row">
        <span class="ri-star-label">${star}★</span>
        <div class="ri-star-track"><span class="ri-star-fill" style="width:${width}%"></span></div>
        <span class="ri-star-value">${value}${topStars === star ? ' • peak' : ''}</span>
      </div>
    `;
  }).join('');

  return `<div class="ri-star-bars">${rows}</div>`;
}

function computeReviewStats(reviews) {
  const stars = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  for (const review of reviews) {
    const rating = Math.round(Number(review.rating) || 0);
    if (rating >= 1 && rating <= 5) stars[rating] += 1;
  }
  return { stars };
}

function summarizeStars(stars) {
  let bestStar = 5;
  let bestValue = -1;
  for (const [key, value] of Object.entries(stars || {})) {
    if (value > bestValue) {
      bestValue = value;
      bestStar = Number(key);
    }
  }
  return bestStar;
}

function renderAspectBars(aspects) {
  const entries = Object.entries(aspects || {});
  if (!entries.length) return '<div class="ri-empty">No aspects extracted.</div>';

  return entries.map(([feature, scores]) => {
    const positive = clampPercent(scores?.positive || 0);
    const negative = clampPercent(scores?.negative || 0);
    return `
      <div class="ri-aspect-row">
        <div class="ri-aspect-name" title="${escHtml(feature)}">${escHtml(feature)}</div>
        <div class="ri-bar-track">
          <div class="ri-bar-pos" style="width:${positive}%"></div>
          <div class="ri-bar-neg" style="width:${negative}%"></div>
        </div>
        <div class="ri-bar-pct">${positive}%</div>
      </div>
    `;
  }).join('');
}

function renderReviewCards(reviews) {
  if (!reviews?.length) return '<div class="ri-empty">No reviews.</div>';

  return reviews.slice(0, 30).map(review => {
    const sentiment = (review.sentiment || 'neutral').slice(0, 3);
    const body = review.body || '';
    const title = review.title || '';
    const aspects = Array.isArray(review.aspects) ? review.aspects : [];

    return `
      <article class="ri-rcard">
        <div class="ri-rcard-top">
          <span class="ri-badge ri-badge-${sentiment}">${escHtml(review.sentiment || 'neutral')}</span>
          <span class="ri-rcard-meta">${escHtml(review.author || 'Anonymous')} · ${escHtml(review.date || '')}${review.verified ? ' · verified' : ''}</span>
        </div>
        ${title ? `<div class="ri-rcard-title">${escHtml(title)}</div>` : ''}
        <div class="ri-rcard-body">${escHtml(truncate(body, 220))}${body.length > 220 ? '…' : ''}</div>
        ${aspects.length ? `<div class="ri-tags">${aspects.map(aspect => `<span class="ri-tag">${escHtml(aspect)}</span>`).join('')}</div>` : ''}
      </article>
    `;
  }).join('');
}

function dedupeReviews(reviews) {
  const seen = new Set();
  const unique = [];

  for (const review of reviews) {
    const signature = [
      review.id || '',
      review.title || '',
      review.body || '',
      review.author || '',
      review.date || '',
    ].join('|');

    if (seen.has(signature)) continue;
    seen.add(signature);
    unique.push(review);
  }

  return unique;
}

function clampPercent(value) {
  const num = Number(value) || 0;
  return Math.max(0, Math.min(100, Math.round(num)));
}

function truncate(text, limit) {
  const value = String(text || '');
  return value.length > limit ? `${value.slice(0, limit - 1).trimEnd()}` : value;
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}