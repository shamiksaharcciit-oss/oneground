"""The receipt half of the rendering contract (task 041).

The state half is tested in `test_lab.py`. These are the rules that are new
because a receipt is not a state: one receipt per view, declared paths in the
report's own citation grammar, an absent field that is a gap rather than a
None, and a list walked by declaration rather than by index.
"""
import json
import os

import pytest

from oneground.lab import guard, receipt as R
from oneground.lab.contract import COULDNT_CHECK, ContractError, Drawing, Mark

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SIMULATE = {
    "run": "r", "schema": 1, "n_base": 150000, "n_queries": 2000,
    "rows": [
        {"config": "single_node_hnsw[M=32,efSearch=128]",
         "family": "single_node_hnsw", "recall_at_10": 0.9968,
         "query_seconds": 1.6},
        {"config": "semantic_sharded[epsilon=0.2,probe=2]",
         "family": "semantic_sharded", "recall_at_10": 0.9318},
    ],
}


class _Table(R.ReceiptView):
    name = "simulate_table"
    receipt = "simulate.json"
    reads = ("n_base", "rows[].config", "rows[].recall_at_10")

    def render(self, f):
        labels, recalls = [], []
        for row in f.each("rows"):
            labels.append(row["config"])
            recalls.append(row["recall_at_10"])
        return Drawing(
            view=self.name,
            marks=[Mark(kind="row", data={"config": labels,
                                          "recall_at_10": recalls},
                        encoding={"y": "recall_at_10"})],
            figures={"n_base": f["n_base"]})


# ------------------------------------------------------------ declared fields
def test_a_view_reads_only_what_it_declared():
    class Sneaky(_Table):
        def render(self, f):
            f["rows[].query_seconds"]                 # never declared
            return Drawing(view=self.name, marks=[], figures={})

    with pytest.raises(R.UndeclaredField) as e:
        R.draw_receipt(Sneaky(), SIMULATE)
    assert "query_seconds" in str(e.value)


def test_a_row_reader_is_bounded_by_the_same_declaration():
    """The bound follows into `each`: declaring rows[].config does not open
    the whole row."""
    class Sneaky(_Table):
        def render(self, f):
            for row in f.each("rows"):
                row["family"]                          # declared on no view
            return Drawing(view=self.name, marks=[], figures={})

    with pytest.raises(R.UndeclaredField):
        R.draw_receipt(Sneaky(), SIMULATE)


def test_walking_a_list_nobody_declared_says_how_to_declare_it():
    class NoLeaves(R.ReceiptView):
        name = "x"
        receipt = "simulate.json"
        reads = ("n_base",)

        def render(self, f):
            list(f.each("rows"))
            return Drawing(view=self.name, marks=[], figures={})

    with pytest.raises(R.UndeclaredField) as e:
        R.draw_receipt(NoLeaves(), SIMULATE)
    assert "rows[].<field>" in str(e.value)


# --------------------------------------------------------------- absent fields
def test_an_absent_field_raises_rather_than_rendering_none():
    """A receipt written before a field existed simply lacks it. Rendering
    that as None would state a measurement nobody made."""
    class Older(R.ReceiptView):
        name = "x"
        receipt = "simulate.json"
        reads = ("ceiling_at_10",)

        def render(self, f):
            return Drawing(view=self.name, marks=[],
                           figures={"c": f["ceiling_at_10"]})

    with pytest.raises(R.AbsentField) as e:
        R.draw_receipt(Older(), SIMULATE)
    assert "check `has` first" in str(e.value)


def test_has_asks_without_raising_and_a_gap_is_the_honest_answer():
    class Older(R.ReceiptView):
        name = "x"
        receipt = "simulate.json"
        reads = ("ceiling_at_10",)

        def render(self, f):
            if f.has("ceiling_at_10"):
                return Drawing(view=self.name, marks=[],
                               figures={"c": f["ceiling_at_10"]})
            return Drawing(view=self.name, marks=[], figures={},
                           gaps={"c": R.gap("this run predates ceiling_at_10")})

    d = R.draw_receipt(Older(), SIMULATE)
    assert d.figures == {}
    assert d.gaps["c"].startswith(COULDNT_CHECK)
    assert d.reads == [], "a field that was absent was not read"


def test_a_gap_that_is_not_a_couldnt_check_reason_is_refused():
    """Inherited from the state half, and it has to keep holding here."""
    class Sloppy(R.ReceiptView):
        name = "x"
        receipt = "simulate.json"
        reads = ("n_base",)

        def render(self, f):
            return Drawing(view=self.name, marks=[], figures={},
                           gaps={"c": "no data"})

    with pytest.raises(ContractError):
        R.draw_receipt(Sloppy(), SIMULATE)


# ------------------------------------------------------------------ provenance
def test_the_drawing_records_the_paths_it_read_in_the_grammar_it_declared():
    d = R.draw_receipt(_Table(), SIMULATE)
    assert d.reads == ["n_base", "rows[].config", "rows[].recall_at_10"]
    assert d.source == {"receipt": "simulate.json", "run": "r", "schema": 1}
    assert d.epsilon == R.NOT_EPSILON


def test_a_list_read_once_per_row_is_recorded_once():
    """Two rows, one path. Provenance is what was read, not how often."""
    d = R.draw_receipt(_Table(), SIMULATE)
    assert d.reads.count("rows[].config") == 1


def test_a_view_may_not_name_a_file_that_is_not_a_receipt():
    class Elsewhere(_Table):
        receipt = "simulate_info.json"

    with pytest.raises(R.UnknownReceipt) as e:
        R.draw_receipt(Elsewhere(), SIMULATE)
    assert "simulate_info.json" in str(e.value)


# --------------------------------------------------------------- the grammar
@pytest.mark.parametrize("path,expected", [
    ("a.b.c", ["a", "b", "c"]),
    ("rows[]", ["rows[]"]),
    ("rows[].config", ["rows[]", "config"]),
    # the case a naive split on "." gets wrong: the label owns dots AND
    # brackets, and it is the form report.json cites with.
    ("rows[semantic_sharded[M=32,epsilon=0.2]].recall_at_10",
     ["rows[semantic_sharded[M=32,epsilon=0.2]]", "recall_at_10"]),
    ("costs[hash_sharded[M=32,shards=3]].monthly_high",
     ["costs[hash_sharded[M=32,shards=3]]", "monthly_high"]),
])
def test_the_path_grammar_is_the_one_report_json_cites_with(path, expected):
    assert R.split_path(path) == expected


@pytest.mark.parametrize("bad", ["rows[", "rows]", "a.b[c"])
def test_an_unbalanced_path_is_refused(bad):
    with pytest.raises(ContractError):
        R.split_path(bad)


def test_a_member_is_found_by_its_label_not_its_index():
    class One(R.ReceiptView):
        name = "x"
        receipt = "simulate.json"
        reads = ("rows[semantic_sharded[epsilon=0.2,probe=2]].recall_at_10",)

        def render(self, f):
            p = "rows[semantic_sharded[epsilon=0.2,probe=2]].recall_at_10"
            return Drawing(view=self.name, marks=[], figures={"r": f[p]})

    d = R.draw_receipt(One(), SIMULATE)
    assert d.figures["r"] == 0.9318


# ------------------------------------------------------------------ the guard
def test_the_receipt_contract_is_classified_and_guarded():
    """041 named a third kind rather than pretending there were two. The
    point is that no module can arrive in this package unclassified."""
    assert "receipt.py" in guard.CONTRACT_MODULES
    assert guard.unclassified_modules() == []
    assert guard.check_contract() == {}


def test_the_contract_reads_no_files():
    """`draw_receipt` takes parsed JSON, so a view cannot be handed a path
    and reach for something beside it."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "receipt.py"), encoding="utf-8").read()
    v = guard.transport_violations(src, "receipt.py", allow_numpy=True)
    assert [x for x in v if x[1] == "import"] == []
    assert "open(" not in src, "the contract does not read files"


# --------------------------------------------------- against a real receipt
def _real(name):
    p = os.path.join(REPO, "runs", "arxiv-150k-via-characterize", name)
    if not os.path.exists(p):
        pytest.skip(f"no local {name}; run `oneground report "
                    f"requirements.arxiv-150k.yaml`")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def test_the_table_draws_the_real_simulate_receipt():
    d = R.draw_receipt(_Table(), _real("simulate.json"))
    assert d.marks[0].data["config"], "no rows drawn"
    assert len(d.marks[0].data["config"]) == len(d.marks[0].data["recall_at_10"])
    assert all(0.0 <= r <= 1.0 for r in d.marks[0].data["recall_at_10"])
    assert d.source["receipt"] == "simulate.json"
