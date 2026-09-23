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

    // The pod card is the CLI's own card: `pod plan` prints it and the log
    // shows it verbatim. The UI computes nothing about a session -- the
    // lab's guard refuses it `oneground.pod`, which is the same ruling that
    // made the supervisor a second process.
    //
    // And then the handover. The one operation that spends money keeps the
    // one boundary that cannot be automated by accident, so this is a
    // command to copy, not a button.
    if (job.stage === 'pod plan' && job.state === 'done') {
      const hand = el('div', 'handover');
      hand.appendChild(el('p', 'note',
        'The card above is what the command line printed. To create the '
        + 'session, run this at a terminal — nothing here will:'));
      const arg = (job.invocation || []).slice(-1)[0] || '<spec>';
      hand.appendChild(el('pre', 'handover-command',
        'oneground pod up ' + arg));
      row.appendChild(hand);
    }

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

  // Which logs are open, and how far each has been read. Kept out here
  // rather than on the element so a refresh that redraws a row does not
  // lose a reader's place -- the job list is rebuilt every few seconds and
  // the log is the one thing on the page somebody is in the middle of.
  const open = new Map();          // job id -> {offset, text, live}

  async function showLog(job, row) {
    if (open.has(job.id)) {
      open.delete(job.id);
      const existing = row.querySelector('.job-log');
      if (existing) existing.remove();
      return;
    }
    open.set(job.id, { offset: 0, text: '', live: true });
    row.appendChild(el('pre', 'job-log', 'reading…'));
    await followLog(job.id, row);
  }

  // Streamed by offset: a `simulate` writes for minutes, and re-reading the
  // whole file every few seconds would cost more to watch than to run, and
  // would replace text a reader was in the middle of.
  async function followLog(id, row) {
    const state = open.get(id);
    if (!state) return;
    const pre = row.querySelector('.job-log');
    if (!pre) return;
    try {
      const out = await get('/api/jobs/log',
                            { id: id, since: String(state.offset) });
      if (!open.has(id)) return;              // closed while we were asking
      if (out.text === null) {
        // Absent is a fact with a reason, not an empty log. A job that has
        // not started yet and a log that was replaced are different things
        // and the endpoint says which.
        pre.textContent = out.absent;
        pre.classList.add('absent');
        state.offset = 0;
        state.text = '';
      } else {
        pre.classList.remove('absent');
        state.text += out.text;
        state.offset = out.offset;
        // Only touch the DOM when there is something new: an unchanged
        // reassignment still resets a selection in some browsers, and the
        // reader is the person this is for.
        if (out.text) {
          pre.textContent = state.text || '(no output yet)';
          // Follow the tail only if the reader is already at it. Scrolling
          // someone back down because a line arrived is the fastest way to
          // make a live log unreadable.
          const atEnd = pre.scrollHeight - pre.scrollTop - pre.clientHeight
            < 24;
          if (atEnd) pre.scrollTop = pre.scrollHeight;
        } else if (!state.text) {
          pre.textContent = '(no output yet)';
        }
      }
      state.live = !!out.live;
    } catch (e) {
      pre.textContent = e.message;
    }
  }

  // Called from the refresh: every open log catches up, and a log whose job
  // has finished is read once more and then left alone.
  async function followOpenLogs() {
    for (const id of Array.from(open.keys())) {
      const row = document.querySelector('.job[data-job="' + id + '"]');
      if (!row) continue;                     // its row is gone; leave it
      if (!row.querySelector('.job-log')) {
        row.appendChild(el('pre', 'job-log', ''));
      }
      await followLog(id, row);
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

  // THE CLICK ASKS. It does not default, and there is no pre-selected
  // target anywhere on this page.
  //
  // It used to send `[stage, '.']`, so clicking `characterize` enqueued
  // `oneground characterize .` against the runs directory -- measured: exit
  // 1, `PermissionError: [Errno 13] Permission denied: '.'`, a traceback,
  // for a job whose target the user was never asked for.
  //
  // **A job records exactly what ran, so a target nobody chose makes the
  // record accurate and meaningless** -- the whole value of the record gone
  // at the first click. A list with a default would have the same defect
  // wearing a control: the default is the thing that just bit us.
  //
  // So the target is part of the request, which is what the record has to
  // carry anyway, and **a stage whose target cannot be named is not
  // offered** -- with the reason, because a missing button is otherwise
  // indistinguishable from an oversight.
  let targets = null;

  function chooser(stage, spec_, anchor) {
    const existing = document.getElementById('chooser');
    if (existing) existing.remove();

    const box = el('section', 'chooser');
    box.id = 'chooser';
    box.appendChild(el('h4', null, 'Run ' + stage + ' against'));
    box.appendChild(el('p', 'note',
      (targets.kinds || {})[spec_.kind] || spec_.kind));

    const list = el('div', 'chooser-list');
    spec_.choices.forEach((choice) => {
      const b = el('button', 'door', choice.name);
      b.type = 'button';
      b.addEventListener('click', () => {
        box.remove();
        start(stage, choice.arg);
      });
      list.appendChild(b);
    });
    box.appendChild(list);

    // The command this would run, before it runs. Nothing is enqueued from
    // this page that the page has not already shown whole.
    const shown = el('pre', 'chooser-preview',
      'oneground ' + stage + ' <' + spec_.kind + '>');
    box.appendChild(shown);
    Array.prototype.forEach.call(list.querySelectorAll('.door'), (b, i) => {
      b.addEventListener('mouseenter', () => {
        shown.textContent = 'oneground ' + stage + ' '
          + spec_.choices[i].arg;
      });
    });

    const cancel_ = el('button', 'linkish', 'not now');
    cancel_.type = 'button';
    cancel_.addEventListener('click', () => { box.remove(); });
    box.appendChild(cancel_);

    anchor.appendChild(box);
  }

  async function start(stage, arg) {
    clearFail();
    try {
      // The invocation is exactly what a terminal would run, which is what
      // makes the record replayable.
      await ask('/enqueue', { stage: stage, invocation: [stage, arg] });
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
    // The rule, once, where it explains every withholding below rather than
    // being repeated inside each of them.
    box.appendChild(el('p', 'note',
      'A stage is offered only when this page can name what it would run '
      + 'against. One that cannot is not offered, and says why.'));

    const offered = (targets && targets.offered) || {};
    const names = Object.keys(offered);
    if (!names.length) {
      box.appendChild(el('p', 'note cannot-run',
        'No stage can be offered here yet: nothing in this directory can be '
        + 'named as a target for one.'));
    }

    // Two groups, because `pod plan` and `characterize` are different kinds
    // of thing and one undifferentiated row invites reading them as
    // equivalent.
    const groups = [
      ['The pipeline', names.filter((s) => s.indexOf('pod ') !== 0)],
      ['A pod session', names.filter((s) => s.indexOf('pod ') === 0)],
    ];
    groups.forEach(([title, stages]) => {
      if (!stages.length) return;
      box.appendChild(el('h4', 'runner-group', title));
      const row = el('div', 'runner-row');
      stages.forEach((stage) => {
        const b = el('button', 'door', stage + '…');
        b.type = 'button';
        b.disabled = !(sup && sup.running);
        // The ellipsis is the promise: this asks before it does anything.
        b.addEventListener('click', () => {
          chooser(stage, offered[stage], box);
        });
        row.appendChild(b);
      });
      box.appendChild(row);
    });

    // What is not offered, and why -- GROUPED BY THE REASON, because nine
    // stages had five reasons between them and the page printed nine
    // paragraphs. Five repeated one sentence verbatim, four repeated
    // another, and the four carried a rule about this page ("a stage whose
    // target cannot be named is a stage that should not be offered") once
    // each, which is a fact about the page and not about `pod watch`.
    //
    // That is task 045's one fact stated fifteen times, arriving in a
    // surface instead of a report, and the repair is the same: state the
    // shared thing once and list what it applies to. A reader should meet
    // one sentence about five stages and one about four, not nine
    // paragraphs to find the single thing they can act on.
    const withheld = (targets && targets.withheld) || [];
    const byReason = [];
    withheld.forEach((w) => {
      const found = byReason.filter((g) => g.why === w.why)[0];
      if (found) found.stages.push(w.stage);
      else byReason.push({ why: w.why, stages: [w.stage] });
    });
    byReason.forEach((group) => {
      const p = el('p', 'note');
      group.stages.forEach((stage, i) => {
        if (i) p.appendChild(document.createTextNode(
          i === group.stages.length - 1 ? ' and ' : ', '));
        p.appendChild(el('code', null, stage));
      });
      p.appendChild(document.createTextNode(
        (group.stages.length > 1 ? ' are not offered: '
                                 : ' is not offered: ') + group.why));
      box.appendChild(p);
    });

    // And the action, which was the thing a reader had to infer from nine
    // paragraphs: if the pipeline is withheld for want of a requirements
    // file, the way out is to write one, and the page that writes one is a
    // click away.
    if (withheld.some((w) => w.why.indexOf('requirements file') !== -1)) {
      const act = el('p', 'note act');
      act.appendChild(document.createTextNode('To run the pipeline here, '));
      const link = el('a', null, 'write a requirements file');
      link.href = '#/new';
      act.appendChild(link);
      act.appendChild(document.createTextNode(
        ' — saving one into this directory is what makes these stages '
        + 'offerable.'));
      box.appendChild(act);
    }

    // And what is never a job at all, which is a ruling rather than a gap.
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
    try {
      targets = await get('/api/jobs/targets');
    } catch (e) {
      targets = { offered: {}, withheld: [], kinds: {} };
      fail(e.message);
    }
    if (mine !== seq) return;
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
    // The rows were just rebuilt, so any open log lost its element. Restore
    // it from what has already been read rather than re-fetching from zero:
    // the reader's place is in `open`, not in the DOM.
    for (const [id, state] of open) {
      const row = list.querySelector('.job[data-job="' + id + '"]');
      if (!row) continue;
      const pre = el('pre', 'job-log', state.text || '(no output yet)');
      if (!state.text) pre.classList.add('absent');
      row.appendChild(pre);
      pre.scrollTop = pre.scrollHeight;
    }
    await followOpenLogs();
    // NOT WHILE SOMEONE IS USING IT. The runner is rebuilt on every
    // refresh, and the chooser lives inside it -- so the four-second timer
    // was deleting the chooser four seconds after it opened. Clicking a
    // stage appeared to do nothing, because by the time a person had read
    // the choices they were gone.
    //
    // It survived my own browser pass because that pass clicked the button
    // and read the DOM 200ms later, and at 200ms the defect does not exist
    // yet. A probe faster than a person cannot see a defect that needs a
    // person's amount of time to happen.
    const host = document.getElementById('jobs-runner');
    if (host && !document.getElementById('chooser')) {
      host.textContent = '';
      host.appendChild(runner());
    }
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
