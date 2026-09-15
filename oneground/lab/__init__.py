"""The lab's rendering contract (task 021).

The lab (v0.2) draws what an architecture did -- the ground, a query's trace
-- from simulator state. This package is the contract every one of its views
is held to:

    a view takes state and returns a drawing

* **`render(state) -> Drawing`, and nothing else.** A view is a pure function
  of the state it is handed: no files, no network, no clock.
* **It declares the state columns it reads** (`reads`), and the state it is
  handed exposes those columns and no others.
* **It may tally state.** Select, gather by stored id, compare, count, sum, and
  take a fraction or a percentile of stored columns: that is what drawing a
  measurement is.
* **It may not measure.** Nothing that needs a vector: no distance, similarity,
  norm, projection, clustering or neighbour search. `characterize` and
  `simulate` measured those, and the state carries what they found. A view
  that re-derived one would be a second measurement that can disagree with the
  first, and nothing on the screen would say which one the table was built
  from.

Two things enforce the last rule, because a rule nobody checks is a comment:

* **The state refuses vector columns.** The state a view is handed
  (`contract.StateColumns`) refuses vector-valued columns at run time, so
  there is no vector in reach to do arithmetic on.
* **The guard reads every view module's source.** `guard.py` fails the test
  suite on vector arithmetic, on importing anything that measures, on reading
  a file, and on dynamic code that could get around those checks.

`contract.py` holds the types, the one entry point (`draw`) and `ON_EPSILON`:
what a change of epsilon does to every state column, and so to every drawing.
`views/` holds the views. `corpora/render_from_state.py` composes them into
the teaser's two figures.
"""

from .contract import (COULDNT_CHECK, NOT_SIMULATED, ON_EPSILON, RECOUNT,
                       REBUILD, SIMULATED, UNCHANGED, VECTOR_COLUMNS,
                       ContractError, Drawing, Mark, StateColumns,
                       UndeclaredColumn, VectorColumn, View, draw, load_state,
                       on_epsilon, same_epsilon)

__all__ = ["COULDNT_CHECK", "NOT_SIMULATED", "ON_EPSILON", "RECOUNT",
           "REBUILD", "SIMULATED", "UNCHANGED", "VECTOR_COLUMNS",
           "ContractError", "Drawing", "Mark", "StateColumns",
           "UndeclaredColumn", "VectorColumn", "View", "draw", "load_state",
           "on_epsilon", "same_epsilon"]
