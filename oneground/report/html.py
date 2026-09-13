"""The rendered report: one self-contained HTML file.

**No network calls of any kind.** No CDN, no webfont fetch, no analytics, no
remote image. A report has to open on a laptop with no internet, and a report
that phones home is a report that has told someone what a user is measuring.
Fonts are loaded from the system with a generic fallback, the ground view is
embedded as a data URI when one exists, and the CSS is inlined from
`docs/design/tokens.css`.

Design rules, from `docs/design/tokens.md`:

* the recommendation is the only emphasised element; everything else is quiet
  and typographic
* outcome colours carry meaning, so nothing else uses them
* monospace means "this is a receipt you can check" -- digests, file paths,
  field references, config labels, and nothing else
* **no charts in this task.** A number with its source beats a picture of a
  number, and a chart would be the third thing on the page competing with the
  recommendation.

Every verdict cell carries its source field in a `title`, so the colour is
never the only thing making the claim.
"""

import base64
import html as _html
import json
import os

from . import claims as cl
from . import verdict as vd

TOKENS_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "docs", "design", "tokens.css")
# There is deliberately no module-level path to a published ground image.
#
# Task 010 embedded `docs/img/ground_b_copies.png` -- the *arxiv-150k* ground
# -- into every report, captioned "the ground". On the smoke report that was a
# picture of a different corpus presented as this one's. A report may only show
# a projection its own run produced (`projection.npy` in the workdir, written
# by `characterize --project`); otherwise it shows the characterization
# numbers, which are always this run's.

OUTCOME_TOKEN = {vd.MEETS: "teal", vd.FAILS: "coral",
                 vd.COULDNT_CHECK: "amber"}

# The words that may only appear against a decided outcome. Used by the tests
# to prove a couldnt_check row never reads like a verdict.
VERDICT_WORDS = ("meets", "fails")


def esc(x):
    return _html.escape("" if x is None else str(x), quote=True)


def _tokens_css():
    try:
        with open(TOKENS_CSS, encoding="utf-8") as f:
            return f.read()
    except OSError:                                   # pragma: no cover
        return ":root{--slate:#1B2432;--panel:#243040;--ink:#E7EAEF;" \
               "--muted:#8B96A5;--ochre:#C99A3B;--teal:#4FC1AD;" \
               "--coral:#E36C5E;--amber:#D9A441;" \
               "--font-ui:system-ui,sans-serif;--font-mono:monospace;}"


def render_projection(workdir, char, max_bytes=6_000_000):
    """Draw this run's own projection, or return None.

    Renders `projection.npy` from the workdir with matplotlib and embeds the
    PNG as a data URI. Nothing published is ever substituted: a report with no
    projection of its own shows numbers, not somebody else's picture.
    """
    if not workdir:
        return None
    path = os.path.join(workdir, "projection.npy")
    if not os.path.exists(path):
        return None
    try:
        import io as _io

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        xy = np.load(path)
        if xy.ndim != 2 or xy.shape[1] != 2:
            return None
        fig = plt.figure(figsize=(10, 6.25), dpi=140)
        ax = fig.add_axes([0, 0, 1, 1])
        fig.patch.set_facecolor("#1B2432")
        ax.set_facecolor("#1B2432")
        ax.scatter(xy[:, 0], xy[:, 1], s=3.0, alpha=0.6, c="#C99A3B",
                   linewidths=0, rasterized=True)
        ax.set_xticks([]); ax.set_yticks([])
        for side in ax.spines.values():
            side.set_visible(False)
        buf = _io.BytesIO()
        fig.savefig(buf, format="png", facecolor="#1B2432")
        plt.close(fig)
        data = buf.getvalue()
        if len(data) > max_bytes:
            return None
        return ("data:image/png;base64,"
                + base64.b64encode(data).decode("ascii"))
    except Exception:                                 # noqa: BLE001
        return None


def _fmt(v, nd=4):
    if v is None:
        return "--"
    if isinstance(v, str):
        return esc(v)
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return esc(v)


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------

def _recommendation(report, recommended):
    """The one emphasised element on the page, with its three outcomes."""
    s = report["summary"]
    counts = (f'<span class="pill teal">{s[vd.MEETS]} meets</span>'
              f'<span class="pill coral">{s[vd.FAILS]} fails</span>'
              f'<span class="pill amber">{s[vd.COULDNT_CHECK]} '
              f"couldn&#39;t-check</span>")
    if recommended is None:
        return f"""
<section class="rec rec-none">
  <div class="rec-label">recommendation</div>
  <h1>Nothing is recommended</h1>
  <p class="rec-why">No option meets every constraint. Recommending an option
  whose constraints could not all be checked would be rounding
  couldn&#39;t-check up to a verdict, so the report does not do it.</p>
  <div class="pills">{counts}</div>
</section>"""

    # Task 018: the constraint name carries its engine. Two engines produce
    # two `latency_p95` rows, and without the engine they read as one
    # constraint answered twice and contradictorily -- a green dot and a red
    # one against the same name, with nothing on the page saying which machine
    # each belonged to.
    rows = "".join(
        f'<div class="rec-c"><span class="dot {r["token"]}">'
        f'</span><span class="rec-cn">{esc(r["constraint"])}'
        + (f'<span class="rec-ce">{esc(r["engine"])}</span>' if r["engine"]
           else "")
        + f'</span><span class="rec-cr">{esc(r["reason"])}</span></div>'
        for r in cl.recommendation_rows(recommended.verdicts, OUTCOME_TOKEN))
    indist = ""
    if recommended.indistinguishable_from:
        indist = (
            '<p class="rec-why">Indistinguishable on recall from '
            + ", ".join(f'<code>{esc(c)}</code>'
                        for c in recommended.indistinguishable_from)
            + f". Their recall differs by less than the calibration tolerance "
              f"({report['calibration']['tolerance']}), so choosing between "
              "them on recall would be reading noise.</p>")
    return f"""
<section class="rec">
  <div class="rec-label">recommendation</div>
  <h1><code class="rec-config">{esc(recommended.config)}</code></h1>
  <div class="pills">{counts}</div>
  {indist}
  <div class="rec-constraints">{rows}</div>
</section>"""


def _outcome_cell(row):
    """The option's own outcome column, from the renderer's strings."""
    return (f'<td class="v {OUTCOME_TOKEN[row["outcome"]]}">'
            f'{cl.outcome_label(row["outcome"], html=True)}</td>')


def _verdict_cell(group):
    """One table cell for every verdict a configuration carries on one
    constraint -- which, with two engines, is one per engine.

    Task 017e's defect was here: the cell rendered `verdict_for(name)`, the
    FIRST verdict, so a configuration whose p95 met the budget on Qdrant and
    missed it on pgvector by forty times showed one flat green `meets` and the
    failing number appeared nowhere on the page.

    Task 019 moved the composition into `claims.verdict_cell`, which returns
    strings. This function assembles tags and reaches into no Verdict, which
    is what the grep-guard in `test_claims.py` enforces.
    """
    cell = cl.verdict_cell(
        group, OUTCOME_TOKEN, couldnt_check=vd.COULDNT_CHECK,
        collapse=lambda g: vd.collapse_by_constraint(g)[g[0].constraint])
    title = esc(cell["title"])
    if not cell["per_engine"]:
        return (f'<td class="v {cell["token"]}" title="{title}">'
                f'{cell["label"]}<span class="src">{esc(cell["source"])}'
                f'</span></td>')
    per = "".join(
        f'<span class="by-engine {e["token"]}">{esc(e["text"])}</span>'
        for e in cell["per_engine"])
    return (f'<td class="v {cell["token"]}" title="{title}">'
            f'{cell["label"]}{per}</td>')


def _options_table(options, not_run_rows, constraint_names):
    head = "".join(f"<th>{esc(c)}</th>" for c in constraint_names)
    body = []
    for o in options:
        cells = []
        for name in constraint_names:
            group = o.verdicts_for(name)
            if not group:
                cells.append('<td class="v"><span class="muted">--</span></td>')
                continue
            cells.append(_verdict_cell(group))
        body.append(
            f'<tr><td class="cfg"><code>{esc(o.config)}</code></td>'
            + _outcome_cell(cl.option_row(o))
            + f'<td class="num">{_fmt(o.measurement.get("recall_at_10"))}</td>'
            + f'<td class="num">{_fmt(o.measurement.get("ceiling_at_10"))}</td>'
            + f'<td class="num">{_fmt(o.measurement.get("storage_amplification"), 2)}x</td>'
            + f'<td class="num">{_fmt(o.measurement.get("fanout"), 0)}</td>'
            + "".join(cells) + "</tr>")
    for r in not_run_rows:
        body.append(
            f'<tr class="notrun"><td class="cfg"><code>{esc(r["family"])}</code></td>'
            f'<td class="v amber">not run</td>'
            f'<td class="num" colspan="{4 + len(constraint_names)}">'
            f'{esc(r["reason"])}</td></tr>')
    return f"""
<section>
  <h2>Options</h2>
  <p class="note">Every configuration the sweep measured, and every family
  that was asked for and produced no rows. Hover a verdict for its reason and
  the file and field it came from.</p>
  <table class="opts">
    <thead><tr>
      <th>configuration</th><th>outcome</th>
      <th>recall@10</th><th>ceiling@10</th><th>storage</th><th>fan-out</th>
      {head}
    </tr></thead>
    <tbody>{''.join(body)}</tbody>
  </table>
</section>"""


def _ground(char, report, workdir=None):
    """This run's own projection when it has one, else the numbers."""
    uri = render_projection(workdir, char)
    ch = ((char or {}).get("characterization") or {})

    def row(label, key, nd=3, note=""):
        v = ch.get(key)
        if isinstance(v, str):
            return (f'<div class="cnum"><span class="cn">{esc(label)}</span>'
                    f'<span class="cv amber">{esc(v)}</span></div>')
        if v is None:
            return ""
        return (f'<div class="cnum"><span class="cn">{esc(label)}</span>'
                f'<span class="cv">{v:.{nd}f}</span>'
                f'<span class="cnote">{esc(note)}</span></div>')

    numbers = "".join([
        row("intrinsic dimensionality", "intrinsic_dimensionality", 2,
            f"of {(char or {}).get('dimension', '?')} declared"),
        row("boundary crispness", "boundary_crispness", 3,
            "d2 > 1.20 x d1, 256 regions"),
        row("ambiguous query rate", "ambiguous_query_rate", 3,
            "d2 <= 1.10 x d1"),
        row("region skew (top 10)", "skew_top10_share", 3,
            "even would be 0.039"),
    ])
    drift = ch.get("drift")
    if isinstance(drift, str):
        numbers += (f'<div class="cnum"><span class="cn">drift</span>'
                    f'<span class="cv amber">{esc(drift)}</span></div>')
    elif isinstance(drift, dict):
        numbers += (f'<div class="cnum"><span class="cn">drift '
                    f'before / after</span><span class="cv">'
                    f'{drift.get("drift_before", 0):.3f} / '
                    f'{drift.get("drift_after", 0):.3f}</span></div>')

    img = ""
    if uri:
        run_name = esc(report.get("run", "this run"))
        img = (f'<figure class="ground"><img src="{uri}" alt="a 2-D '
               'projection of this run&#39;s own sample"/>'
               f'<figcaption>The ground for <strong>{run_name}</strong>: this '
               "run&#39;s own sample, projected to 2-D by UMAP. Illustrative "
               "and declared -- the measurements above are computed in the "
               "full-dimensional space, not from this picture."
               "</figcaption></figure>")
    else:
        img = ('<p class="note">This run produced no projection, so there is '
               "no ground view here. A published image from another corpus "
               "would be a picture of something else. Re-run "
               "<code>oneground characterize --project</code> to draw this "
               "sample&#39;s own.</p>")
    return f"""
<section>
  <h2>The ground</h2>
  <p class="note">What the corpus is shaped like, measured before any
  architecture was considered.</p>
  {img}
  <div class="cnums">{numbers}</div>
</section>"""


def _log(report):
    items = []
    for e in report["decision_log"]:
        src = (f'<span class="src">{esc(e["source"])}</span>'
               if e.get("source") else "")
        items.append(f'<li class="log-{esc(e["kind"])}">'
                     f'<span class="lk">{esc(e["kind"])}</span>'
                     f'<span class="lt">{esc(e["text"])}</span>{src}</li>')
    return f"""
<section>
  <h2>Decision log</h2>
  <p class="note">One entry per rule that fired, in order. The last entries
  say what would turn each couldn&#39;t-check into a verdict.</p>
  <ol class="log">{''.join(items)}</ol>
</section>"""


def _calibration(report):
    """The calibration citation, in the footer of every report.

    Never silent: when a check has no line, the absence is what gets printed.
    """
    cal = report.get("calibration") or {}
    statements = cal.get("statements") or []
    if not statements:
        return ("<p><strong>Calibration: not stated.</strong> This report was "
                "generated without a calibration footer, which is a defect in "
                "the tool rather than a property of the run.</p>")
    items = "\n".join(f"    <li>{esc(s)}</li>" for s in statements)
    return (f"  <p><strong>Calibration this report was generated under</strong>"
            f" (<code>{esc(str(cal.get('history_path')))}</code>):</p>\n"
            f"  <ul>\n{items}\n  </ul>")


def _receipts(report):
    rows = "".join(
        f'<tr><td><code>{esc(name)}</code></td>'
        f'<td class="kind">{esc(d["kind"])}</td>'
        f'<td><code class="digest">{esc(d["sha256"])}</code></td></tr>'
        for name, d in sorted(report["inputs"].items()))
    return f"""
<section>
  <h2>Receipt</h2>
  <p class="note">Every file this report was derived from. <em>receipt</em>
  means re-derivable from the seeds and rules; <em>declared</em> means
  recorded rather than re-derivable. Nothing on this page came from anywhere
  else.</p>
  <table class="receipts">
    <thead><tr><th>file</th><th>kind</th><th>sha256</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>"""


# --------------------------------------------------------------------------
# the page
# --------------------------------------------------------------------------

def render_html(report, options, not_run_rows, recommended, char,
                verify_data, verify_info, req, workdir=None):
    names = []
    for o in options:
        for v in o.verdicts:
            if v.constraint not in names:
                names.append(v.constraint)

    env = report["environment"]
    env_line = (f"verify on {esc(env['verify_target'])} "
                f"({esc(env['verify_platform'])})"
                if env.get("verify_target") else "no verify run in this workdir")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>oneground report -- {esc(report['run'])}</title>
<style>
{_tokens_css()}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--slate);color:var(--ink);
  font-family:var(--font-ui);line-height:1.55;
  font-size:15px;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:48px 28px 96px}}
code,.digest{{font-family:var(--font-mono);font-size:.86em}}
h1{{font-size:1.7rem;margin:.2em 0 .5em;font-weight:600;letter-spacing:-.01em}}
h2{{font-size:1.05rem;margin:3rem 0 .4rem;font-weight:600;
  color:var(--ink);letter-spacing:.01em}}
.note{{color:var(--muted);margin:.2rem 0 1.1rem;font-size:.9rem;max-width:70ch}}
.masthead{{display:flex;justify-content:space-between;align-items:baseline;
  border-bottom:1px solid #33405422;padding-bottom:14px;margin-bottom:34px}}
.masthead .name{{color:var(--ochre);font-weight:600;letter-spacing:.02em}}
.masthead .env{{color:var(--muted);font-size:.85rem}}

/* the recommendation: the only emphasised element */
.rec{{background:var(--panel);border-radius:10px;padding:26px 28px;
  border-left:3px solid var(--teal)}}
.rec-none{{border-left-color:var(--amber)}}
.rec-label{{text-transform:uppercase;letter-spacing:.14em;font-size:.68rem;
  color:var(--muted)}}
.rec-config{{font-size:1.1rem;color:var(--ink)}}
.rec-why{{color:var(--muted);max-width:74ch;font-size:.9rem}}
.pills{{margin:.5rem 0 1rem}}
.pill{{display:inline-block;padding:2px 10px;border-radius:999px;
  font-size:.76rem;margin-right:8px;border:1px solid currentColor}}
.rec-constraints{{display:grid;gap:6px}}
.rec-c{{display:grid;grid-template-columns:12px 190px 1fr;gap:10px;
  align-items:baseline;font-size:.88rem}}
.rec-cn{{color:var(--muted);font-family:var(--font-mono);font-size:.8rem}}
.rec-ce{{color:var(--ochre);font-family:var(--font-mono);font-size:.72rem;
  margin-left:.5em}}
.dot{{width:8px;height:8px;border-radius:50%;display:inline-block;
  background:currentColor;transform:translateY(-1px)}}

.teal{{color:var(--teal)}} .coral{{color:var(--coral)}} .amber{{color:var(--amber)}}
.muted{{color:var(--muted)}}

table{{width:100%;border-collapse:collapse;font-size:.84rem}}
th{{text-align:left;font-weight:500;color:var(--muted);padding:8px 10px;
  border-bottom:1px solid #33405433;font-size:.76rem;
  text-transform:uppercase;letter-spacing:.07em}}
td{{padding:9px 10px;border-bottom:1px solid #2b374a55;vertical-align:top}}
tbody tr:hover{{background:#27334699}}
.opts .cfg code{{color:var(--ink)}}
.num{{text-align:right;font-family:var(--font-mono);font-size:.8rem;
  color:var(--ink)}}
td.v{{white-space:nowrap}}
.src{{display:block;color:var(--muted);font-family:var(--font-mono);
  font-size:.66rem;margin-top:2px;opacity:.75}}
/* one line per engine inside a verdict cell: the collapsed outcome above,
   each engine's own beneath it, so a cell can never present one engine's
   answer as the configuration's. */
.by-engine{{display:block;font-family:var(--font-mono);font-size:.68rem;
  margin-top:3px;opacity:.95}}
.notrun td{{color:var(--muted)}}
.kind{{color:var(--muted);font-size:.78rem}}
.receipts .digest{{color:var(--muted);font-size:.72rem;word-break:break-all}}

.cnums{{display:grid;gap:8px;background:var(--panel);border-radius:10px;
  padding:20px 24px;margin-top:14px}}
.cnum{{display:grid;grid-template-columns:220px 120px 1fr;gap:12px;
  align-items:baseline;font-size:.88rem}}
.cn{{color:var(--muted)}}
.cv{{font-family:var(--font-mono);text-align:right}}
.cnote{{color:var(--muted);font-size:.78rem}}
figure.ground{{margin:0 0 16px}}
figure.ground img{{width:100%;border-radius:10px;display:block}}
figcaption{{color:var(--muted);font-size:.8rem;margin-top:8px}}

ol.log{{list-style:none;counter-reset:l;padding:0;margin:0}}
ol.log li{{counter-increment:l;padding:10px 0 10px 46px;position:relative;
  border-bottom:1px solid #2b374a55;font-size:.88rem}}
ol.log li::before{{content:counter(l);position:absolute;left:0;top:10px;
  color:var(--muted);font-family:var(--font-mono);font-size:.74rem}}
.lk{{display:inline-block;min-width:0;margin-right:10px;color:var(--muted);
  font-family:var(--font-mono);font-size:.7rem;text-transform:uppercase;
  letter-spacing:.08em}}
.log-fails .lk{{color:var(--coral)}}
.log-meets .lk{{color:var(--teal)}}
.log-to_resolve .lk,.log-not_run .lk,.log-indistinguishable .lk{{color:var(--amber)}}
.log-recommendation .lk{{color:var(--ochre)}}
.lt{{display:block;margin-top:2px;max-width:86ch}}
footer{{margin-top:56px;padding-top:18px;border-top:1px solid #33405422;
  color:var(--muted);font-size:.8rem;max-width:80ch}}
</style>
</head><body><div class="wrap">

<div class="masthead">
  <span class="name">oneground</span>
  <span class="env">{esc(report['run'])} &middot; {env_line} &middot;
    generated {esc(report['generated_at'])}</span>
</div>

{_recommendation(report, recommended)}
{_options_table(options, not_run_rows, names)}
{_ground(char, report, workdir)}
{_log(report)}
{_receipts(report)}

<footer>
  {_calibration(report)}
  <p>The tolerance used to call two options indistinguishable on recall is
  {report['calibration']['tolerance']}, taken from the fixture specs&#39; own
  tolerance on published reference recall. It is not yet a measured
  distribution of simulated-minus-measured error.</p>
  <p>Latency verdicts are made only from a <code>verify</code> run in the
  environment the constraint targets, never from simulation. Latency measured
  by this project is a shape -- sequential, single client -- and is never
  throughput.</p>
  <p>This file makes no network requests. Fonts fall back to the system;
  the ground view, if present, is embedded.</p>
</footer>
</div></body></html>
"""
