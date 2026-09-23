"""The UI in a real browser, and proved read-only (task 041, steps 9 and 10).

Step 9: after a session that exercises every page of every run, every
`MANIFEST.sha256` under the runs directory verifies unchanged and no file was
added. The lab proves this for one workdir; this proves it for a directory.

Step 10: a 200 is not a loaded page. Task 025 found the landing page hanging
for the developer while every endpoint answered correctly, so these drive a
real browser and ask what the page ended up holding.
"""
import contextlib
import hashlib
import json
import os
import shutil
import tempfile
import urllib.parse
import urllib.request

import pytest

from oneground.lab import server as labserver

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = os.path.join(REPO, "runs", "041-ui")


def _snapshot(root):
    """Every file under `root`, by path and digest."""
    out = {}
    for base, _, files in os.walk(root):
        for name in files:
            p = os.path.join(base, name)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hashlib.sha256(
                    f.read()).hexdigest()
    return out


@contextlib.contextmanager
def _ui(runs_dir):
    lab = labserver.LabServer(runs_dir=runs_dir)
    lab.start()
    try:
        yield lab
    finally:
        lab.httpd.shutdown()
        lab.httpd.server_close()


def _get(lab, path, params=None):
    q = urllib.parse.urlencode(list((params or []) + [("token", lab.token)]))
    base = lab.url.split("?")[0]
    with urllib.request.urlopen(base + path.lstrip("/") + "?" + q) as r:
        return json.loads(r.read())


def _local_copy(tmp):
    if not os.path.isdir(LOCAL):
        pytest.skip("no local runs/041-ui")
    dst = os.path.join(tmp, "runs")
    shutil.copytree(LOCAL, dst)
    return dst


# --------------------------------------------------------- step 9: read-only
def test_a_session_over_a_directory_writes_nothing():
    """Every page of every run, then every digest re-checked and the file
    list compared. The lab proves this for one workdir; the UI serves many."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _local_copy(tmp)
        before = _snapshot(root)
        with _ui(root) as lab:
            names = [r["name"] for r in lab.index["runs"]]
            _get(lab, "/api/check")
            _get(lab, "/api/runs")
            for name in names:
                _get(lab, "/api/headline", [("run", name)])
                try:
                    _get(lab, "/api/evidence", [("run", name)])
                except urllib.error.HTTPError as e:
                    # a run with no report has no claims; a 400 with its
                    # reason is the right answer and not a write
                    assert e.code == 400
            for i in range(len(names) - 1):
                _get(lab, "/api/compare",
                     [("run", names[i]), ("run", names[i + 1])])
        after = _snapshot(root)
        assert sorted(after) == sorted(before), "a file was added or removed"
        assert after == before, "a file changed"


def test_every_manifest_still_verifies_after_a_session():
    with tempfile.TemporaryDirectory() as tmp:
        root = _local_copy(tmp)
        with _ui(root) as lab:
            _get(lab, "/api/runs")
            for r in lab.index["runs"]:
                _get(lab, "/api/headline", [("run", r["name"])])
        for entry in labserver.verify_manifests(
                [os.path.join(root, n) for n in sorted(os.listdir(root))]):
            if entry.get("manifest") is None:
                continue
            assert entry["all_verified"] is True, entry["directory"]


def test_the_server_has_no_write_path():
    """Asserted on the source, not only on behaviour: nothing in the modules
    the UI serves from opens a file for writing.

    Task 046 replaced this test's own string scan with `guard.check_write_path()`.
    The rule has not moved -- the served modules still write nothing -- but
    the tree now holds one module that *may* write, so the scan that decides
    has to see a write however it is spelled.

    Keeping the string scan beside the parsed one would have been a second
    implementation of one rule (`docs/PRACTICE.md` section 2, warning 2), and
    it did not survive the day it acquired a rival: the string scan looks for
    a quoted `"w"` anywhere in a served module, and `guard.py` now declares
    `WRITING_MODES = ("w", "a", "x", "+")` -- so the old test failed on the
    constant that spells out the rule it was enforcing. It would also have
    missed the inverse case, a module that renames a file into place, because
    `os.replace` contains no quoted mode at all.

    The scan's own mutants are in `test_compose.py`: ten spellings of a write
    it must catch, six reads and string methods it must not.
    """
    from oneground.lab import guard
    assert guard.check_write_path() == {}, "a served module writes"
    assert guard.WRITE_MODULES == ("compose.py",)


# ------------------------------------------------------- step 10: a browser
LOOKED_FOR = ("chrome", "chromium", "msedge")


@contextlib.contextmanager
def _browser(**kw):
    from oneground.lab import cdp
    found = cdp.find_browser()
    if not found:
        pytest.skip("no Chromium-family browser on this machine (looked for "
                    + ", ".join(LOOKED_FOR) + "), so the page was not "
                    "loaded; this does not pass")
    try:
        b = cdp.Browser(**kw)
    except (OSError, RuntimeError) as e:
        pytest.skip(f"{os.path.basename(found)} would not start headless "
                    f"({e}), so the page was not loaded; this does not pass")
    try:
        yield b
    finally:
        b.close()


def _go(b, url, frag):
    b.goto(url)
    b.evaluate(f"window.location.hash = {frag!r}")
    b.evaluate("window.dispatchEvent(new HashChangeEvent('hashchange'))")


def _state(b):
    return json.loads(b.evaluate(
        "JSON.stringify(window.__uiState ? window.__uiState() : null)"))


@pytest.mark.parametrize("width,height", [(1200, 900), (500, 800)])
def test_every_page_renders_in_a_browser_at_both_widths(width, height):
    if not os.path.isdir(LOCAL):
        pytest.skip("no local runs/041-ui")
    with _ui(LOCAL) as lab, _browser(width=width, height=height) as b:
        names = [r["name"] for r in lab.index["runs"]]

        _go(b, lab.url, "#/runs")
        b.wait_for("(() => { const s = window.__uiState && window.__uiState();"
                   " return !!(s && s.runRows > 1 && !s.error); })()",
                   timeout=60)
        s = _state(b)
        assert s["mode"] == "runs"
        assert s["runRows"] == len(names) + 1, s

        for name in names:
            _go(b, lab.url, "#/run/" + urllib.parse.quote(name))
            b.wait_for("(() => { const s = window.__uiState && "
                       "window.__uiState(); return !!(s && !s.error && "
                       "document.querySelector('.finding')); })()", timeout=60)
            assert _state(b)["error"] is None, name

        _go(b, lab.url, "#/compare/" + urllib.parse.quote(names[0]) + "/"
            + urllib.parse.quote(names[1]))
        b.wait_for("(() => { const s = window.__uiState && window.__uiState();"
                   " return !!(s && s.verdict && !s.error); })()", timeout=60)
        s = _state(b)
        assert s["error"] is None
        assert s["verdict"], "the verdict did not reach the page"


def test_the_three_counts_all_reach_the_page_including_the_zero():
    """stackexchange records 0 couldn't-check. The zero is a count, and a
    page that drops it makes a different statement."""
    if not os.path.isdir(LOCAL):
        pytest.skip("no local runs/041-ui")
    with _ui(LOCAL) as lab, _browser() as b:
        _go(b, lab.url, "#/run/stackexchange-150k-via-characterize")
        b.wait_for("(() => !!document.querySelector('.counts .count'))()",
                   timeout=60)
        classes = _state(b)["counts"]
        assert len(classes) == 3, classes
        assert any("outcome-couldnt_check" in c for c in classes)
        shown = b.evaluate(
            "document.querySelector('.outcome-couldnt_check').textContent")
        assert shown.startswith("0"), shown


def test_a_not_comparable_pair_shows_two_observations_and_no_joined_table():
    if not os.path.isdir(LOCAL):
        pytest.skip("no local runs/041-ui")
    with _ui(LOCAL) as lab, _browser() as b:
        _go(b, lab.url, "#/compare/arxiv-smoke/support-tickets-2026q3")
        b.wait_for("(() => { const s = window.__uiState && window.__uiState();"
                   " return !!(s && s.verdict); })()", timeout=60)
        s = _state(b)
        assert s["joinedTables"] == 0, "two runs were lined up in one table"
        assert s["observations"] == 2


def test_a_non_field_citation_is_rendered_as_its_kind_not_as_a_dead_link():
    if not os.path.isdir(LOCAL):
        pytest.skip("no local runs/041-ui")
    with _ui(LOCAL) as lab, _browser() as b:
        _go(b, lab.url, "#/run/arxiv-150k-via-characterize/report")
        b.wait_for("(() => !!document.querySelector('ol.claims li'))()",
                   timeout=60)
        s = _state(b)
        assert s["notNavigable"] > 0, "no non-field citation reached the page"
        assert s["navigable"] > 0
        kinds = b.evaluate(
            "JSON.stringify(Array.from(document.querySelectorAll("
            "'.entry.not-navigable .entry-kind')).map(n => n.textContent))")
        assert "rule" in json.loads(kinds)
        # and none of them is an anchor
        anchors = b.evaluate(
            "document.querySelectorAll('.entry.not-navigable a').length")
        assert int(anchors) == 0, "a non-field citation was rendered as a link"


def test_a_run_with_no_report_says_so_rather_than_rendering_empty():
    if not os.path.isdir(LOCAL):
        pytest.skip("no local runs/041-ui")
    with _ui(LOCAL) as lab, _browser() as b:
        _go(b, lab.url, "#/run/acme-existing")
        b.wait_for("(() => !!document.querySelector('.finding'))()",
                   timeout=60)
        text = b.text(".finding")
        assert "has not reported" in text
        assert "verify" in text


# ------------------------------------------------------------- step 2: --demo
def test_the_demo_opens_a_real_run_not_a_mock():
    """Real receipts, real digests verifying, the real report with its real
    couldn't-checks. Nothing on the page is fabricated for the demonstration."""
    from oneground.lab import runs as runsmod
    ix = runsmod.demo_index()
    row = ix["runs"][0]
    assert row["manifest"]["all_verified"] is True
    assert row["manifest"]["n_files"] >= 5, row["manifest"]
    assert row["report"]["tier"] == 1
    assert row["report"]["n_claims"] > 0
    assert all(row["stages"].values()), row["stages"]


def test_the_demo_downloads_nothing_and_says_so():
    """The brief allows a fetch "if absent". Nothing the read half needs is
    absent -- the fixture's report bundle is in the repository -- so there is
    no download to name and no refusal to offer, and the page says that rather
    than implying a fetch happened."""
    from oneground.lab import runs as runsmod
    demo = runsmod.demo_index()["demo"]
    assert demo["fetched"] is None
    assert "nothing was downloaded" in demo["fetched_note"]


def test_the_demo_says_whose_corpus_it_is_inside_the_drawing():
    """In the view, not as fine print, and carried in the drawing so it
    survives a screenshot -- the rule the lab's projection caption follows."""
    from oneground.lab import runs as runsmod
    from oneground.lab.receipt import draw_receipt
    from oneground.lab.views.run_list import RunListView
    d = draw_receipt(RunListView(), runsmod.demo_index())
    label = d.figures["demo"]["label"]
    assert "not your data" in label
    assert "arxiv-150k" in label
    assert d.figures["demo"]["way_out"]
    assert "requirements.yaml" in d.figures["demo"]["way_out"]


def test_the_demo_names_what_it_cannot_show():
    """The fixture ships no simulator state, so the ground and the trace are
    not reachable. A gap with its reason, not a link that opens nothing."""
    from oneground.lab import runs as runsmod
    demo = runsmod.demo_index()["demo"]
    assert "ground" in demo["not_available"]
    assert "no simulator state" in demo["not_available"]


def test_the_demo_banner_reaches_the_page():
    from oneground.lab import runs as runsmod
    if not os.path.isdir(os.path.join(runsmod.demo_root(), "report")):
        pytest.skip("the arxiv-150k fixture is not in this checkout")
    lab = labserver.LabServer(demo=True)
    lab.start()
    try:
        with _browser() as b:
            _go(b, lab.url, "#/runs")
            b.wait_for("(() => !!document.querySelector('.demo-banner'))()",
                       timeout=60)
            s = _state(b)
            assert s["demoBanner"] == 1
            assert s["error"] is None
            assert "not your data" in b.text(".demo-label")
    finally:
        lab.httpd.shutdown()
        lab.httpd.server_close()


def test_the_demo_writes_nothing_into_the_fixture():
    from oneground.lab import runs as runsmod
    fixture = runsmod.demo_root()
    if not os.path.isdir(os.path.join(fixture, "report")):
        pytest.skip("the arxiv-150k fixture is not in this checkout")
    before = _snapshot(fixture)
    lab = labserver.LabServer(demo=True)
    lab.start()
    try:
        name = lab.index["runs"][0]["name"]
        _get(lab, "/api/check")
        _get(lab, "/api/runs")
        _get(lab, "/api/headline", [("run", name)])
        _get(lab, "/api/evidence", [("run", name)])
    finally:
        lab.httpd.shutdown()
        lab.httpd.server_close()
    assert _snapshot(fixture) == before, "the demo touched the fixture"
