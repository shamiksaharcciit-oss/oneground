"""The lab's views, each a `View` over the contract in `../contract.py`.

Every module in this package is read by `../guard.py`, registered or not: a
module sitting here is a view module, and a view module may not measure.
"""

from .ground import GroundView
from .query_index import QueryIndexView
from .query_trace import QueryTraceView

VIEWS = {GroundView.name: GroundView, QueryTraceView.name: QueryTraceView,
         QueryIndexView.name: QueryIndexView}

__all__ = ["GroundView", "QueryIndexView", "QueryTraceView", "VIEWS"]
