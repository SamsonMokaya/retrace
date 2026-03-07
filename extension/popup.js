const DEFAULT_API_URL = 'http://localhost:8000';

document.addEventListener('DOMContentLoaded', async () => {
  const input = document.getElementById('apiUrl');
  const { apiUrl } = await chrome.storage.local.get('apiUrl');
  input.value = apiUrl || DEFAULT_API_URL;
  input.addEventListener('change', () => {
    const url = (input.value || '').trim() || DEFAULT_API_URL;
    chrome.storage.local.set({ apiUrl: url });
  });
});
