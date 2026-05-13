// background.js — Service worker
// Handles extension lifecycle, optional message passing

chrome.runtime.onInstalled.addListener(() => {
  console.log('[ReviewIntel] Extension installed');
});

// Relay messages between content script and popup if needed
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'ANALYSIS_COMPLETE') {
    // Could update badge, store results, etc.
    chrome.action.setBadgeText({ text: '✓', tabId: sender.tab.id });
    chrome.action.setBadgeBackgroundColor({ color: '#4dbe9f' });
  } else if (msg.type === 'ANALYZE_REVIEWS') {
    fetch('http://localhost:8000/analyze', {
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
      .then(data => sendResponse({ success: true, data }))
      .catch(error => sendResponse({ success: false, error: error.message }));
      
    return true; // Keep message channel open for async response
  }
  return true;
});
