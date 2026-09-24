# Finding — the field table and the example file describe different things

*Task 046, step 2. The brief says: generate `requirements.example.yaml` and
`requirements.declared.example.yaml` from the table, or delete them. Measured,
neither is available, and the reason is worth more than the instruction.*

## Measured

| | leaf fields | in the table | not in the table |
|---|---|---|---|
| `requirements.example.yaml` | 74 | 16 | **58** |
| `requirements.declared.example.yaml` | 31 | 10 | **21** |

The table declares **21** fields. The example file documents **74**.

## Why neither option is available

**Generating** would shrink the file the README calls *the schema by example*
— and `intake`'s own module docstring calls it the same — from 74 fields to
16. The `constraints`, `simulate` and `cost` blocks would vanish from the
document a user is told to copy.

**Deleting** removes what `README.md`, `docs/INTAKE.md`, `oneground/cli.py`
and `intake`'s docstring all point at, including a command in `INTAKE.md`
that runs against it by name.

The brief's premise is that the two describe the same fields and one is
hand-maintained. They do not:

- **the table** is what `intake` *validates* — 21 fields, 25 refusals;
- **the example** is the *schema* — 74 fields, most of which nothing
  validates and the form does not offer.

Both are correct about their own subject. They were never two copies of one
thing, so there is no duplication to remove, and the 56 hand-written comment
lines the brief counts are explaining fields the table has never heard of.

## The finding underneath, which is the larger one

**58 of the 74 fields a requirements file can carry are validated by
nothing.** A user can write `constraints.latency.p95_ms: fourty` or
`cost.error_band: "a lot"` and `intake.load()` will accept the file without a
word. They are read later, by whatever consumes them, or not at all.

That is not a defect this slice introduced or should fix — but it is the
reason two of its acceptance lines cannot be met as written, and it should be
known before either is called done:

- *"Every field a requirements file can carry is offered by the form"* — **21
  of 74**. The form offers what the table declares, and the table declares
  what `intake` validates.
- *"the example files are generated or gone"* — neither, for the reasons
  above.

## What I would do, not taken

Three options, in increasing order of what they cost and buy:

1. **Say so.** `docs/UI.md`'s write half already states that the form offers
   what the table declares; add the number, so *the form does not offer
   everything* is a measured fact rather than an impression. Cheap, honest,
   changes nothing.
2. **Extend the table to the whole schema**, leaving `belongs_to` and
   `REQUIRED` empty for fields nothing validates. The form would then offer
   all 74 and the example files *could* be generated. It also puts 58 fields
   in a table whose stated purpose is that explanation and refusal come from
   one declaration — and for those 58 there is no refusal to share a
   declaration with, which weakens the table's own claim.
3. **Validate them**, which is a change to `intake` and the seventh contract
   item this slice has wanted.

My reading is that (1) is right for this slice and (3) is the real answer
eventually, because a field nothing validates is a field a user can get wrong
silently — which is the defect this project exists to refuse, sitting in the
file that starts every run.

(2) is the tempting one and I think it is wrong: it would make the form look
complete by putting fields in a declaration that cannot honour the
declaration's contract, and the example files would then be generated from a
table that is half real.
