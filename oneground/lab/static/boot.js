// Which page this is: one run, or a directory of them (task 041).
//
// `oneground lab` and `oneground ui` are one server, so one page is served
// for both, and the page asks which mode it is in before it loads anything
// that assumes an answer. `lab.js` boots straight into one run's ground and
// would fail against a directory; `ui.js` lists runs and would fail against
// a single workdir with no index.
//
// Asking first, rather than letting one of them fail and falling back, is the
// same rule the views follow: an absent thing is a fact to read, not an error
// to recover from.
(() => {
  'use strict';
  const TOKEN = document.querySelector(
    'meta[name="oneground-lab-token"]').content;

  function load(src) {
    const s = document.createElement('script');
    s.src = '/static/' + src + '?token=' + encodeURIComponent(TOKEN);
    document.body.appendChild(s);
  }

  function fatal(message) {
    const el = document.getElementById('fatal');
    if (el) { el.textContent = message; el.hidden = false; }
    if (window.console) console.error('oneground:', message);
  }

  fetch('/api/check?token=' + encodeURIComponent(TOKEN),
        { headers: { 'Accept': 'application/json' } })
    .then((r) => {
      if (!r.ok) throw new Error('/api/check answered ' + r.status);
      return r.json();
    })
    .then((check) => {
      window.__ONEGROUND_MODE__ = check.mode;
      if (check.mode === 'runs') {
        document.body.classList.add('mode-runs');
        load('ui.js');
        // The write half, and only here. A `oneground lab` session serves
        // one run for reading and its server refuses every write, so
        // loading the form there would put a page in front of a user that
        // cannot do the thing it offers.
        load('compose.js');
        load('jobs.js');
      } else {
        document.body.classList.add('mode-run');
        load('lab.js');
      }
    })
    .catch((e) => fatal(
      'could not ask this server what it is serving: ' + e.message));
})();
