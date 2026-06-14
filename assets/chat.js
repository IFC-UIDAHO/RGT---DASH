// ForestTask chat behaviours: Enter-to-send, auto-scroll, typing indicator,
// and a SINGLE optimistic user bubble (no duplicates).
(function () {
  function $(id) { return document.getElementById(id); }
  function clickSend() { var b = $('chat-send'); if (b) b.click(); }

  function showTyping() {
    var log = $('chat-log');
    if (!log || $('typing-tmp')) return;
    var d = document.createElement('div');
    d.id = 'typing-tmp';
    d.className = 'msg assistant typing-row';
    d.innerHTML = '<div class="who">ForestTask</div>' +
      '<div class="bubble typing" aria-label="ForestTask is typing">' +
      '<span class="td"></span><span class="td"></span><span class="td"></span></div>';
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  }

  // Optimistically show the user's message the instant they send — exactly once.
  // The node is tagged '.optimistic' so it can be removed when the server's own
  // render of the message arrives (otherwise it would orphan and duplicate).
  function appendUser(text) {
    var log = $('chat-log');
    if (!log || !text || !text.trim()) return;
    if (log.querySelector('.msg.user.optimistic')) return;   // never add two
    var d = document.createElement('div');
    d.className = 'msg user optimistic';
    d.innerHTML = '<div class="who">You</div><div class="bubble"></div>';
    d.querySelector('.bubble').textContent = text.trim();
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  }

  function hasText() {
    var i = $('chat-input');
    return i && i.value && i.value.trim().length > 0;
  }

  // Enter sends (Shift+Enter = newline).
  document.addEventListener('keydown', function (e) {
    if (e.target && e.target.id === 'chat-input' && e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (hasText()) { appendUser($('chat-input').value); showTyping(); clickSend(); }
    }
  });

  // Send button / quick-prompt chips. IMPORTANT: clickSend() above fires a
  // synthetic click (e.isTrusted === false); we must NOT append again for it,
  // or the user's bubble would appear twice.
  document.addEventListener('click', function (e) {
    if (!e.target) return;
    var sendBtn = e.target.id === 'chat-send' || (e.target.closest && e.target.closest('#chat-send'));
    var chip = e.target.closest && e.target.closest('.forestask-chips .chip');
    if (sendBtn && hasText()) {
      if (e.isTrusted) appendUser($('chat-input').value);   // real user click only
      showTyping();
    } else if (chip) {
      showTyping();
    }
  });

  // Keep the log pinned to newest; once the server has rendered the real message,
  // drop the optimistic placeholder and the typing bubble so nothing duplicates.
  function attach() {
    var log = $('chat-log');
    if (!log) { setTimeout(attach, 400); return; }
    new MutationObserver(function () {
      if (log.querySelector('.msg.user:not(.optimistic)')) {
        var orphans = log.querySelectorAll('.msg.user.optimistic, #typing-tmp');
        for (var i = 0; i < orphans.length; i++) orphans[i].remove();
      }
      log.scrollTop = log.scrollHeight;
    }).observe(log, { childList: true, subtree: true });
    log.scrollTop = log.scrollHeight;
  }
  attach();
})();
