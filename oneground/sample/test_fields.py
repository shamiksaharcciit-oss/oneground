"""The field map and the reader dispatch.

The contract these guard is narrow and load-bearing: a spec that declares no
`field_map` must behave exactly as it did before task 016, because arxiv-150k's
published digests were produced by that path and nothing here is allowed to
move them.
"""

import os

import pytest
import yaml

from ..sample import READERS, sample_for_spec
from ..sample import arxiv as arxiv_reader
from ..sample import stackexchange as se_reader
from ..sample.fields import (DEFAULT_DRIFT_CUTOFF, DEFAULTS, FieldMapError,
                             drift_cutoff, field_map)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "fixtures")


def test_a_spec_with_no_field_map_gets_arxivs_names():
    """The whole byte-identity argument rests on this."""
    assert field_map({}) == DEFAULTS
    assert field_map({}) == {"id": "id", "title": "title", "body": "abstract",
                             "categories": "categories",
                             "date": "update_date"}


def test_a_spec_with_no_cutoff_gets_arxivs_cutoff():
    assert drift_cutoff({}) == DEFAULT_DRIFT_CUTOFF == "2019-01-01"


def test_a_declared_map_overrides_only_what_it_names():
    fm = field_map({"source": {"field_map": {"date": "creation_date"}}})
    assert fm["date"] == "creation_date"
    assert fm["body"] == "abstract"        # untouched keys keep the default


def test_a_typo_in_the_field_map_is_refused_not_ignored():
    """Silently falling back to `update_date` would characterize the drift
    pair on a field the corpus does not have."""
    with pytest.raises(FieldMapError) as e:
        field_map({"source": {"field_map": {"dates": "creation_date"}}})
    assert "dates" in str(e.value)


def test_no_format_dispatches_to_the_arxiv_reader():
    assert READERS["arxiv_jsonl"] is arxiv_reader.sample_records
    assert READERS["stackexchange_parquet"] is se_reader.sample_records


def test_an_unknown_format_names_the_ones_that_exist():
    with pytest.raises(ValueError) as e:
        sample_for_spec("x", {"source": {"format": "csv"}}, 1, 1)
    assert "csv" in str(e.value) and "arxiv_jsonl" in str(e.value)


# ------------------------------------------------------- the shipped specs
def _spec(name):
    with open(os.path.join(FIXTURES, f"{name}.fixture.yaml"),
              encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize("name", ["arxiv-150k", "arxiv-smoke",
                                  "stackexchange-150k"])
def test_every_shipped_spec_resolves_a_complete_field_map(name):
    fm = field_map(_spec(name))
    assert set(fm) == {"id", "title", "body", "categories", "date"}
    assert all(fm.values())


@pytest.mark.parametrize("name", ["arxiv-150k", "arxiv-smoke"])
def test_the_arxiv_specs_declare_exactly_the_builders_old_defaults(name):
    """Declaring the map is documentation, not a change. If either of these
    ever differs from DEFAULTS, arxiv-150k's published values are no longer
    reproducible by the path that produced them."""
    assert field_map(_spec(name)) == DEFAULTS
    assert drift_cutoff(_spec(name)) == DEFAULT_DRIFT_CUTOFF


def test_the_stackexchange_spec_maps_onto_the_fields_its_reader_produces():
    spec = _spec("stackexchange-150k")
    fm = field_map(spec)
    assert fm == {"id": "id", "title": "title", "body": "body",
                  "categories": "categories", "date": "creation_date"}
    assert drift_cutoff(spec) == "2017-01-01"
    assert spec["source"]["format"] == "stackexchange_parquet"
    # The text template can only be formatted from keys the reader emits.
    tmpl = spec["sampling"]["text_template"]
    produced = {"id", "title", "body", "categories", "creation_date",
                "content_license"}
    import string
    named = {f for _, f, _, _ in string.Formatter().parse(tmpl) if f}
    assert named <= produced, f"template names {named - produced}"


# ------------------------------------------- the call site, not the helpers
# The helpers above prove `field_map({})` returns arXiv's names. That is not
# quite the contract task 016 has to keep: what must not move is the output of
# `fixture.build.characterize`, which is where the map is actually read. The
# full byte-identity gate rebuilds arxiv-smoke end to end, which needs the
# embedding model; this pins the same invariant at the layer 016 changed,
# without one.
def _tiny_corpus(dim=32, seed=20260911):
    """Synthetic unit vectors, with records in three date tiers.

    Three tiers rather than two so a cutoff can be moved between them and
    still leave both halves of the drift pair non-empty -- an empty half is
    not a different measurement, it is a division by zero. The oldest tier has
    500 records so the drift pair's k-means has more points than centroids
    even when the cutoff is pulled back to 2017.
    """
    import numpy as np
    tiers = [("2015-01-01", 500), ("2018-01-01", 400), ("2021-01-01", 300)]
    rng = np.random.default_rng(seed)
    n_base = sum(n for _, n in tiers)
    base = rng.normal(size=(n_base, dim)).astype(np.float32)
    base /= np.linalg.norm(base, axis=1, keepdims=True)
    base_recs = [{"update_date": d} for d, n in tiers for _ in range(n)]
    # 20 queries per tier, taken from that tier's rows.
    q_idx, off = [], 0
    for _, n in tiers:
        q_idx.extend(range(off, off + 20))
        off += n
    queries = base[q_idx].copy()
    q_recs = [base_recs[i] for i in q_idx]
    return base, queries, base_recs, q_recs


def test_declaring_arxivs_own_field_map_changes_no_measure_synthetic():
    """A spec that declares arXiv's names and cutoff must characterize
    identically to one that declares neither. If this ever fails, every
    published arxiv-150k value is in question, not just this test."""
    import numpy as np

    from ..fixture.build import characterize
    from ..truth import exact_knn

    base, queries, base_recs, q_recs = _tiny_corpus()
    gt = exact_knn(base, queries, 10)

    bare = {"sampling": {"seed": 20260911}}
    declared = {
        "sampling": {"seed": 20260911, "drift_cutoff": DEFAULT_DRIFT_CUTOFF},
        "source": {"field_map": dict(DEFAULTS)},
    }

    out_bare, cents_bare = characterize(base, queries, base_recs, q_recs, gt,
                                        bare)
    out_decl, cents_decl = characterize(base, queries, base_recs, q_recs, gt,
                                        declared)

    assert out_bare == out_decl, "the field map is not a no-op for arXiv"
    assert np.array_equal(cents_bare, cents_decl)


def test_a_declared_cutoff_actually_moves_the_drift_split_synthetic():
    """The negative control for the test above: if `drift_cutoff` were ignored
    rather than read, the previous test would pass for the wrong reason.

    2017 puts the 2018 tier on the `after` side, where 2019 leaves it on the
    `before` side, so the pair must move while every measure computed above
    the drift block stays put.
    """
    from ..fixture.build import characterize
    from ..truth import exact_knn

    base, queries, base_recs, q_recs = _tiny_corpus()
    gt = exact_knn(base, queries, 10)

    bare = {"sampling": {"seed": 20260911}}
    moved = {"sampling": {"seed": 20260911, "drift_cutoff": "2017-01-01"}}

    out_bare, _ = characterize(base, queries, base_recs, q_recs, gt, bare)
    out_moved, _ = characterize(base, queries, base_recs, q_recs, gt, moved)

    for k in ("intrinsic_dimensionality", "boundary_crispness",
              "ambiguous_query_rate", "skew_top10_share"):
        assert out_bare[k] == out_moved[k], k
    drift_keys = [k for k in out_bare if k.startswith("drift")]
    assert drift_keys, "characterize() reported no drift measure at all"
    assert any(out_bare[k] != out_moved[k] for k in drift_keys), \
        "drift_cutoff was ignored"
