// ForestTask chat behaviours (minimal): Enter-to-send and auto-scroll.
// The optimistic user bubble and the typing indicator are now Dash-managed
// (#chat-pending, driven by clientside callbacks), so there is no DOM
// manipulation, MutationObserver-removal, or duplicate-bubble logic here.
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }

  // Enter sends (Shift+Enter = newline).
  document.addEventListener("keydown", function (e) {
    if (e.target && e.target.id === "chat-input" && e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      var input = $("chat-input"), send = $("chat-send");
      if (input && input.value && input.value.trim() && send) send.click();
    }
  });

  // Keep the conversation pinned to the newest message / the pending bubbles.
  function pin() { var log = $("chat-log"); if (log) log.scrollTop = log.scrollHeight; }
  function attach() {
    var log = $("chat-log");
    if (!log) { setTimeout(attach, 400); return; }
    new MutationObserver(pin).observe(log, { childList: true, subtree: true });
    var pending = $("chat-pending");
    if (pending) {
      new MutationObserver(pin).observe(pending, { childList: true, subtree: true, attributes: true });
    }
    pin();
  }
  attach();
})();
