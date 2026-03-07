(function () {
  'use strict';

  // Keyboard shortcut: Ctrl+Shift+H (Windows/Linux) or Cmd+Shift+H (Mac)
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'H' || e.key === 'h')) {
      var sel = window.getSelection();
      var text = (sel && sel.toString().trim()) || '';
      if (text.length > 0) {
        e.preventDefault();
        chrome.runtime.sendMessage({
          type: 'highlight',
          url: window.location.href,
          text: text,
        }).catch(function () {});
      }
    }
  });
})();
