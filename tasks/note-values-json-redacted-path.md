# Note for core — a redacted path in `values.json`

*Found incidentally by task 044g's blast-radius scan, not by looking at the
teaser. **Not a change request and not urgent.** To be routed with 044e's
`measured.k_sweep` export, which touches this file anyway; this is a second
reason to touch it, not a reason to touch it sooner.*

`site/teaser/data/values.json` carries, at
`verdict.calibration.engine_line.source`, the value
`C:\Users\<developer>\projects\oneground-012\runs\arxiv-smoke\verify.json`.
The username is already the literal `<developer>`, so **this is not a leak and
nothing needs to be taken down** — somebody saw the path and redacted it
before it shipped. The distinction worth making is that our rule is not *a
published path must be redacted*, it is that **a receipt should never have
recorded the path in the first place**: `receipts.public_path` records a file
repo-relative, or as a basename when it is outside the checkout, so there is
nothing to redact later and no judgement call at publication time about
whether a given string is sensitive. What is in `values.json` today is the
weaker form — a path that was recorded, travelled through a receipt into
published data, and was repaired by hand at the end — and the hand is the part
that does not scale, because it has to be applied every time and only has to
be forgotten once. If the field is regenerated for the k-sweep export, the
natural fix is for its source to come through `public_path` at the write site
so the published value reads `runs/arxiv-smoke/verify.json` and no redaction
is involved; if it is not regenerated, leaving it exactly as it is costs
nothing and this note is only so the reason it looks odd is on the record.
