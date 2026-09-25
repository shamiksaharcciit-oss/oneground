"""`oneground library check-card` -- the command, not the schema.

`test_card_schema.py` proves the validator's rules; this proves the
command reaches it: a file on disk, exit codes, and that submission is
genuinely not reachable from here (`docs/LIBRARY.md` §6).

    python oneground/library/test_cli.py
    pytest oneground/library/test_cli.py
"""

import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.library import cli               # noqa: E402
from oneground.library.test_card_schema import _well_formed_card  # noqa: E402


def _capture(fn, *a, **kw):
    buf, orig_out = io.StringIO(), sys.stdout
    err_buf, orig_err = io.StringIO(), sys.stderr
    sys.stdout, sys.stderr = buf, err_buf
    try:
        rc = fn(*a, **kw)
    finally:
        sys.stdout, sys.stderr = orig_out, orig_err
    return rc, buf.getvalue() + err_buf.getvalue()


def _write(tmp, card, name="card.json"):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(card, f)
    return p


def test_a_well_formed_card_is_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, _well_formed_card())
        rc, out = _capture(cli.main, ["check-card", p])
        assert rc == 0, out
        assert "accepted" in out


def test_a_card_missing_a_required_field_is_refused_and_named():
    with tempfile.TemporaryDirectory() as tmp:
        card = _well_formed_card()
        del card["licence"]
        p = _write(tmp, card)
        rc, out = _capture(cli.main, ["check-card", p])
        assert rc != 0
        assert "licence" in out


def test_invalid_json_is_refused_not_a_traceback():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "card.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{not json")
        rc, out = _capture(cli.main, ["check-card", p])
        assert rc != 0
        assert "not valid JSON" in out


def test_a_missing_file_is_refused_by_name():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "nope.json")
        rc, out = _capture(cli.main, ["check-card", p])
        assert rc != 0
        assert "nope.json" in out


def test_check_card_never_writes_anything():
    """docs/LIBRARY.md §6 leaves submission's transport unsettled; this
    command answers accepted/refused and touches nothing else -- proven
    by diffing the directory, not by reading the source and trusting it."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, _well_formed_card())
        before = sorted(os.listdir(tmp))
        _capture(cli.main, ["check-card", p])
        after = sorted(os.listdir(tmp))
        assert before == after


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
