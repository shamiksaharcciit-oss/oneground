# Reconciliation — what 043 changed about the carriers finding

*For the interface stream, who own
`tasks/finding-comparability-carriers.md`. **Not edited by 043**: it was
written before the fix existed, as a finding about a function neither task
owned, and a write-up that predates its fix should end by saying what closed
it rather than being silently updated. This note is what 043 changed, so you
can reconcile it yourselves.*

## What your audit found, and what it was right about

Everything. All four items reproduced exactly as written:

- **The wrong value.** `facts_of` read `run_environment` — the machine that
  wrote the report — where it needed `environment`, the machine that
  measured. On the published arXiv fixture it returned
  `environment_id: local:windows-amd64` and `pod: None` in the same dict as
  `platform: Linux-6.8.0-117-generic`. One facts dict describing a Linux pod
  and a Windows laptop as one run.
- **Why it mattered most.** `pod` is the sole path by which `machine` can be
  known for a remote run, so 043 as briefed would have fixed the local case
  and left the remote one silently broken. That framing is yours and it is in
  043's report as yours.
- **The two latent ones.** `libraries` and `python_version` read from the info
  files only, though `report.json:run_environment` carries both.
- **The design consequence.** Declare the carriers as data; iterate the
  declaration; test against the declaration rather than a restatement.

## What 043 did

All four closed.

`oneground/comparability.py` now declares `FACT_CARRIERS`: fact name → ordered
list of `(file, dotted key path)`, with `*info` expanding to every receipt in
order. `facts_of` iterates it and nothing reads a receipt any other way. The
measuring machine precedes the reporting one for both `environment_id` and
`installation`.

The published fixture now reads `pod: 1ombs4scr257a5` beside
`platform: Linux-6.8.0…` — one machine.

`oneground/test_comparability_reader.py` is parametrised **from
`FACT_CARRIERS`**, as you specified, so a carrier added is tested without
anyone remembering and a carrier the reader claims but does not honour names
itself. It carries a mirror test so it cannot pass against a reader returning
constants, and a test asserting the measuring-machine precedence **as an
ordering in the declaration** rather than as a behaviour — a behaviour test
passes when the order changes for the wrong reason.

## Two things your write-up could not have known

**Your count was four. It is five.** While fixing the fourth I introduced
another: `run_environment` added to `characterize`'s `build_info.json`, where
`environment` already sat three lines below and where `run_environment` means
the opposite of what it means in `report.json`. Reverted. It is the strongest
evidence for your design ruling — the declaration is what would have made the
collision visible at the point of choosing the name — and it is why the rule
is being sent to `docs/PRACTICE.md`.

**The exhaustive test cannot catch the wrong-value class, and you said so.**
That is now recorded in the code: the first version of the reader test found a
*third absence* (`library_versions`) on its first run, on a fact nobody was
investigating — and it could not have found yours, because the field was
present and plausible. The declaration is what makes both checkable by one
test, which is precisely the argument you made.

## Suggested ending for your write-up

Rather than editing the finding, it could close with what closed it:

> **Closed by task 043.** All four items fixed; the carriers are declared as
> data in `comparability.FACT_CARRIERS` and the reader iterates the
> declaration. A fifth instance was found in the fixing and is recorded there.
> The rule this produced is in `docs/PRACTICE.md`.

Yours to word and yours to place.
