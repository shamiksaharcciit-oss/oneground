"""Task 045, finding 3: a machine token in the middle of an English sentence.

`couldnt_check` is a constant two machines compare. It appeared in 16 of the
arXiv report's 37 claim sentences, printed where a reader was being addressed,
and `outcome_label` -- the translation into *couldn't-check* -- already existed
three hundred lines below the two renderers that did not call it.

**This asserts it over a real report**, rebuilt from the tracked arXiv bundle
rather than read out of the `report.json` that bundle carries. The stored one
still holds the token and will until it is regenerated: it was written before
the repair. Conflating the artifact with the code is how a fix gets reported
as not working -- or, worse, as working when only the artifact happened to be
clean.

`meets` and `fails` are not tested for. They are the English words the
sentences are made of, and a rule that forbade them would forbid the prose.
`couldnt_check` is the one outcome whose constant is not a word anybody would
write, which is exactly why it read as a defect on the page.
"""

import json
import os

from .. import report as rep
from . import claims as cl
from . import verdict as vd
from .test_one_fact_one_sentence import WORKDIR, _options, _report

TOKEN = "couldnt_check"
READER = "couldn't-check"


def _all_claims():
    doc = _report()
    options = _options(doc)
    vd.mark_indistinguishable(options)
    with open(os.path.join(WORKDIR, "verify_info.json"), encoding="utf-8") as f:
        verify_info = json.load(f)
    claims = rep.decision_claims(
        options, [], vd.recommend(options), doc["constraints"], verify_info,
        env_id=(doc.get("environment") or {}).get("id"))
    with open(os.path.join(WORKDIR, "verify.json"), encoding="utf-8") as f:
        claims = list(claims) + list(rep.qps_max_claims(json.load(f)))
    return doc, claims


def test_no_claim_in_the_rebuilt_arxiv_report_prints_the_outcome_constant():
    doc, claims = _all_claims()

    # The defect is real in the artifact, which is what makes the absence
    # below a result rather than a property of an empty list.
    stored = sum(1 for d in doc["claims"] if TOKEN in (d.get("text") or ""))
    assert stored == 16, (
        "the stored report no longer carries the 16 token-bearing sentences "
        "this test is the control for; it has %d" % stored)

    assert claims, "the rebuild produced no claims: this check would be vacuous"
    bad = [(c.kind, c.text) for c in claims if TOKEN in (c.text or "")]
    assert bad == [], bad


def test_the_readers_word_is_what_replaced_it():
    """Not deleted -- translated. A sentence that simply dropped the outcome
    would say less than the one that printed a constant."""
    _, claims = _all_claims()
    said = [c for c in claims if READER in (c.text or "")]
    assert said, [c.kind for c in claims]
    assert cl.outcome_label(vd.COULDNT_CHECK) == READER


def test_the_rebuilt_report_has_the_claim_count_finding_4_predicts():
    """37 before, 25 after, and the two numbers come from the same machinery.

    Stated here rather than in the finding 4 file because it is the report's
    whole claim set, which only `decision_claims` plus `qps_max_claims`
    produces.
    """
    doc, claims = _all_claims()
    assert len(doc["claims"]) == 37
    assert len(claims) == 25
