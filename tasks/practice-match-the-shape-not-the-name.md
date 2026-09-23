# For `docs/PRACTICE.md` — a transform keyed on a field's name

*From task 044i, for the interface stream to place. It is the same family as
§4, *A key whose meaning differs by file*, **arriving from the other
direction**: §4 is about writing a name that means something else somewhere
else; this is about reading a name as if it guaranteed something about the
value. Whether it belongs beside §4 or in §2 is yours. What it cost is at the
bottom.*

## The rule

> **A transform should match the shape it fixes, not the name it is filed
> under.** A sanitiser keyed on a field's name transforms whatever is *called*
> that, not whatever *is* that.

## Why the usual instinct fails

Keying on a name feels like the careful choice. It is narrow, it is
declarative, it reads well — `PATH_KEYS = ("source", "path")` — and it is
obviously better than transforming everything. The failure is that a field
name is a **convention**, and a transform is a **function**: the name says
what someone meant to put there, and the function runs on what is actually
there.

The two agree almost always, which is what makes the exception expensive. The
transform is applied hundreds of times correctly, and the one field where the
convention slipped is damaged silently, by code written to protect it.

## The instance

Task 044e added `public_sources`, a walker that made path fields fit to
publish. It applied `receipts.public_path` to every key named `source` or
`path`.

`verdict.price_table.source` is not a path. It is a sentence:

    "Public list prices, EU regions, typed from vendor pages on the as_of
     date. On-demand, no committed-use discount, no support plan, no egress."

`public_path` resolved it as a path relative to the repository root — which
succeeds, because any string is a valid relative path — and `relpath`
normalised it. **`normpath` removed the trailing full stop**, because `.` is a
path component meaning *this directory*.

So a published page lost a full stop, to a repair for machine-local paths,
in a field that never held one. Nobody would have found it by reading the
transform; the transform is correct. It was found by the other team diffing
two published files and asking why a sentence had changed.

## The repair, which is the rule

Key on the shape:

```python
def _needs_sanitising(key, value):
    return (key in PATH_KEYS and isinstance(value, str) and value
            and bool(LOCAL_PATH.search(value)))
```

`LOCAL_PATH` is the pattern the **refusal** uses to reject a publishable
value. Tying the transform to it makes the two agree by construction:
*exactly what would otherwise be refused is transformed, and nothing else
can be.* A value the refusal would accept is left alone whatever it is
called.

That is the general form. Where a transform exists to fix a shape, and
something else already recognises that shape, they should be the same
predicate — not because it is tidier but because **two predicates for one
shape is two places for the answer to differ**, and the difference shows up
as a silent edit rather than an error.

## The tell

**You are about to write a rule of the form "fields called X are Y".** Ask
what happens to a field called X that is not Y. If the answer is "it gets
fixed", ask what "fixed" does to it. Here it deleted a character from a
published page.

The name-keyed form is not always wrong — sometimes the name is all you have.
When it is, the transform should be one that cannot damage a non-match, which
`public_path` is not: it rewrites anything it is given.

## What it cost

One full stop on a published page, and the other team's time to find it —
they diffed two exports, noticed a sentence had changed, and asked whether our
path check had done it. It had. The cost that matters is not the character: it
is that **a check installed to protect published data was quietly editing it**,
and the only reason anyone knows is that someone was comparing bytes for an
unrelated reason.
