"""Cost, with an error band on every number.

`nodes x node_price x hours_per_month`, where the node count comes from the
simulator's estimated memory and the prices come from a **provided table** the
user can read and edit. There is no pricing API call here and there will not
be one in this build: a cost you cannot re-derive from a file is a cost you
cannot check.

Why every figure carries a band
-------------------------------
The inputs are an *estimate* (`est_memory_bytes` is vector payload plus an
HNSW graph term, not observed RSS), a *declared* price table with an `as_of`
date, and a headroom policy chosen by the user. A single number built from
three soft inputs would be the most confident-looking and least defensible
thing in the report.

So a cost is `EUR X +/- Y`, the band comes from `verify.cost.error_band`
(default 0.25), and **budget verdicts use the upper bound**. Under-running a
budget is a pleasant surprise; over-running one is the failure the constraint
exists to prevent, so the arithmetic leans that way on purpose.

What is not in a price
----------------------
Compute only. Storage, egress, load balancers, backups, and the people who run
it are outside the table and outside every number this module produces, and
`prices.example.yaml` says so in its own header. Nothing here is a quote.
"""

import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

HOURS_PER_MONTH = 730          # 365 * 24 / 12, the convention vendors bill on
DEFAULT_ERROR_BAND = 0.25

# Fraction of a node's RAM the index may occupy before another node is needed.
# Not a tuning parameter: an engine that fills its host has no room for the
# query working set, the OS, or a rebuild.
DEFAULT_HEADROOM = 0.70

PRICES_EXAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "prices.example.yaml")


class CostError(ValueError):
    """The price table is missing or unusable. The message names the file."""


@dataclass
class PriceTable:
    """A declared table of node types and hourly prices."""

    as_of: str
    currency: str
    nodes: List[Dict[str, Any]]
    source: str = ""
    note: str = ""
    path: str = ""
    kind: str = "declared"

    def as_dict(self):
        return {"as_of": self.as_of, "currency": self.currency,
                "source": self.source, "note": self.note,
                "path": self.path, "kind": self.kind,
                "node_types": len(self.nodes)}

    def smallest_fitting(self, memory_gb, headroom=DEFAULT_HEADROOM):
        """The cheapest node whose usable memory holds `memory_gb`.

        Usable memory is `memory_gb * headroom`. Returns None when nothing in
        the table is big enough -- the caller reports couldn't-check rather
        than inventing a machine that is not on the list.
        """
        fits = [n for n in self.nodes
                if float(n["memory_gb"]) * headroom >= memory_gb]
        if not fits:
            return None
        return min(fits, key=lambda n: float(n["eur_per_hour"]))


def load_prices(path=None):
    """Read a price table. Defaults to the shipped example."""
    p = path or PRICES_EXAMPLE
    if not os.path.exists(p):
        raise CostError(
            f"price table not found: {p}. oneground does not fetch prices; "
            "point verify.cost.prices at a table you can read, or use the "
            f"shipped example at {PRICES_EXAMPLE}")
    with open(p, encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    nodes = d.get("nodes") or []
    if not nodes:
        raise CostError(f"{p}: no `nodes` in the price table")
    for n in nodes:
        for key in ("id", "memory_gb", "eur_per_hour"):
            if key not in n:
                raise CostError(f"{p}: node {n.get('id', '?')} has no {key}")
    return PriceTable(as_of=str(d.get("as_of", "unknown")),
                      currency=str(d.get("currency", "EUR")),
                      nodes=nodes, source=str(d.get("source", "")),
                      note=str(d.get("note", "")), path=os.path.abspath(p))


@dataclass
class Cost:
    """One option's monthly cost, with its band and its whole derivation."""

    nodes: int
    node_id: str
    node_memory_gb: float
    eur_per_hour: float
    monthly: float
    error_band: float
    currency: str = "EUR"
    headroom: float = DEFAULT_HEADROOM
    index_memory_gb: float = 0.0
    basis: str = ""
    kind: str = "estimate (declared prices, estimated sizing)"

    @property
    def low(self):
        return self.monthly * (1 - self.error_band)

    @property
    def high(self):
        return self.monthly * (1 + self.error_band)

    def render(self):
        """`EUR 420 +/- 105` -- the form the report prints."""
        pm = self.monthly * self.error_band
        return f"{self.currency} {self.monthly:,.0f} +/- {pm:,.0f}"

    def as_dict(self):
        return {
            "monthly": round(self.monthly, 2),
            "monthly_low": round(self.low, 2),
            "monthly_high": round(self.high, 2),
            "error_band": self.error_band,
            "currency": self.currency,
            "rendered": self.render(),
            "nodes": self.nodes,
            "node_id": self.node_id,
            "node_memory_gb": self.node_memory_gb,
            "eur_per_hour": self.eur_per_hour,
            "hours_per_month": HOURS_PER_MONTH,
            "headroom": self.headroom,
            "index_memory_gb": round(self.index_memory_gb, 4),
            "basis": self.basis,
            "kind": self.kind,
            "note": ("compute only: no storage, egress, load balancers, "
                     "backups or operators. Budget verdicts use monthly_high."),
        }


def size_and_cost(sim_row, prices, error_band=DEFAULT_ERROR_BAND,
                  headroom=DEFAULT_HEADROOM, memory_budget_gb=None):
    """Cost one option. Returns (Cost, None) or (None, reason).

    Sizing: the simulator's `est_memory_bytes` is the index's resident
    footprint including replication, so the node count is

        ceil(index_memory_gb / (node_memory_gb * headroom))

    `memory_budget_gb`, when the user gave one, caps the *per-node* size
    considered -- a user who says 64 GB is telling you what machines they are
    willing to run, not just a total.
    """
    mem = sim_row.get("est_memory_bytes")
    if mem is None:
        return None, ("the sweep row has no est_memory_bytes, so the option "
                      "cannot be sized")
    index_gb = float(mem) / 1e9

    candidates = prices.nodes
    if memory_budget_gb:
        capped = [n for n in candidates
                  if float(n["memory_gb"]) <= float(memory_budget_gb)]
        if capped:
            candidates = capped

    # The cheapest node type that minimises total monthly cost, given that a
    # bigger node may need fewer of them.
    best = None
    for n in candidates:
        usable = float(n["memory_gb"]) * headroom
        if usable <= 0:
            continue
        count = max(1, math.ceil(index_gb / usable))
        monthly = count * float(n["eur_per_hour"]) * HOURS_PER_MONTH
        if best is None or monthly < best[0]:
            best = (monthly, count, n)

    if best is None:
        return None, (f"no node in {prices.path} can hold "
                      f"{index_gb:.2f} GB at {headroom:.0%} headroom")

    monthly, count, node = best
    return Cost(
        nodes=count, node_id=str(node["id"]),
        node_memory_gb=float(node["memory_gb"]),
        eur_per_hour=float(node["eur_per_hour"]),
        monthly=monthly, error_band=float(error_band),
        currency=prices.currency, headroom=headroom,
        index_memory_gb=index_gb,
        basis=(f"{count} x {node['id']} at {node['eur_per_hour']} "
               f"{prices.currency}/hour x {HOURS_PER_MONTH} h/month; sized "
               f"from est_memory_bytes {index_gb:.2f} GB at {headroom:.0%} "
               f"headroom; prices declared, as_of {prices.as_of}")), None


def cost_for_options(sim_rows, cost_cfg=None, constraints=None):
    """Cost every option. Returns {config_label: cost_dict_or_reason}."""
    cfg = dict(cost_cfg or {})
    if cfg.get("enabled") is False:
        return {}, None
    try:
        prices = load_prices(cfg.get("prices"))
    except CostError as e:
        return {}, str(e)

    band = float(cfg.get("error_band", DEFAULT_ERROR_BAND))
    headroom = float(cfg.get("headroom", DEFAULT_HEADROOM))
    budget_gb = (constraints or {}).get("memory_budget_gb")

    out = {}
    for row in sim_rows:
        cost, why = size_and_cost(row, prices, band, headroom, budget_gb)
        out[row.get("config", "?")] = (cost.as_dict() if cost
                                       else {"couldnt_check": why})
    return out, prices
