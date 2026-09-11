"""Every path the calibration workflow names must exist in the commit.

Calibration run #5 died on

    .github/scripts/merge_history.py: No such file or directory

The file was in the commit the job checked out. It stopped being on disk
because the push step checked out the `calibration` branch -- whose tree is
rooted three commits earlier and has no `.github/scripts/` -- into the same
working tree, one line before invoking it. Two defects, then, and this module
guards both:

  * a path that is simply not there (nothing referenced it into existence), and
  * a path that is there at checkout and gone by the time it runs.

The second is the one that actually bit, so it gets a structural assertion
rather than a filesystem one: the push must not check the target branch out
into the job's working tree at all.

    .venv/Scripts/python.exe -m pytest .github/scripts/test_referenced_paths.py
"""

import glob as globlib
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORKFLOWS = sorted(globlib.glob(os.path.join(HERE, "..", "workflows", "*.yml")))
ACTIONS = sorted(globlib.glob(
    os.path.join(HERE, "..", "actions", "*", "action.yml")))

# A path we are prepared to assert on: something the runner opens by name.
RUNNABLE = (".py", ".sh", ".yml", ".yaml", ".txt")

# Written by a step rather than committed, so absence is correct.
GENERATED = ("/.ci/", ".ci/", ".cache/", "/tmp/")


def _sources():
    """(label, text, base_dir) for every workflow and composite action."""
    for p in WORKFLOWS + ACTIONS:
        rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
        with open(p, encoding="utf-8") as f:
            yield rel, f.read(), os.path.dirname(os.path.abspath(p))


def _strip_comments(text):
    return "\n".join(l for l in text.splitlines()
                     if not l.lstrip().startswith("#"))


def _expand(token, base_dir):
    """Resolve the one GitHub expression that names a path.

    `${{ github.action_path }}` is the composite action's own directory, so
    `${{ github.action_path }}/../../scripts/x.py` is a real, checkable path.
    Any token still carrying an expression after this is runtime-dependent
    and is skipped rather than guessed at.
    """
    token = token.replace("${{ github.action_path }}", base_dir)
    token = token.replace("${{ github.workspace }}", ROOT)
    return token


def _referenced(text, base_dir):
    """Paths named inside `run:` blocks and by `uses: ./`."""
    code = _strip_comments(text)
    found = set()

    for m in re.finditer(r"uses:\s*(\./\S+)", code):
        found.add(_expand(m.group(1), base_dir))

    # Bare tokens that look like a path to a file the runner executes or reads.
    for m in re.finditer(r"[\"']?((?:\$\{\{[^}]*\}\}/)?[\w./$@{}\-]+"
                         r"(?:" + "|".join(re.escape(e) for e in RUNNABLE) +
                         r"))[\"']?", code):
        tok = m.group(1)
        if "/" not in tok and not tok.endswith(".txt"):
            continue                      # `python-version: '3.12'` and friends
        found.add(_expand(tok, base_dir))

    out = set()
    for tok in found:
        if "${{" in tok or "*" in tok:
            continue                      # runtime-dependent, or a filter
        if any(g in tok.replace(os.sep, "/") for g in GENERATED):
            continue
        out.add(tok)
    return out


def _resolve(tok):
    return tok if os.path.isabs(tok) else os.path.join(ROOT, tok)


@pytest.mark.parametrize("label,_t,_b", [(l, t, b) for l, t, b in _sources()],
                         ids=[l for l, _, _ in _sources()])
def test_every_path_the_workflow_names_exists(label, _t, _b):
    missing = sorted(tok for tok in _referenced(_t, _b)
                     if not os.path.exists(_resolve(tok)))
    assert not missing, f"{label} references paths that are not in the repo: {missing}"


def test_the_scripts_the_action_invokes_are_all_named_and_present():
    """The explicit list, so a reader can see what run #5 needed on disk."""
    for name in ("push-calibration.sh", "merge_history.py",
                 "count_contradictions.py", "make_ci_corpus.py",
                 "fetch-glove.sh"):
        assert os.path.exists(os.path.join(HERE, name)), name


@pytest.mark.parametrize("label,_t,_b", [(l, t, b) for l, t, b in _sources()],
                         ids=[l for l, _, _ in _sources()])
def test_every_trigger_path_filter_still_matches_something(label, _t, _b):
    """A stale `paths:` filter disables a trigger silently.

    It is not an error the way a missing script is, but a calibration workflow
    that stopped firing on a pin change would be invisible for exactly as long
    as nobody looked.
    """
    stale = []
    for m in re.finditer(r"^\s+-\s+'([^']+)'\s*$", _t, re.M):
        pat = m.group(1)
        if "/" not in pat or pat.startswith("0 "):
            continue
        hits = globlib.glob(os.path.join(ROOT, pat.replace("**", "*")),
                            recursive=True)
        if not hits and not os.path.exists(os.path.join(ROOT, pat)):
            stale.append(pat)
    assert not stale, f"{label}: path filters matching nothing: {stale}"


def test_the_push_never_checks_the_target_branch_into_the_working_tree():
    """Run #5's defect, asserted structurally.

    `git checkout -B calibration ...` swaps the job's working tree for a tree
    that does not contain `.github/scripts/`, which deletes the very scripts
    the next two steps invoke. Building the commit with plumbing is what makes
    the scripts' paths stay valid, so the absence of a checkout is the
    invariant worth pinning, not the path resolution.
    """
    with open(os.path.join(HERE, "push-calibration.sh"), encoding="utf-8") as f:
        code = _strip_comments(f.read())
    for forbidden in ("checkout -B", "git checkout", "git switch",
                      "git reset --hard"):
        assert forbidden not in code, \
            f"{forbidden!r} moves the job's working tree off the commit it " \
            f"was checked out at; run #5 died of exactly that"
