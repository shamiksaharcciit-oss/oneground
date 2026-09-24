"""The receipt write sites route their paths through `public_path` (044f).

Companion to `test_no_tracked_file_carries_a_machine_identifier`, and **not a
replacement for it**. That one scans what git tracks; this one scans where
receipts are written. The gap between those two subjects held four write sites
putting `os.path.abspath(requirements_path)` into `build_info.json`,
`simulate_info.json` and `verify_info.json` -- invisible to the tracked scan
because `runs/` is gitignored, and read by a publisher because
`corpora/export_teaser_data.py` reads `runs/`.

Two checks that see different things are not redundant. This pair is the
proof, and deleting either restores a blind spot.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.receipts import pathguard as pg                    # noqa: E402

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))

SHIPPED = [os.path.join(REPO, "oneground"), os.path.join(REPO, "corpora")]


def _fmt(found):
    return "\n".join(
        "  %s:%d  %r in %s()  [caught by %s]" % f for f in found)


#: The one finding this guard reports and 044f did not fix, with the reason
#: and the task that closes it.
#:
#: `requirements_file.path` is written by four receipt writers as
#: `os.path.abspath(...)`, so every local `build_info.json`,
#: `simulate_info.json` and `verify_info.json` carries the operator's home
#: directory. It was fixed, and the fix was reverted: **this field is
#: resolvable, not descriptive.** `proposals/propose.py` reads it back out of
#: `simulate_info.json` and reopens the file, so a public path breaks
#: resolution whenever the requirements file sits outside the checkout -- 30
#: tests in `test_propose.py`, measured.
#:
#: That makes it a behaviour change on the write path with a consumer
#: attached, which belongs to **task 044g** and not to the task that built
#: this guard. Recorded here rather than declared in `DECLARED_PUBLIC`,
#: because a declaration states what the code guarantees and this code
#: guarantees the opposite.
KNOWN_OPEN = {
    ("oneground/characterize.py", "path", "run"),
    ("oneground/characterize.py", "path", "run_declared"),
    ("oneground/simulate/__init__.py", "path", "run"),
    ("oneground/verify/__init__.py", "path", "_write"),
}


# ------------------------------------------------------------- the guard
def test_no_receipt_write_site_records_a_machine_local_path():
    found = pg.findings(SHIPPED, REPO)
    new = [f for f in found if (f[0], f[2], f[3]) not in KNOWN_OPEN]
    assert new == [], (
        "these receipt fields hold a path that did not come from "
        "receipts.public_path:\n" + _fmt(new))


def test_the_known_open_set_is_exactly_what_is_still_open():
    """Pinned to a current state deliberately, and it says so.

    `docs/PRACTICE.md` section 2 warning 7 is that a test pinned to a current
    state breaks when a later task legitimately changes it. That is the
    intended behaviour here: when 044g closes these four, this test fails and
    whoever closes them deletes the entry. A one-sided allowlist would let
    them be quietly fixed and the exception live on, which is how an
    allowlist becomes a place defects go to be forgotten.
    """
    found = pg.findings(SHIPPED, REPO)
    still = {(f[0], f[2], f[3]) for f in found} & KNOWN_OPEN
    assert still == KNOWN_OPEN, (
        "KNOWN_OPEN lists something the guard no longer reports: %s. If task "
        "044g closed it, delete the entry."
        % sorted(KNOWN_OPEN - still))


# --------------------------------------- it can find what it was written for
def test_the_guard_names_a_planted_instance_synthetic():
    """A guard that cannot fail is not a guard.

    Synthetic, and it says which part is not evidence: this shows the detector
    fires, **not** that it would have caught the real instances. That is
    `test_the_guard_rediscovers_the_requirements_file_instance` below, which
    uses the real pre-fix source.
    """
    src = (
        "import os\n"
        "def write(p, wd):\n"
        "    write_json_stable(p, {'path': os.path.abspath(wd)})\n")
    found = pg.findings_in_source(src, "planted.py")
    assert [f[2] for f in found] == ["path"], found
    assert found[0][4] == "origin"


def test_the_guard_rediscovers_the_requirements_file_instance():
    """NOT synthetic: the real write site, exactly as it stood before 044f.

    The rule from `docs/PRACTICE.md` -- run the audit against the source as it
    was before the fix and require it to name the known instance. This is that
    instance, verbatim.
    """
    before = (
        "import os\n"
        "def run(workdir, requirements_path):\n"
        "    info = {\n"
        "        'requirements_file': {'path': "
        "os.path.abspath(requirements_path),\n"
        "                              'sha256': "
        "sha256_file(requirements_path)},\n"
        "    }\n"
        "    write_json_stable(os.path.join(workdir, 'build_info.json'), "
        "info)\n")
    found = pg.findings_in_source(before, "characterize.py")
    assert "path" in {f[2] for f in found}, (
        "the guard cannot rediscover the instance it was written for:\n"
        + _fmt(found))


def test_the_same_source_is_clean_once_it_is_fixed():
    """The mirror. Without it the test above passes against a guard that
    flags everything."""
    after = (
        "def run(workdir, requirements_path):\n"
        "    info = {\n"
        "        'requirements_file': {'path': "
        "public_path(requirements_path),\n"
        "                              'sha256': "
        "sha256_file(requirements_path)},\n"
        "    }\n"
        "    write_json_stable(os.path.join(workdir, 'build_info.json'), "
        "info)\n")
    assert pg.findings_in_source(after, "characterize.py") == []


def test_a_dict_wrapped_in_the_table_form_is_public():
    """`public_paths_in({...})` is the correct idiom and must not be a finding.

    It was, briefly: the walk descended into the sanitiser and judged the
    dict's keys one at a time, so the guard failed the *fixed* form of task
    044c's own instance. A guard that fails the code written to satisfy it is
    a guard that gets switched off.
    """
    src = ("def run(p, vp):\n"
           "    write_json_stable(p, {'inputs': "
           "public_paths_in({'path': vp})})\n")
    assert pg.findings_in_source(src, "sweep.py") == []


def test_a_nested_dicts_path_is_not_blamed_on_its_parent_key():
    """A finding on the wrong key sends the reader to a line where nothing is
    wrong, which is worse than no finding."""
    src = ("import os\n"
           "def run(p, t):\n"
           "    write_json_stable(p, {'epsilon': {'requested': 0.2,\n"
           "        'trace': os.path.basename(t)}})\n")
    named = [f[2] for f in pg.findings_in_source(src, "m.py")]
    assert "epsilon" not in named, named
    assert "trace" in named, named


# --------------------------------------------------- it is not vacuous
def test_the_guard_actually_read_the_package():
    """PRACTICE section 2, warning 6: a check that skips where it would fail.

    An empty roots list, a typo in a path, or a walk that matched no files
    would make the assertion above pass while reading nothing.
    """
    assert all(os.path.isdir(d) for d in SHIPPED), SHIPPED
    seen = 0
    for root in SHIPPED:
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            seen += sum(1 for f in files
                        if f.endswith(".py") and not f.startswith("test_"))
    assert seen > 50, "only %d modules scanned" % seen


def test_scratch_is_reported_rather_than_asserted():
    """Why `tasks/scratch/` is not in `SHIPPED`, stated rather than implied.

    Task 044c's instance was a scratch script whose output was committed, so
    scratch is squarely in this guard's subject. It is **not** asserted on
    because it is gitignored: it is absent in CI, where the assertion would
    pass having read nothing -- warning 6 again, arrived at from the other
    side. `known_roots` includes it when it exists so the guard can be run
    over it by hand, which is what to do before committing a scratch script's
    output.
    """
    roots = pg.known_roots(REPO)
    scratch = os.path.join(REPO, "tasks", "scratch")
    if os.path.isdir(scratch):
        assert scratch in roots
    else:
        pytest.skip("no scratch directory here, which is the CI case")
