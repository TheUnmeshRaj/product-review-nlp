// background.js — Service worker
// Handles extension lifecycle, optional message passing

chrome.runtime.onInstalled.addListener(() => {
  console.log('[ReviewIntel] Extension installed');
});

// Relay messages between content script and popup if needed
const BACKEND_URL = 'http://localhost:8000';

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  console.log('[ReviewIntel] message received', msg?.type);

  if (msg.type === 'ANALYSIS_COMPLETE') {
    chrome.action.setBadgeText({ text: '✓', tabId: sender.tab?.id });
    chrome.action.setBadgeBackgroundColor({ color: '#4dbe9f' });
    return;
  }

  if (msg.type === 'ANALYZE_REVIEWS') {
    console.log('[ReviewIntel] ANALYZE_REVIEWS payload', msg.payload?.reviews?.length, 'reviews');
    fetch(`${BACKEND_URL}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(msg.payload)
    })
      .then(async (response) => {
        if (!response.ok) {
          const errorBody = await response.json().catch(() => ({}));
          throw new Error(errorBody.detail || `Backend error ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        console.log('[ReviewIntel] backend response OK');
        sendResponse({ success: true, data });
      })
      .catch(error => {
        console.error('[ReviewIntel] backend fetch failed', error);
        const message = error.message || 'Failed to fetch';
        sendResponse({ success: false, error: message });
      });

    return true; // Keep message channel open for async response
  }

  // Return mock price history for testing when content requests it
  if (msg.type === 'FETCH_PRICE_HISTORY') {
    const asin = msg.asin || msg.payload?.asin;
    // Mock data: generate a simple declining/increasing price history
    const now = Date.now();
    const points = [];
    let base = 1999 + (Math.floor(Math.random() * 500));
    for (let i = 0; i < 60; i++) {
      // add some noise
      base += Math.round((Math.random() - 0.4) * 20);
      if (base < 50) base = 50;
      points.push({ t: now - (60 - i) * 24 * 3600 * 1000, price: base });
    }
    sendResponse({ success: true, data: { history: points } });
    return true;
  }

  return false;
});
