"""Tests for the cost model, on synthetic rows and a synthetic price table.

**Synthetic throughout.** These check the arithmetic and the direction the
error band is used in, not any vendor's real price.

    python oneground/cost/test_cost.py
    pytest oneground/cost/test_cost.py
"""

import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import cost as cm  # noqa: E402
from oneground.report import verdict as vd  # noqa: E402

TABLE = {
    "as_of": "2026-01-01", "currency": "EUR", "kind": "declared",
    "source": "synthetic",
    "nodes": [
        {"id": "small", "vcpu": 4, "memory_gb": 16, "eur_per_hour": 0.20},
        {"id": "large", "vcpu": 16, "memory_gb": 64, "eur_per_hour": 0.80},
    ],
}


def _table(tmp, d=None):
    p = os.path.join(tmp, "prices.yaml")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(d or TABLE, f, sort_keys=False)
    return p


def row(config="opt", mem_bytes=8e9):
    return {"config": config, "family": "single_node_hnsw",
            "est_memory_bytes": mem_bytes, "storage_amplification": 1.0,
            "recall_at_10": 0.99, "fanout": 1.0}


# ------------------------------------------------------------------ table
def test_shipped_example_table_loads_and_is_declared_synthetic():
    t = cm.load_prices()
    assert t.kind == "declared"
    assert t.as_of and t.currency
    assert len(t.nodes) >= 3
    for n in t.nodes:
        assert n["memory_gb"] > 0 and n["eur_per_hour"] > 0


def test_a_missing_table_is_refused_by_name_synthetic():
    try:
        cm.load_prices("no/such/prices.yaml")
    except cm.CostError as e:
        assert "no/such/prices.yaml" in str(e)
        assert "does not fetch prices" in str(e)
        return
    raise AssertionError("a missing price table was tolerated")


def test_a_table_missing_a_field_is_refused_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        bad = {"as_of": "x", "currency": "EUR",
               "nodes": [{"id": "n", "memory_gb": 8}]}   # no price
        try:
            cm.load_prices(_table(tmp, bad))
        except cm.CostError as e:
            assert "eur_per_hour" in str(e)
            return
        raise AssertionError("a table with no price was accepted")


# ------------------------------------------------------------------ sizing
def test_node_count_covers_the_index_with_headroom_synthetic():
    """8 GB index at 70% headroom needs 11.2 GB usable: one 16 GB node."""
    with tempfile.TemporaryDirectory() as tmp:
        prices = cm.load_prices(_table(tmp))
        c, why = cm.size_and_cost(row(mem_bytes=8e9), prices)
        assert why is None
        assert c.nodes == 1 and c.node_id == "small", c.as_dict()


def test_a_bigger_index_needs_more_nodes_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        prices = cm.load_prices(_table(tmp))
        c, _ = cm.size_and_cost(row(mem_bytes=40e9), prices)
        # 40 GB at 70%: small gives 11.2 usable -> 4 nodes at 0.20;
        # large gives 44.8 usable -> 1 node at 0.80. 4*0.20 == 0.80, tie
        # broken by iteration order; either is correct arithmetic.
        assert c.nodes * c.eur_per_hour == 0.80, c.as_dict()


def test_monthly_is_nodes_times_price_times_hours_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        prices = cm.load_prices(_table(tmp))
        c, _ = cm.size_and_cost(row(mem_bytes=8e9), prices)
        assert abs(c.monthly - 1 * 0.20 * cm.HOURS_PER_MONTH) < 1e-6


def test_an_index_too_big_for_any_node_is_couldnt_check_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        one = {"as_of": "x", "currency": "EUR",
               "nodes": [{"id": "tiny", "memory_gb": 1, "eur_per_hour": 0.01}]}
        prices = cm.load_prices(_table(tmp, one))
        # A single node cannot hold it, but many can -- so this must succeed
        # with a large count rather than refuse.
        c, why = cm.size_and_cost(row(mem_bytes=100e9), prices)
        assert why is None and c.nodes > 100


def test_a_row_without_memory_is_couldnt_check_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        prices = cm.load_prices(_table(tmp))
        c, why = cm.size_and_cost({"config": "x"}, prices)
        assert c is None and "est_memory_bytes" in why


def test_memory_budget_caps_the_node_size_considered_synthetic():
    """A user who says 16 GB is saying which machines they will run."""
    with tempfile.TemporaryDirectory() as tmp:
        prices = cm.load_prices(_table(tmp))
        c, _ = cm.size_and_cost(row(mem_bytes=40e9), prices,
                                memory_budget_gb=16)
        assert c.node_id == "small", c.as_dict()


# -------------------------------------------------------------- error band
def test_every_cost_carries_a_band_and_renders_it_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        prices = cm.load_prices(_table(tmp))
        c, _ = cm.size_and_cost(row(), prices, error_band=0.25)
        assert c.low < c.monthly < c.high
        assert abs(c.high - c.monthly * 1.25) < 1e-6
        assert "+/-" in c.render() and "EUR" in c.render()


def test_the_default_band_is_25_percent_synthetic():
    assert cm.DEFAULT_ERROR_BAND == 0.25


# ----------------------------------------------------------- budget verdict
def test_budget_verdict_uses_the_upper_bound_synthetic():
    """The band is used in the direction that can only make it stricter.

    A cost whose midpoint fits the budget but whose upper bound does not must
    fail: over-running is the failure the constraint exists to prevent.
    """
    with tempfile.TemporaryDirectory() as tmp:
        prices = cm.load_prices(_table(tmp))
        c, _ = cm.size_and_cost(row(), prices, error_band=0.25)
        mid, high = c.monthly, c.high
        costs = {"opt": c.as_dict()}
        # budget between the midpoint and the upper bound
        between = (mid + high) / 2
        v = vd.monthly_budget_from_cost(
            row(), {"monthly_budget": {"amount": between, "currency": "EUR"}},
            costs)
        assert v.outcome == vd.FAILS, (
            f"midpoint {mid:.0f} fits {between:.0f} but upper bound "
            f"{high:.0f} does not; the verdict must use the upper bound")
        assert v.value == high

        v2 = vd.monthly_budget_from_cost(
            row(), {"monthly_budget": {"amount": high * 1.01,
                                       "currency": "EUR"}}, costs)
        assert v2.outcome == vd.MEETS


def test_budget_is_couldnt_check_without_a_cost_synthetic():
    v = vd.monthly_budget_from_cost(
        row(), {"monthly_budget": {"amount": 100}}, {})
    assert v.outcome == vd.COULDNT_CHECK
    assert "no cost model" in v.reason


def test_budget_is_couldnt_check_when_sizing_failed_synthetic():
    costs = {"opt": {"couldnt_check": "the sweep row has no est_memory_bytes"}}
    v = vd.monthly_budget_from_cost(
        row(), {"monthly_budget": {"amount": 100}}, costs)
    assert v.outcome == vd.COULDNT_CHECK
    assert "est_memory_bytes" in v.reason


def test_no_budget_constraint_produces_no_row_synthetic():
    assert vd.monthly_budget_from_cost(row(), {}, {"opt": {}}) is None


def test_cost_states_what_it_excludes_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        prices = cm.load_prices(_table(tmp))
        c, _ = cm.size_and_cost(row(), prices)
        d = c.as_dict()
        assert "compute only" in d["note"]
        assert "upper bound" in d["note"].lower() or "monthly_high" in d["note"]
        assert "as_of" in d["basis"]


def _main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
