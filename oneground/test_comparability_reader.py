"""The reader finds every fact in every carrier it declares (task 043).

WHY THIS FILE EXISTS
--------------------
`comparability.facts_of` had failed the same way four times, in one function.

  041  `oneground` read from the receipts only, so a run whose report carried
       the commit reported `code: unknown`. **Published as a finding about the
       artifacts** before anyone saw it was the reader.
  043  `run_environment` read from `report.json` only, so a characterize-only
       workdir reported every provenance field `None` — identical to the
       symptom of a writer that never wrote.
  043  `library_versions` read from the receipts only. Caught by the first
       version of this file, on its first run, on a fact nobody was
       investigating.
  043  **`report.json` carries two environment blocks on purpose** —
       `environment` is the machine that measured, `run_environment` is the
       one that wrote the report — and the reader took the second. On the
       published arXiv fixture that discarded a pod id and returned a Windows
       laptop beside a Linux platform, in one dict, for one run.

The first three are ABSENCES. The fourth is a **wrong value**, and no
exhaustive absence test can catch it: the field was present and plausible.

So the carriers are declared as data in `FACT_CARRIERS`, the order being the
precedence rule written down, and this file asserts **against that
declaration** rather than against a restatement of it. That is what makes
absence and wrong-carrier checkable by the same test: the declaration says
where a fact may live and which source wins, and both halves are then
assertable.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground import comparability as CMP                      # noqa: E402

#: How to pull each declared fact back out of `facts_of`'s result. Only this
#: mapping is written by hand; every carrier comes from the declaration.
EXTRACT = {
    "code": lambda f: f.get("code_block"),
    "libraries": lambda f: f.get("libraries"),
    "platform": lambda f: f.get("platform"),
    "python_version": lambda f: f.get("python_version"),
    "requirements_file": lambda f: f.get("settings_from") and True,
    "environment_id": lambda f: f.get("environment_id"),
    "installation": lambda f: f.get("installation"),
}

#: A value to write for each fact, shaped as the real one is.
SAMPLE = {
    "code": {"commit": "a" * 40, "dirty": False, "version": "0.1.0"},
    "libraries": {"numpy": "2.5.3"},
    "platform": "Linux-test",
    "python_version": "3.12.3",
    "requirements_file": {"sha256": "c" * 64},
    "environment_id": "pod-under-test",
    "installation": "b" * 16,
}


def _cases():
    """Every (fact, carrier) pair the reader declares it can read."""
    out = []
    for fact, carriers in CMP.FACT_CARRIERS.items():
        for where, path in carriers:
            files = (list(CMP.INFO_FILES) if where == CMP.ANY_INFO
                     else [where])
            for f in files:
                out.append(pytest.param(fact, f, path,
                                        id="%s-%s-%s" % (fact, f, path)))
    return out


def _nest(path, value):
    out = value
    for part in reversed(str(path).split(".")):
        out = {part: out}
    return out


def _write(workdir, filename, payload):
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, filename), "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


@pytest.mark.parametrize("fact,filename,path", _cases())
def test_the_reader_finds_each_declared_fact_in_each_declared_carrier(
        tmp_path, fact, filename, path):
    """One fact, one declared carrier, nothing else present.

    Parametrised from `FACT_CARRIERS` itself, so a carrier added to the
    declaration is tested without anyone remembering to add a case, and a
    carrier the reader claims and does not honour names itself in the failure.
    """
    wd = str(tmp_path / "wd")
    _write(wd, filename, _nest(path, SAMPLE[fact]))
    got = EXTRACT[fact](CMP.facts_of(wd))
    assert got, (
        "%s is declared to be readable from %s:%s and the reader did not "
        "find it there. A reader that consults fewer sources than it declares "
        "reports an absence that is its own." % (fact, filename, path))


def test_the_measuring_machine_wins_over_the_reporting_one():
    """The wrong-value defect, as a test rather than a story.

    `report.json` carries both blocks. `environment` is where the run was
    measured; `run_environment` is where the report was written. When they
    disagree — which is every pod run reported from a laptop — the reader must
    take the first, or it reports a pod run as a local one and discards the
    only thing that can make `machine` knowable.
    """
    lhs = CMP.FACT_CARRIERS["environment_id"]
    measured = [i for i, (w, p) in enumerate(lhs)
                if p.endswith("environment.environment_id")
                and not p.startswith("run_")]
    reported = [i for i, (w, p) in enumerate(lhs)
                if "run_environment" in p]
    assert measured and reported, lhs
    assert min(measured) < min(reported), (
        "the measuring machine must precede the reporting one in the "
        "declaration; the order IS the precedence rule: %s" % (lhs,))


def test_the_published_fixture_reads_as_one_machine():
    """NOT synthetic. The defect as it actually shipped.

    Before task 043 this returned `local:windows-amd64` and `pod: None`
    alongside `platform: Linux-...`: one facts dict describing two machines.
    """
    wd = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "fixtures", "arxiv-150k", "report")
    if not os.path.isdir(wd):
        pytest.skip("the published report fixture is not present")
    f = CMP.facts_of(wd)
    if not f.get("platform"):
        pytest.skip("this fixture records no platform")
    linux = "linux" in str(f["platform"]).lower()
    local = str(f.get("environment_id") or "").startswith("local:")
    assert not (linux and local), (
        "a Linux platform with a local: environment_id is the reporting "
        "laptop read as the measuring machine (facts: %s / %s)"
        % (f.get("environment_id"), f.get("platform")))
    assert f.get("pod"), (
        "this run was measured on a pod and the pod id must survive to "
        "`pod`, which is the only path by which `machine` can be known")


def test_the_reader_reports_a_genuine_absence_as_absent(tmp_path):
    """The mirror, so the parametrised test cannot pass against a reader that
    returns constants."""
    wd = str(tmp_path / "empty")
    os.makedirs(wd, exist_ok=True)
    facts = CMP.facts_of(wd)
    for fact, extract in EXTRACT.items():
        assert not extract(facts), "%s invented from an empty workdir" % fact


def test_every_declared_fact_is_actually_read():
    """A fact in the declaration that `facts_of` never consults is a promise
    the reader does not keep, and the declaration is the promise."""
    unread = [f for f in CMP.FACT_CARRIERS if f not in EXTRACT]
    assert not unread, (
        "declared but not covered here: %s — add it to EXTRACT and SAMPLE, "
        "or remove it from FACT_CARRIERS" % unread)
