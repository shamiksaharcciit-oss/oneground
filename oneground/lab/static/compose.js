// The write half: the form that writes `requirements.yaml` (task 046).
//
// Kept in its own file because `docs/INTERFACE.md` §3 says the two halves are
// kept apart "in the code and in the page", and because `ui.js` opens by
// stating that there is no POST in it. Adding one there would have falsified
// the file's own first paragraph, which is the cheapest kind of stale
// sentence to avoid: the one you are about to write.
//
// `ui.js` owns the router and hands `#/new` to the hook this file installs.
// That seam is deliberate and it is one line on each side: the read half
// gains a branch and no POST, and this file gains a page and no route table.
//
// THE RULE THIS FILE IS HELD TO
// -----------------------------
// It renders the declaration and it executes refusals. It does not carry a
// second copy of either.
//
//   * every label, explanation, type, bound and conditional comes from
//     /api/compose/fields, which is `oneground/intake/fields.py` -- so the
//     string beside a box and the comment in the written file are one string
//     by construction rather than by agreement;
//   * every refusal shown here is the CLI's own sentence, rendered verbatim,
//     never rephrased and never summarised;
//   * this file validates nothing. It cannot: eleven of intake's twenty-five
//     refusals are relational or not about a field at all, and a form that
//     re-expressed them would be the second implementation the whole design
//     exists to prevent. The guard refuses them at save.
//
// It does define its own four-line `el()` rather than importing one. A DOM
// helper is not a rule, and the second-implementation rule is about rules.
(() => {
  'use strict';
  const TOKEN = document.querySelector(
    'meta[name="oneground-lab-token"]').content;

  const PRESENT = '<present>';
  const ABSENT = '<absent>';

  let spec = null;              // the declaration, fetched once
  let state = {};               // dotted name -> what the user typed
  let previewSeq = 0;           // newest preview wins; see ui.js on routeSeq

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  async function postApi(path, body) {
    const r = await fetch(path + '?token=' + encodeURIComponent(TOKEN), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json',
                 'Accept': 'application/json' },
      body: JSON.stringify(body),
    });
    const out = await r.json().catch(() => ({
      error: path + ' answered ' + r.status + ' and no readable body' }));
    if (!r.ok) { out.__status = r.status; throw out; }
    return out;
  }

  async function getApi(path) {
    const r = await fetch(path + '?token=' + encodeURIComponent(TOKEN),
                          { headers: { 'Accept': 'application/json' } });
    const out = await r.json().catch(() => ({ error: 'unreadable answer' }));
    if (!r.ok) throw out;
    return out;
  }

  // --- what a field belongs to -------------------------------------------
  // The declaration's two sentinels. Presence is a different question from
  // membership -- `oneground/intake/fields.py` says why at length -- and this
  // is the whole of the difference in code: one asks whether anything is
  // there, the other asks what it is.
  function shown(field) {
    return conditionHolds(field.belongs_to);
  }

  // Requiredness is stated whenever it is true of anything, and says what
  // it is true OF. Two corrections got here and the second overshot the
  // first, which is worth keeping in view:
  //
  //   * it first read `Param.default is NO_DEFAULT` and marked every field
  //     required, including one whose explanation begins "Optional.";
  //   * the repair moved it to `fields.REQUIRED` and rendered the badge only
  //     while the condition held -- and since every condition is false on an
  //     empty form, NOTHING was marked required at all. `run.seed`, whose
  //     own explanation says an unseeded run cannot be reproduced, looked
  //     exactly as optional as `languages`.
  //
  // Silence everywhere is not the repair for a label that claimed too much.
  // So the badge is always shown where `REQUIRED` knows something, and it
  // names the condition rather than hiding behind it: a reader deciding
  // whether to fill in `seed` is told it is required for a sample run, which
  // is true before they have typed anything.
  function requiredBadge(field) {
    if (!field.required) return null;
    const when = field.required_when;
    let text = 'required';
    if (when) {
      const [owner, wanted] = when;
      const last = owner.split('.').pop();
      if (wanted === PRESENT) text = 'required with ' + last;
      else if (wanted === ABSENT) text = 'required without ' + last;
      else text = 'required when ' + last + ' is '
                  + (wanted || []).join(' or ');
    }
    // `now` when the condition actually holds, so the page distinguishes
    // *this is required of the file you are writing* from *this would be
    // required if you went that way*.
    const cls = 'required' + (conditionHolds(when) ? ' now' : '');
    return el('span', cls, text);
  }

  // One helper, two callers. `belongs_to` decides whether a field is offered
  // at all; `REQUIRED` decides whether it must be filled. They are written
  // in the same vocabulary -- a value set, or PRESENT/ABSENT for the
  // presence question -- so one function answers both, and the two cannot
  // drift into reading the same declaration two ways. `shown()` called its
  // own copy of this for about ten minutes, which is warning 2 arriving
  // inside the file that cites it.
  function conditionHolds(when) {
    if (!when) return true;
    const [owner, wanted] = when;
    const held = ownerValue(owner);
    if (wanted === PRESENT) return held !== '' && held !== undefined;
    if (wanted === ABSENT) return held === '' || held === undefined;
    return (wanted || []).map(String).indexOf(String(held)) !== -1;
  }

  // An owner may be a declared field or a block that is not one of its own
  // -- `corpus.sample`, `corpus.documents`. A block counts as present when
  // anything beneath it has been filled in.
  function ownerValue(owner) {
    if (Object.prototype.hasOwnProperty.call(state, owner)) return state[owner];
    const prefix = owner + '.';
    const beneath = Object.keys(state).filter(
      (k) => k.indexOf(prefix) === 0 && state[k] !== '');
    return beneath.length ? beneath[0] : '';
  }

  // --- the form -----------------------------------------------------------
  function blockOf(name) {
    const parts = name.split('.');
    if (parts.length === 1) return 'the file';
    return parts.slice(0, parts.length - 1).join('.');
  }

  function control(field) {
    let input;
    if (field.choices || field.type === 'bool') {
      // An empty select invites being left alone, and one of these sat
      // directly above an explanation saying any other version is refused.
      // The unselected option names itself, and where leaving it alone
      // writes something anyway it says what.
      input = el('select');
      // The value is set explicitly. An <option> with no `value` takes its
      // own text, so this one answered to its label rather than to '' --
      // `select.value = ''` then matched nothing, selectedIndex went to -1,
      // and the control rendered blank again. The same empty select, from
      // the opposite direction, inside the fix for it.
      const unset = el('option', null, unsetLabel(field));
      unset.value = '';
      input.appendChild(unset);
      const values = field.choices
        ? field.choices.map(String) : ['true', 'false'];
      values.forEach((v) => {
        const o = el('option', null, v);
        o.value = v;
        input.appendChild(o);
      });
    } else {
      input = el('input');
      input.type = field.type === 'int' ? 'text' : 'text';
      // `text` even for numbers: `2_100_000` is how the example file writes
      // a corpus size and a number input would refuse to hold it. The
      // declaration types it on the way in -- this box carries what was
      // typed, which is also what a refusal has to quote back.
      input.setAttribute('inputmode',
                         field.type === 'int' ? 'numeric' : 'text');
    }
    input.id = 'f-' + field.name;
    input.value = state[field.name] === undefined ? '' : state[field.name];
    input.addEventListener('input', () => {
      state[field.name] = input.value;
      refresh();
    });
    input.addEventListener('change', () => {
      state[field.name] = input.value;
      refresh();
    });
    return input;
  }

  // What an untouched box means, said in the box. Three cases and they are
  // different statements: the key is simply absent; the key is written from
  // a declared default; or the file will be refused without it.
  function unsetLabel(field) {
    if (field.default !== null && field.default !== undefined) {
      return '\u2014 not set (' + field.default + ' is written) \u2014';
    }
    if (field.required) return '\u2014 not set \u2014';
    return '\u2014 not set (left out of the file) \u2014';
  }

  function fieldRow(field) {
    const row = el('div', 'field');
    row.dataset.field = field.name;
    const head = el('div', 'field-head');
    const lab = el('label', null, field.name.split('.').pop());
    lab.setAttribute('for', 'f-' + field.name);
    head.appendChild(lab);
    const req = requiredBadge(field);
    if (req) head.appendChild(req);
    row.appendChild(head);
    row.appendChild(control(field));
    // The explanation, from the declaration. This is the same string the
    // written file carries as a comment.
    row.appendChild(el('p', 'note', field.note));
    return row;
  }

  function form() {
    const wrap = el('section', 'compose-form');
    const seen = {};
    spec.fields.forEach((field) => {
      if (!shown(field)) return;
      const block = blockOf(field.name);
      if (!seen[block]) {
        const group = el('div', 'field-group');
        group.appendChild(el('h3', null, block));
        wrap.appendChild(group);
        seen[block] = group;
      }
      seen[block].appendChild(fieldRow(field));
    });
    return wrap;
  }

  // --- what this form cannot refuse, said out loud ------------------------
  // Eleven of intake's twenty-five refusals are outside the field table, and
  // the page names all eleven with the reason each is out.
  //
  // IF YOU ARE HERE TO ADD CLIENT-SIDE VALIDATION, READ THIS FIRST. You will
  // be about to improve the form and you will be removing the only thing
  // that makes it honest.
  //
  // This disclosure is what stands between the form and the inference *the
  // form did not stop me, so this is valid*. Without it a user types, sees
  // nothing complain, and reasonably concludes the document is good -- and
  // for eleven refusals it may not be. Naming them converts silence from a
  // claim into a stated gap, which is the difference between a form that is
  // incomplete and one that is misleading.
  //
  // Adding checks here does not shrink the list. It creates a second
  // implementation of rules that live in `oneground/intake/__init__.py`, and
  // the two disagree the first time either is fixed -- which is the defect
  // this whole design exists to prevent, arriving in the one place it looks
  // like a courtesy. The list shrinks by moving a refusal INTO the
  // declaration in `oneground/intake/fields.py`, where the form and the
  // command line read the same one. If it cannot be declared, it stays here
  // and it stays named.
  //
  // An incomplete table is a timing defect, not a correctness one -- the
  // write guard refuses all eleven at save, in the CLI's words -- and this
  // paragraph is what makes the timing honest rather than a surprise.
  function outsideTheTable() {
    const box = el('section', 'outside');
    // Not a <details>, and not closed. The list is the only thing standing
    // between this form and "it did not stop me, so it is valid", and it was
    // collapsed behind a triangle labelled with what the form cannot do --
    // so the page's most important honesty was its least prominent element,
    // and a reader who never opened it got the first half of that sentence
    // without the second.
    box.appendChild(el('h3', null,
      'Eleven things this form cannot check while you type'));
    box.appendChild(el('p', 'note',
      'They are checked when you save, by the same validator the command '
      + 'line uses, and refused in its words. They are listed here so that '
      + '"the form did not stop me" is never mistaken for "this is valid".'));
    const list = el('ul', 'outside-list');
    spec.outside_the_table.forEach((o) => {
      const li = el('li');
      li.appendChild(el('code', null, o.rule));
      li.appendChild(el('span', 'kind', o.kind));
      li.appendChild(el('span', 'why', o.why));
      list.appendChild(li);
    });
    box.appendChild(list);
    return box;
  }

  // --- refusals -----------------------------------------------------------
  function clearRefusal() {
    const box = document.getElementById('compose-refusal');
    if (box) { box.hidden = true; box.textContent = ''; }
    Array.prototype.forEach.call(
      document.querySelectorAll('.field.refused'),
      (n) => n.classList.remove('refused'));
  }

  function showRefusal(payload) {
    const box = document.getElementById('compose-refusal');
    if (!box) return;
    box.hidden = false;
    box.textContent = '';
    // Verbatim. A refusal is the most useful thing the tool produces and it
    // was written once, in the CLI, on purpose.
    if (payload.refusal) {
      box.appendChild(el('p', 'refusal-what', payload.refusal));
    } else if (payload.error) {
      box.appendChild(el('p', 'refusal-what', payload.error));
    }
    if (payload.raised) {
      // The third state: not a refusal, and not a file that was accepted.
      box.appendChild(el('p', 'note',
        'This is a defect in the tool rather than in your file: '
        + payload.raised));
    }
    if (payload.lost) {
      box.appendChild(el('p', 'note',
        'These fields did not read back as they were written:'));
      const list = el('ul', 'outside-list');
      payload.lost.forEach((l) => {
        list.appendChild(el('li', null,
          l.field + ': wrote ' + JSON.stringify(l.written)
          + ', read back ' + JSON.stringify(l.read_back)));
      });
      box.appendChild(list);
    }
    if (payload.field) {
      const row = document.querySelector(
        '.field[data-field="' + payload.field + '"]');
      if (row) {
        row.classList.add('refused');
        row.scrollIntoView({ block: 'center' });
      }
    }
  }

  // --- the file, as it stands ---------------------------------------------
  async function refresh() {
    const mine = ++previewSeq;
    const out = document.getElementById('compose-file');
    try {
      const preview = await postApi('/api/compose/preview', { state: state });
      if (mine !== previewSeq) return;
      out.textContent = preview.text;
    } catch (e) {
      if (mine !== previewSeq) return;
      out.textContent = '';
      showRefusal(e);
    }
    // The form's own shape can change with what was typed: a field that
    // belongs to another only appears once its owner says so. Re-rendering
    // here keeps the declaration's conditionals live rather than evaluated
    // once at load.
    redrawFormKeepingFocus();
  }

  function redrawFormKeepingFocus() {
    const active = document.activeElement;
    const focused = active && active.id ? active.id : null;
    const at = focused && active.selectionStart !== undefined
      ? active.selectionStart : null;
    const host = document.getElementById('compose-fields');
    if (!host) return;
    host.textContent = '';
    host.appendChild(form());
    if (focused) {
      const again = document.getElementById(focused);
      if (again) {
        again.focus();
        if (at !== null && again.setSelectionRange) {
          try { again.setSelectionRange(at, at); } catch (ignored) { /* select */ }
        }
      }
    }
  }

  // --- the three doors ----------------------------------------------------
  async function save() {
    clearRefusal();
    const where = document.getElementById('compose-path');
    try {
      const out = await postApi('/api/compose/write',
                                { state: state, path: where.value });
      const said = document.getElementById('compose-saved');
      said.hidden = false;
      said.textContent = 'written: ' + out.path;
    } catch (e) {
      showRefusal(e);
    }
  }

  async function upload(file) {
    clearRefusal();
    const text = await file.text();
    try {
      const out = await postApi('/api/compose/open', { text: text });
      state = {};
      Object.keys(out.state).forEach((k) => {
        state[k] = out.state[k] === null ? '' : String(out.state[k]);
      });
      redrawFormKeepingFocus();
      await refresh();
      if (out.refusal) showRefusal(out);
      if (out.not_offered && out.not_offered.length) {
        const box = document.getElementById('compose-refusal');
        box.hidden = false;
        box.appendChild(el('p', 'note',
          'This form does not offer these keys, so they are not in the file '
          + 'it would write: ' + out.not_offered.join(', ')));
      }
    } catch (e) {
      showRefusal(e);
    }
  }

  async function template() {
    const out = await getApi('/api/compose/template');
    const blob = new Blob([out.text], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const a = el('a');
    a.href = url;
    a.download = 'requirements.yaml';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // --- the page -----------------------------------------------------------
  async function showCompose() {
    const main = document.getElementById('ui-main');
    main.textContent = '';
    if (!spec) spec = await getApi('/api/compose/fields');

    main.appendChild(el('h2', null, 'A new requirements file'));
    main.appendChild(el('p', 'lede',
      'Three ways in and one file out. Fill this in, upload one you have, or '
      + 'take a template to keep. All three write the same file for the same '
      + 'answers, and every explanation below is written into it as a '
      + 'comment.'));

    const doors = el('div', 'compose-doors');
    const up = el('input');
    up.type = 'file';
    up.id = 'compose-upload';
    up.accept = '.yaml,.yml,text/yaml';
    up.addEventListener('change', () => {
      if (up.files && up.files[0]) upload(up.files[0]);
    });
    const upLabel = el('label', 'door');
    upLabel.setAttribute('for', 'compose-upload');
    upLabel.appendChild(el('span', null, 'Upload one you have'));
    doors.appendChild(upLabel);
    doors.appendChild(up);
    const tmpl = el('button', 'door');
    tmpl.type = 'button';
    tmpl.textContent = 'Download a template';
    tmpl.addEventListener('click', () => { template(); });
    doors.appendChild(tmpl);
    main.appendChild(doors);

    const split = el('div', 'compose-split');
    const left = el('div', 'compose-left');
    left.id = 'compose-fields';
    const right = el('div', 'compose-right');
    right.appendChild(el('h3', null, 'The file this writes'));
    // At rest this pane shows `oneground: 1` alone, which reads as broken
    // rather than as empty. It is also the thing that proves the form
    // writes what was typed, so it is worth one line of its own.
    right.appendChild(el('p', 'note',
      'The file as you type, and exactly what Save writes. A field you '
      + 'leave empty is left out rather than written blank.'));
    const pre = el('pre', 'compose-file');
    pre.id = 'compose-file';
    right.appendChild(pre);
    split.appendChild(left);
    split.appendChild(right);
    main.appendChild(split);

    const refusal = el('div', 'refusal');
    refusal.id = 'compose-refusal';
    refusal.hidden = true;
    refusal.setAttribute('role', 'alert');
    main.appendChild(refusal);

    const saveRow = el('div', 'compose-save');
    const where = el('input');
    where.id = 'compose-path';
    where.value = 'requirements.yaml';
    const whereLabel = el('label', null, 'Write it to');
    whereLabel.setAttribute('for', 'compose-path');
    // WHERE IT LANDS, BEFORE IT LANDS. `Write it to requirements.yaml`
    // named a file and not a place, so the only way to learn the directory
    // was to save and watch the jobs page react -- which is finding out
    // afterwards. The server already knows; the page was not asking.
    //
    // It is the same shortened form the header shows, from the same field,
    // so the two cannot disagree and neither prints an absolute path.
    const dir = el('span', 'save-dir');
    dir.id = 'compose-dir';
    dir.textContent = '';
    const go = el('button', 'primary', 'Save');
    go.type = 'button';
    go.addEventListener('click', () => { save(); });
    saveRow.appendChild(whereLabel);
    saveRow.appendChild(dir);
    saveRow.appendChild(where);
    saveRow.appendChild(go);
    main.appendChild(saveRow);

    const saved = el('p', 'saved');
    saved.id = 'compose-saved';
    saved.hidden = true;
    main.appendChild(saved);

    main.appendChild(outsideTheTable());

    redrawFormKeepingFocus();
    await refresh();

    // After the form is up, because a directory the reader cannot act on is
    // not worth blocking the page for. A session that cannot answer leaves
    // the prefix empty rather than guessing or printing a placeholder that
    // reads like a path.
    try {
      const check = await getApi('/api/check');
      if (check.runs_dir) {
        dir.textContent = check.runs_dir
          + (check.runs_dir.endsWith('/') ? '' : '/');
        dir.title = 'the runs directory this session was opened on';
      }
    } catch (e) {
      dir.textContent = '';
    }
  }

  window.onegroundCompose = showCompose;
})();
