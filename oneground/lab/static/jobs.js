// The jobs page: what has run, what is running, and what it left behind.
//
// Task 046 steps 3 and 4. Its own file for the same reason `compose.js` is:
// `ui.js` opens by saying there is no POST in it, and the read half and the
// write half are kept apart in the code and in the page.
//
// WHY THIS PAGE TALKS TO TWO SERVERS
// ----------------------------------
// It reads from the lab server and it *asks* the supervisor. That is not an
// accident of layout, it is the shape of a ruling: the lab server's own
// header has promised since it was written that it makes no request of its
// own, and it has no write path. So it cannot enqueue a job and it will not
// forward one. The page is told where the supervisor is and does the asking
// itself, with the supervisor's token.
//
// The supervisor permits exactly one origin -- this page's -- and the token
// is still required on every request. **CORS says which page the browser
// will let read a reply; it says nothing about who may ask.** If the next
// person here starts treating the allowance as authentication, that is the
// sentence they should meet first.
//
// WHAT IS DRAWN AND WHAT IS NOT
// -----------------------------
//   * a refusal is shown verbatim, never rephrased and never summarised;
//   * `why` is shown beside every terminal state, because a reader of one
//     job does not have the workdir and cannot re-run the decision;
//   * a cancelled job's outputs are marked partial, from the record rather
//     than inferred from the state;
//   * no supervisor running is a fact the page states, not a button that
//     fails when pressed.
(() => {
  'use strict';
  const TOKEN = document.querySelector(
    'meta[name="oneground-lab-token"]').content;

  let sup = null;          // where the supervisor is, or why it is not
  let spec = null;         // stages, and what is never a job
  let seq = 0;             // newest refresh wins
  let timer = null;

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  async function get(path, params) {
    const q = new URLSearchParams(params || {});
    q.set('token', TOKEN);
    const r = await fetch(path + '?' + q.toString(),
                          { headers: { 'Accept': 'application/json' } });
    const body = await r.json().catch(() => ({ error: 'unreadable answer' }));
    if (!r.ok) throw new Error(body.error || (path + ' answered ' + r.status));
    return body;
  }

  // The supervisor, directly. Not through the lab server, which makes no
  // request of its own.
  async function ask(path, body) {
    if (!sup || !sup.running) throw new Error(sup ? sup.why : 'no supervisor');
    const r = await fetch(sup.url + path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Oneground-Supervisor-Token': sup.token,
      },
      body: JSON.stringify(body),
    });
    const out = await r.json().catch(() => ({
      error: 'the supervisor answered ' + r.status + ' and no readable body',
    }));
    if (!r.ok) { out.__status = r.status; throw out; }
    return out;
  }

  // --- drawing ------------------------------------------------------------
  function stateChip(job) {
    const chip = el('span', 'state state-' + job.state, job.state);
    if (job.partial) chip.appendChild(el('span', 'partial', ' partial'));
    return chip;
  }

  function jobRow(job) {
    const row = el('section', 'job');
    row.dataset.job = job.id;

    const head = el('div', 'job-head');
    head.appendChild(el('span', 'job-stage', job.stage));
    head.appendChild(stateChip(job));
    head.appendChild(el('span', 'job-when',
      job.ended || job.started || 'not started'));
    row.appendChild(head);

    // The invocation, which is what everything else hangs off: it is what
    // the receipts name and what a replay re-runs.
    const inv = el('pre', 'job-invocation',
      'oneground ' + (job.invocation || []).join(' '));
    row.appendChild(inv);

    // Why it is in the state it is in. Shown for every terminal job, not
    // only the interesting ones: a state without its reason hands over the
    // conclusion and keeps the evidence.
    if (job.why) row.appendChild(el('p', 'job-why', job.why));

    if (job.refusal) {
      // Verbatim. The most useful thing the tool produces, written once, in
      // the CLI, on purpose.
      const box = el('div', 'refusal');
      box.appendChild(el('p', 'refusal-what', job.refusal));
      row.appendChild(box);
    }

    const foot = el('div', 'job-foot');
    if (job.exit_code !== null && job.exit_code !== undefined) {
      foot.appendChild(el('span', 'job-exit', 'exit ' + job.exit_code));
    }
    if (job.build) foot.appendChild(el('span', 'job-build', job.build));

    const log = el('button', 'linkish', 'log');
    log.type = 'button';
    log.addEventListener('click', () => { showLog(job, row); });
    foot.appendChild(log);

    const live = job.state === 'queued' || job.state === 'running';
    if (live && sup && sup.running) {
      const stop = el('button', 'linkish', 'cancel');
      stop.type = 'button';
      stop.addEventListener('click', () => { cancel(job); });
      foot.appendChild(stop);
    }
    row.appendChild(foot);
    return row;
  }

  async function showLog(job, row) {
    const existing = row.querySelector('.job-log');
    if (existing) { existing.remove(); return; }
    const pre = el('pre', 'job-log', 'reading…');
    row.appendChild(pre);
    try {
      const out = await get('/api/jobs/log', { id: job.id });
      pre.textContent = out.text === null ? out.absent : out.text;
      if (out.text === null) pre.classList.add('absent');
    } catch (e) {
      pre.textContent = e.message;
    }
  }

  async function cancel(job) {
    try {
      await ask('/cancel', { id: job.id });
    } catch (e) {
      fail(e.refusal || e.error || String(e));
    }
    await refresh();
  }

  async function run(stage) {
    // The invocation is built here and recorded whole. `runs/<name>` is the
    // directory this session serves, which the supervisor is already
    // pointed at.
    try {
      await ask('/enqueue', { stage: stage, invocation: [stage, '.'] });
    } catch (e) {
      fail(e.refusal || e.error || String(e));
    }
    await refresh();
  }

  function fail(message) {
    const box = document.getElementById('jobs-error');
    if (!box) return;
    box.hidden = false;
    box.textContent = '';
    box.appendChild(el('p', 'refusal-what', message));
  }

  function clearFail() {
    const box = document.getElementById('jobs-error');
    if (box) { box.hidden = true; box.textContent = ''; }
  }

  // The supervisor's absence, stated. Not a disabled button and not a
  // button that fails: a sentence saying what is not running and what that
  // means for this page.
  function supervisorNote() {
    const note = el('section', 'supervisor-note');
    if (sup && sup.running && sup.same_build) {
      note.appendChild(el('p', 'note',
        'A supervisor is running and this page speaks to it directly. '
        + 'The server that drew this page starts nothing and writes '
        + 'nothing.'));
      return note;
    }
    note.classList.add('absent');
    note.appendChild(el('h3', null,
      sup && sup.running ? 'The supervisor is running a different build'
                         : 'No supervisor is running'));
    note.appendChild(el('p', 'note', (sup && sup.why)
      || 'nothing can be started from here'));
    if (!(sup && sup.running)) {
      note.appendChild(el('p', 'note',
        'Jobs already recorded are listed below and are read from the '
        + 'directory, so what has run is still visible.'));
    }
    return note;
  }

  function runner() {
    const box = el('section', 'runner');
    box.appendChild(el('h3', null, 'Start a stage'));
    const row = el('div', 'runner-row');
    (spec.stages || []).forEach((stage) => {
      const b = el('button', 'door', stage);
      b.type = 'button';
      b.disabled = !(sup && sup.running);
      b.addEventListener('click', () => { run(stage); });
      row.appendChild(b);
    });
    box.appendChild(row);

    // What is never a job, named with the ruling rather than absent from
    // the row. Someone who finds `pod up` missing assumes an omission.
    (spec.not_a_job || []).forEach((n) => {
      const p = el('p', 'note');
      p.appendChild(el('code', null, 'oneground ' + n.stage));
      p.appendChild(document.createTextNode(
        ' is never a job here: ' + n.why + '. The pod card shows the '
        + 'command to run at a terminal.'));
      box.appendChild(p);
    });
    return box;
  }

  async function refresh() {
    const mine = ++seq;
    clearFail();
    let out;
    try {
      out = await get('/api/jobs');
    } catch (e) {
      if (mine !== seq) return;
      fail(e.message);
      return;
    }
    if (mine !== seq) return;
    spec = out;
    const list = document.getElementById('jobs-list');
    if (!list) return;
    list.textContent = '';
    if (!out.jobs.length) {
      list.appendChild(el('p', 'note',
        'Nothing has been run from this directory yet.'));
    }
    out.jobs.slice().reverse().forEach((job) => {
      list.appendChild(jobRow(job));
    });
    const host = document.getElementById('jobs-runner');
    if (host) { host.textContent = ''; host.appendChild(runner()); }
  }

  async function showJobs() {
    const main = document.getElementById('ui-main');
    main.textContent = '';
    sup = await get('/api/supervisor');
    spec = await get('/api/jobs');

    main.appendChild(el('h2', null, 'Jobs'));
    main.appendChild(el('p', 'lede',
      'Every stage is a command. What ran, what it exited with, why it is '
      + 'in the state it is in, and the log it wrote — all of it read from '
      + 'this directory, which is the truth.'));
    main.appendChild(supervisorNote());

    const runnerHost = el('div');
    runnerHost.id = 'jobs-runner';
    main.appendChild(runnerHost);

    const err = el('div', 'refusal');
    err.id = 'jobs-error';
    err.hidden = true;
    err.setAttribute('role', 'alert');
    main.appendChild(err);

    const list = el('div');
    list.id = 'jobs-list';
    main.appendChild(list);

    await refresh();

    // A running job's state changes without anyone clicking. Cleared when
    // the page is left, so a route away does not leave a timer redrawing a
    // page that is gone.
    if (timer) window.clearInterval(timer);
    timer = window.setInterval(() => {
      if (window.location.hash !== '#/jobs') {
        window.clearInterval(timer);
        timer = null;
        return;
      }
      refresh();
    }, 4000);
  }

  window.onegroundJobs = showJobs;
})();
