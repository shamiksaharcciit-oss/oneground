# For `docs/PRACTICE.md` — a number on a page has a receipt in the data that
page ships

*Not ours. This is the lab team's rule, arrived at independently, and it is
recorded here because it refused one of our proposals and was right to. Passed
on at the developer's instruction, for the interface stream to place. It has
cost them something — they can say what — and it converges with a rule this
project already enforces from the opposite direction.*

## The rule, in their words

> **A number on the page has a receipt in the data the page ships.**

## How we met it

Task 044c measured that `boundary_crispness` is U-shaped in the centroid
count, and that the teaser's published 0.036 therefore is not arXiv's
crispness but arXiv's crispness at 256 regions. We proposed adding a clause to
the ε = 0.00 caption naming the count, and a second sentence making the
dependence concrete:

> *"Both numbers are part of the reading: cut the same corpus into 2,048
> regions instead and the crisp fraction is 0.053 rather than 0.036."*

Core **took the finding and the caption clause, and refused the 0.053** — on
the grounds that a typed `0.053` would be the first number on that page the
page cannot check. Everything else there resolves to `data/`, digested in
`data/MANIFEST.sha256` and re-verified by their own script.

**The refusal is the caption's own argument turned on the caption.** The whole
purpose of that sentence is to stop a figure travelling without the thing it
depends on. A hand-typed second figure travels with nothing at all — it is the
defect it was written to fix, one layer up, on the page that exists to show
receipts.

They refused it **by naming the remedy rather than by trimming the sentence**:
export the sweep into the page's data, and the caption reads the number
instead of stating it. That is the half worth copying. A refusal that deletes
the claim loses the finding; a refusal that names what would license the claim
keeps it and prices it.

## Why it belongs on this page rather than only in theirs

**It is the rendering contract arriving from the other side.**
`docs/STATE.md` §"The rendering contract" already binds our end:

> **Tally, never measure.** A view may select, gather by stored id, compare,
> count, sum, and take fractions and percentiles of **stored columns**. It may
> not compute anything that needs a vector.

Ours constrains the **renderer**: it may not compute a number, only tally one
that is already in the state. Theirs constrains the **page**: it may not state
a number that is not in the data it ships. Same constraint on where a figure
comes from, discovered twice, from two directions, by two teams — which is
about as much evidence as a rule of this kind ever gets.

Recording both together is worth more than either alone, because the pair
shows what the rule is actually about. It is not about purity or about
testability. **It is about a number being answerable to something after the
person who wrote it has gone.** A computed number in a view and a typed number
in a caption fail identically: there is nothing a later reader can check them
against, and nothing that goes red when they drift.

## The tell

**You are about to write a number into prose, and you know it because you
measured it.** That is precisely the condition under which it feels safe and
is not: you have the measurement, so the figure is right today, and the page
acquires a fact with no path back to the thing that made it true.

Ask what a reader could check it against, and then whether they could do it
from what the page ships. If the answer is "the report in the repository", the
number is right and the page is still the wrong place for it until the data
follows.

## What it cost them

Theirs to state. From our side the price was one refused sentence and a task
to export the data properly (044e) — which is the cheap end, because the
refusal came before publication rather than after.

*If the page's constraint is read strictly as "nothing goes in it that has not
cost this project something", note that the cost here was paid by the lab team
rather than by us, and the entry should say so as it does above. The developer
routed it here deliberately; the placement is still the interface stream's
call.*
