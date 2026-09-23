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
    if (!field.belongs_to) return true;
    const [owner, wanted] = field.belongs_to;
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
    if (field.choices) {
      input = el('select');
      input.appendChild(el('option', null, ''));
      field.choices.forEach((c) => {
        const o = el('option', null, String(c));
        o.value = String(c);
        input.appendChild(o);
      });
    } else if (field.type === 'bool') {
      input = el('select');
      ['', 'true', 'false'].forEach((v) => {
        const o = el('option', null, v === '' ? '' : v);
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

  function fieldRow(field) {
    const row = el('div', 'field');
    row.dataset.field = field.name;
    const head = el('div', 'field-head');
    const lab = el('label', null, field.name.split('.').pop());
    lab.setAttribute('for', 'f-' + field.name);
    head.appendChild(lab);
    if (field.required) head.appendChild(el('span', 'required', 'required'));
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
  // the page says so rather than leaving a user to discover at save that the
  // form was never going to catch them. An incomplete table is a timing
  // defect, not a correctness one -- the guard refuses all eleven at save --
  // and this paragraph is what makes the timing honest instead of a surprise.
  function outsideTheTable() {
    const box = el('details', 'outside');
    box.appendChild(el('summary', null,
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
    const go = el('button', 'primary', 'Save');
    go.type = 'button';
    go.addEventListener('click', () => { save(); });
    saveRow.appendChild(whereLabel);
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
  }

  window.onegroundCompose = showCompose;
})();
