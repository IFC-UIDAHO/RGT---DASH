// =============================================================================
// loadbridge.js — coordinates the loading film (iframe) with the report reveal.
// The film keeps playing in an overlay over #report-body; we reveal the report
// when: the user clicks Skip, OR the film finishes one full play AND the report
// is ready, OR a failsafe timeout. Plain JS — no Dash callback dependency.
// =============================================================================
(function () {
  "use strict";
  var ready = false, failsafe = null;
  function $(id){ return document.getElementById(id); }
  function frame(){ var l = $('report-loading'); return l ? l.querySelector('iframe') : null; }
  function tell(msg){ var f = frame(); try { if (f && f.contentWindow) f.contentWindow.postMessage(msg, '*'); } catch(e){} }

  function reveal(){
    var skip = $('report-skip');
    if (skip) skip.click();                       // routes through Dash -> adds 'revealed'
    var v = $('report-view');                     // immediate visual fallback
    if (v && v.className.indexOf('revealed') < 0) v.className += ' revealed';
  }

  function onReady(){
    if (ready) return;
    ready = true;
    tell({ type: 'rgt-ready' });                  // let the film know it can wrap up
    clearTimeout(failsafe);
    failsafe = setTimeout(reveal, 45000);         // backstop so the report always shows
  }

  function watch(id, cb){
    var n = $(id);
    if (!n) { setTimeout(function(){ watch(id, cb); }, 400); return; }
    try { new MutationObserver(cb).observe(n, { childList: true }); } catch(e){}
  }

  // report finished building -> #report-body receives children
  watch('report-body', function(){ var b = $('report-body'); if (b && b.children.length > 0) onReady(); });
  // a new report started -> #report-loading gets a fresh iframe -> reset
  watch('report-loading', function(){ ready = false; clearTimeout(failsafe); });

  // messages from the film iframe
  window.addEventListener('message', function (e) {
    var d = e && e.data;
    if (!d || typeof d !== 'object') return;
    if (d.type === 'rgt-reveal') reveal();
    else if (d.type === 'rgt-hello' && ready) tell({ type: 'rgt-ready' });
  });
})();
