// Does every readable thing on this page have enough contrast to read?
//
// Task 046. Injected into a page by the browser pass and run against
// COMPUTED styles, which is the whole point: three times now the interface
// has shipped a control the same colour as its background, and none of the
// three was reachable from the stylesheet.
//
//   slice 1   compare selects, dark on dark
//   046       compose form controls, on --panel instead of --field
//   046       the jobs runner's buttons, matching no rule at all
//
// The third is the one that settles the question. Those buttons were
// `.door` inside `.runner-row`, and `.door` was declared as
// `.compose-doors .door` -- a descendant selector -- so they matched
// nothing and rendered as bare UA buttons. **There was no `var()` to check,
// because there was no rule.** A stylesheet check verifies that the tokens
// a rule names are declared; it cannot see a rule that was never written,
// and it cannot resolve cascade, inheritance, specificity, `opacity`, or a
// background inherited from three ancestors up.
//
// Only a rendered page knows what colour a thing actually is. So this reads
// `getComputedStyle` and computes the WCAG 2.1 contrast ratio, which is a
// formula over two colours and needs no judgement.
//
// WHAT IT DOES NOT CLAIM. Contrast is not readability: a 21:1 ratio at 6px
// is unreadable, and this says nothing about that. It catches one failure
// mode -- text you cannot see against what is behind it -- completely, and
// nothing else at all.
(() => {
  'use strict';

  const AA_NORMAL = 4.5;   // WCAG 2.1 AA, text below 18.66px or not bold
  const AA_LARGE = 3.0;    // 24px+, or 18.66px+ bold

  function parse(colour) {
    const m = String(colour).match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
    if (parts.length < 3 || parts.some(Number.isNaN)) return null;
    return { r: parts[0], g: parts[1], b: parts[2],
             a: parts.length > 3 ? parts[3] : 1 };
  }

  function luminance(c) {
    const f = (v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }

  function over(fg, bg) {
    // A translucent foreground is what is actually seen, so it is composited
    // before the ratio is taken. Reporting the ratio of the unmixed colour
    // would pass text that is invisible because it is 10% opaque.
    const a = fg.a;
    return { r: fg.r * a + bg.r * (1 - a),
             g: fg.g * a + bg.g * (1 - a),
             b: fg.b * a + bg.b * (1 - a), a: 1 };
  }

  // What is actually behind this element: walk up until something is not
  // transparent. `transparent` is not white -- assuming it were is how a
  // dark-on-dark control passes a naive check.
  function backdrop(node) {
    let at = node;
    while (at) {
      const c = parse(getComputedStyle(at).backgroundColor);
      if (c && c.a > 0) {
        if (c.a >= 1) return c;
        const under = backdrop(at.parentElement);
        return over(c, under || { r: 255, g: 255, b: 255, a: 1 });
      }
      at = at.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };   // the canvas
  }

  function ratio(fg, bg) {
    const a = luminance(fg), b = luminance(bg);
    const hi = Math.max(a, b), lo = Math.min(a, b);
    return (hi + 0.05) / (lo + 0.05);
  }

  function ownText(node) {
    // Text this element renders itself, not text its children render. A
    // container whose only text is in a child would otherwise be measured
    // against the wrong colours.
    return Array.prototype.some.call(node.childNodes,
      (n) => n.nodeType === 3 && n.textContent.trim().length > 0);
  }

  function visible(node, style) {
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    if (Number(style.opacity) === 0) return false;
    const box = node.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  }

  function describe(node) {
    const id = node.id ? '#' + node.id : '';
    const cls = node.className && typeof node.className === 'string'
      ? '.' + node.className.trim().split(/\s+/).join('.') : '';
    return node.tagName.toLowerCase() + id + cls;
  }

  window.__onegroundContrast = function (opts) {
    const options = opts || {};
    const findings = [];
    const exempt = [];
    let checked = 0;
    const nodes = document.querySelectorAll('body *');
    for (const node of nodes) {
      const style = getComputedStyle(node);
      if (!visible(node, style)) continue;
      // A control is measured even with no text of its own: an empty select
      // is still a thing a person has to see.
      const control = ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA']
        .indexOf(node.tagName) !== -1;
      if (!control && !ownText(node)) continue;

      // WCAG 1.4.3 exempts INACTIVE user interface components, and it is
      // right to: a disabled control is dimmed on purpose, and that is how
      // it says it is disabled. Without this the check reports every
      // disabled button as a defect and its output stops being read -- a
      // check that answers on a healthy tree teaches its readers to ignore
      // it (PRACTICE section 2, warning 4).
      //
      // Reported rather than skipped, because an exemption that is not
      // reported has only moved the silence (section 7.2). The count of
      // what was set aside is in the answer.
      if (control && node.disabled) {
        exempt.push({ what: describe(node),
                      why: 'a disabled control; WCAG 1.4.3 exempts inactive '
                           + 'components, and the dimming is how it says so' });
        continue;
      }

      const fg = parse(style.color);
      if (!fg) continue;
      const bg = backdrop(node);
      // `opacity` on the element scales everything it paints.
      const alpha = Number(style.opacity);
      const painted = alpha < 1
        ? over({ r: fg.r, g: fg.g, b: fg.b, a: fg.a * alpha }, bg)
        : over(fg, bg);
      const got = ratio(painted, bg);

      const size = parseFloat(style.fontSize) || 16;
      const bold = (parseInt(style.fontWeight, 10) || 400) >= 700;
      const large = size >= 24 || (size >= 18.66 && bold);
      const need = large ? AA_LARGE : AA_NORMAL;

      checked += 1;
      if (got + 0.01 < need) {
        findings.push({
          what: describe(node),
          text: (node.textContent || '').trim().slice(0, 40),
          ratio: Math.round(got * 100) / 100,
          need: need,
          color: style.color,
          background: 'rgb(' + [bg.r, bg.g, bg.b].map(Math.round).join(',')
                      + ')',
          fontSize: size,
          control: control,
        });
      }
    }
    return { checked: checked, findings: findings, exempt: exempt,
             width: window.innerWidth, hash: window.location.hash,
             threshold: { normal: AA_NORMAL, large: AA_LARGE },
             note: options.note || null };
  };
})();
