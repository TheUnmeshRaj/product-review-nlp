// scraper.js — Amazon review scraper v2

const ReviewScraper = (() => {

  function detectProduct() {
    const url = window.location.href;
    const asinMatch = url.match(/\/(?:dp|product-reviews)\/([A-Z0-9]{10})/);
    if (!asinMatch) return null;
    const asin = asinMatch[1];
    const domainMatch = url.match(/amazon\.(in|com|co\.uk)/);
    const domain = domainMatch ? `amazon.${domainMatch[1]}` : 'amazon.in';
    const nameEl = document.getElementById('productTitle') || document.querySelector('h1.a-size-large') || document.querySelector('h1');
    const name = nameEl ? nameEl.textContent.trim() : 'Unknown Product';
    return { asin, domain, name, url };
  }

  // Extract aspect keywords like "Quality", "Battery" from page sidebar
  function extractPageAspects() {
    const labels = [];
    const selectors = [
      'span[data-testid="aspect-label"]',
      '[data-testid="aspect-label"]',
      '[data-testid="review-all-aspects"] span',
      '#customer-reviews-content .a-size-base',
    ];

    for (const selector of selectors) {
      document.querySelectorAll(selector).forEach(el => {
        const text = el.textContent.replace(/\(\d+\)/g, '').trim().toLowerCase();
        if (text && text.length < 40 && !/^(\d+|see all)/.test(text)) labels.push(text);
      });
    }

    // Fallback: older Amazon layout and adjacent aspect chips
    if (!labels.length) {
      document.querySelectorAll('#customer-reviews-content .a-size-base').forEach(el => {
        const text = el.textContent.trim().toLowerCase();
        if (text && text.length < 25 && !/^\d/.test(text)) labels.push(text);
      });
    }
    return [...new Set(labels)].slice(0, 12);
  }

  function buildReviewURL(domain, asin, opts = {}) {
    const base = `https://www.${domain}/product-reviews/${asin}`;
    const params = new URLSearchParams({
      pageNumber: opts.page || 1,
      reviewerType: 'all_reviews',
      mediaType: 'all_contents',
      formatType: 'all_formats',
    });
    if (opts.filterByStar)    params.set('filterByStar', opts.filterByStar);
    if (opts.filterByKeyword) params.set('filterByKeyword', opts.filterByKeyword);
    if (opts.sortBy)          params.set('sortBy', opts.sortBy);
    return `${base}?${params.toString()}`;
  }

  async function fetchPage(url) {
    const resp = await fetch(url, {
      credentials: 'include',
      headers: { 'Accept': 'text/html,application/xhtml+xml', 'Accept-Language': 'en-US,en;q=0.9' }
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const doc = new DOMParser().parseFromString(await resp.text(), 'text/html');
    return parseDoc(doc);
  }

  function parseDoc(doc) {
    const reviews = [];
    doc.querySelectorAll('[data-hook="review"]').forEach(el => {
      try {
        const ratingText = el.querySelector('[data-hook="review-star-rating"] .a-icon-alt, [data-hook="cmps-review-star-rating"] .a-icon-alt')?.textContent || '';
        const rating = parseFloat(ratingText) || null;
        const titleEl = el.querySelector('[data-hook="review-title"] span:not(.a-icon-alt)');
        const title = titleEl?.textContent?.trim() || '';
        const bodyEl = el.querySelector('[data-hook="review-body"] span');
        const body = bodyEl?.textContent?.trim() || '';
        if (!body) return;
        const author = el.querySelector('.a-profile-name')?.textContent?.trim() || 'Anonymous';
        const dateRaw = el.querySelector('[data-hook="review-date"]')?.textContent?.trim() || '';
        const date = dateRaw.match(/on (.+)$/)?.[1] || dateRaw;
        const verified = !!el.querySelector('[data-hook="avp-badge"]');
        const helpfulText = el.querySelector('[data-hook="helpful-vote-statement"]')?.textContent || '';
        const helpful = parseInt(helpfulText.match(/(\d+)/)?.[1] || '0');
        const id = el.getAttribute('id') || `r_${Math.random().toString(36).slice(2)}`;
        reviews.push({ id, title, body, rating, author, date, verified, helpful });
      } catch (e) {}
    });
    const hasNext = !!doc.querySelector('.a-pagination .a-last:not(.a-disabled)');
    return { reviews, hasNext };
  }

  // Holistic: all stars × both sorts × 5 pages + keyword scrapes per aspect
  async function scrapeHolistic(onProgress) {
    const product = detectProduct();
    if (!product) throw new Error('Not an Amazon product page');
    const { asin, domain } = product;
    const seen = new Set();
    const all = [];

    const push = (reviews) => {
      for (const r of reviews) {
        if (!seen.has(r.id)) { seen.add(r.id); all.push(r); }
      }
    };

    const aspects = extractPageAspects();
    console.log('[ReviewIntel] Page aspects:', aspects);

    const STARS = ['one_star','two_star','three_star','four_star','five_star'];
    const SORTS = ['helpful','recent'];

    let done = 0;
    const total = STARS.length * SORTS.length * 5 + aspects.length * 3;
    const tick = () => { done++; onProgress?.(done, total, all.length); };

    // Phase 1: star × sort × page
    for (const star of STARS) {
      for (const sort of SORTS) {
        for (let page = 1; page <= 5; page++) {
          try {
            const { reviews, hasNext } = await fetchPage(buildReviewURL(domain, asin, { filterByStar: star, sortBy: sort, page }));
            push(reviews);
            if (!hasNext || reviews.length === 0) { tick(); break; }
          } catch (e) { console.warn(`[ReviewIntel] ${star}/${sort}/p${page}:`, e.message); }
          tick();
          await sleep(500 + Math.random() * 400);
        }
      }
    }

    // Phase 2: keyword per aspect
    for (const keyword of aspects) {
      for (let page = 1; page <= 3; page++) {
        try {
          const { reviews, hasNext } = await fetchPage(buildReviewURL(domain, asin, { filterByKeyword: keyword, sortBy: 'recent', page }));
          push(reviews);
          if (!hasNext || reviews.length === 0) { tick(); break; }
        } catch (e) {}
        tick();
        await sleep(400 + Math.random() * 300);
      }
    }

    console.log(`[ReviewIntel] Done: ${all.length} unique reviews`);
    return { product, reviews: all, aspects };
  }

  async function scrapeReviews(opts = {}) {
    const product = detectProduct();
    if (!product) throw new Error('Not an Amazon product page');
    const { maxPages = 5, filterByStar, filterByKeyword, sortBy = 'recent', onProgress } = opts;
    const all = [];
    for (let page = 1; page <= maxPages; page++) {
      try {
        const { reviews, hasNext } = await fetchPage(buildReviewURL(product.domain, product.asin, { page, filterByStar, filterByKeyword, sortBy }));
        all.push(...reviews);
        onProgress?.(page, all.length);
        if (!hasNext || reviews.length === 0) break;
        await sleep(600 + Math.random() * 400);
      } catch (e) { break; }
    }
    return { product, reviews: all };
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  return { detectProduct, scrapeHolistic, scrapeReviews, extractPageAspects, buildReviewURL };
})();

window.ReviewScraper = ReviewScraper;