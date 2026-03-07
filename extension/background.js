const DEFAULT_API_URL = 'http://localhost:8000';

async function getApiUrl() {
  const { apiUrl } = await chrome.storage.local.get('apiUrl');
  return apiUrl || DEFAULT_API_URL;
}

function isTrackableUrl(url) {
  if (!url || typeof url !== 'string') return false;
  return url.startsWith('http://') || url.startsWith('https://');
}

function toISOTimestamp() {
  return new Date().toISOString().slice(0, 19);
}

async function sendPageVisit(tabId, url, title) {
  const base = await getApiUrl();
  const payload = {
    type: 'page_visit',
    url: url || '',
    title: (title && title.trim()) || null,
    timestamp: toISOTimestamp(),
  };
  try {
    const res = await fetch(`${base}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      console.log('[Retrace] page_visit sent:', payload.url);
    } else {
      console.warn('[Retrace] POST /events failed:', res.status, await res.text());
    }
  } catch (err) {
    console.warn('[Retrace] Failed to send page_visit:', err.message);
  }
}

async function sendHighlight(url, text) {
  if (!url || !text || !text.trim()) return;
  const base = await getApiUrl();
  const payload = {
    type: 'highlight',
    url: url,
    text: text.trim(),
    timestamp: toISOTimestamp(),
  };
  try {
    const res = await fetch(`${base}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      console.log('[Retrace] highlight sent:', text.trim().slice(0, 50) + '...');
    } else {
      console.warn('[Retrace] POST /events (highlight) failed:', res.status);
    }
  } catch (err) {
    console.warn('[Retrace] Failed to send highlight:', err.message);
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'highlight' && msg.url && msg.text) {
    sendHighlight(msg.url, msg.text).then(() => sendResponse({ ok: true })).catch(() => sendResponse({ ok: false }));
  }
  return true;
});

chrome.contextMenus.create({
  id: 'retrace-save-highlight',
  title: 'Save to Retrace',
  contexts: ['selection'],
});

chrome.contextMenus.onClicked.addListener(async (_info, tab) => {
  if (tab?.id == null) return;
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const sel = window.getSelection();
        return { text: (sel && sel.toString().trim()) || '', url: window.location.href };
      },
    });
    if (result && result.text) await sendHighlight(result.url, result.text);
  } catch (e) {
    console.warn('[Retrace] context menu failed:', e.message);
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;
  const url = tab?.url || changeInfo?.url;
  if (!url || !isTrackableUrl(url)) return;
  await sendPageVisit(tabId, url, tab?.title);
});
