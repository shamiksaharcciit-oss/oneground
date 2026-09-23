# Finding — the comparability reader, and which file carries which fact

*An audit of `oneground/comparability.py:facts_of`, asked for after the same
function failed twice in the same way three lines apart. It has its own file
because it belongs to neither task that touches it: task 041 built the reader
and published the first instance as a finding about the artifacts; task 043
owns the file now and has taken the ruling into its scope. This is the
measurement both of them refer to.*

**Nothing was changed. The file is in 043's path and that stream is
mid-build.**

---

## The shape being looked for

`facts_of` reads seven facts out of a run directory, and the comparability
verdict compares them. Every fact is carried by one or more files, and the
question asked was: **for each fact, does the reader consult every file that
may carry it, or the one it happens to have been given?**

The first instance was `code`. Task 033's `oneground` block is written into
`report.json` as well as the `_info.json` receipts; the reader consulted only
the latter and reported `code: unknown` for runs whose report carried the
commit. Task 041 published that as a finding about the artifacts. It was a
defect in the reader.

---

## The live defect: `report.json` carries two environment blocks

`report.json` records the environment **twice**, deliberately, because a run
has two:

```
environment.environment_id      = "1ombs4scr257a5"        the pod verify ran on
run_environment.environment_id  = "local:windows-amd64"   the laptop that wrote the report
```

`facts_of` reads `run_environment`.

Measured against the published arXiv fixture bundle — the one
`oneground ui --demo` serves:

| | |
|---|---|
| `verify_info.json` records | `environment_id: 1ombs4scr257a5` (**a pod id**) |
| `report.json:environment` records | `environment_id: 1ombs4scr257a5` |
| `report.json:run_environment` records | `environment_id: local:windows-amd64` |
| **`facts_of` returns** | **`local:windows-amd64`, `pod: None`** |

Three things make this worse than the `code` instance.

**It is not an absence; it is a wrong value.** The reader finds a fact, from a
file that carries a *different fact of the same name*. `run_environment` is
the machine that produced the report. `environment` is the machine the
measurement was taken on. Comparability is a question about the second.

**The facts it returns are internally inconsistent.** The same call returns
`platform: Linux-6.8.0-117-generic-x86_64…`, read from `verify_info.json`,
beside `environment_id: local:windows-amd64`, read from `report.json`. One
facts dictionary describing a Linux pod and a Windows laptop as one run.

**It lands on the only ingredient that can ever be earned.** `pod` is the sole
path by which the `machine` ingredient becomes known — `local:<os>-<arch>` is
a class, never an identity. A pod run read as a local class cannot reach
`comparable` however completely task 043 records its salt, because the reader
discards the identity before the verdict sees it.

---

## The seven facts, measured

Carriers established by reading every receipt in a real workdir and in the
published bundle, not by reading the function.

| fact | carried by | the reader consults | state |
|---|---|---|---|
| `code` | `report.json`, `_info.json` receipts | both | **correct** — instance 1, repaired |
| `platform` | three `_info.json` receipts | `INFO_FILES` | **correct** — no other carrier |
| `settings` | three `_info.json` receipts | `INFO_FILES` | **correct** — no other carrier |
| `sample` | `report.json:inputs` only | `report.json:inputs` | **correct** — no other carrier |
| `libraries` | three receipts, **and** `report.json:run_environment.versions` | `INFO_FILES` | **latent** — a report-only workdir loses it |
| `python_version` | three receipts, **and** `report.json:run_environment.python_version` | `INFO_FILES` | **latent** — same shape |
| `environment_id` | `verify_info.json`, `verify.json`, **two** `report.json` blocks | `report.json:run_environment` only | **live defect** |

Three correct outright, two latent, one repaired, one live.

The two latent ones are the `code` instance exactly, in a configuration this
machine does not currently hold: a workdir with a report and no `_info.json`
receipts. They are reported because the answer to "is the general form sound"
is **no** — four of seven readers are special-cased to a file set, and two of
those four happen to be right because no second carrier exists yet.

One non-finding, recorded so it is not re-investigated: `acme-existing` has a
verify stage and no report, and `facts_of` returns `environment_id: None` for
it. That is correct. Neither its `verify.json` nor its `verify_info.json`
records the field; the run predates it. The reader is not at fault there.

---

## Why an exhaustive presence test cannot reach the live one

The natural test is *"for each fact, and each file that may carry it, the
reader finds it."* It is worth writing and it would have caught instance 1
and both latent ones.

**It cannot catch the environment defect, because the fact is found.** It is
found from the wrong carrier. A presence test asks whether a value came back;
this defect returns a value, of the right type, from a file that legitimately
holds a field of that name meaning something else.

What that needs is a **precedence** rule — when two carriers disagree, which
wins and why — and there is no such rule in the function. There is only the
order `INFO_FILES` happens to be declared in, which is a fact about a tuple
and not a decision anybody recorded.

So the two questions are different, and a test built for the first will report
green on the second:

- **absence**: did the reader look everywhere the fact may be?
- **precedence**: when it found the fact twice, did it take the right one?

---

## The shape that makes both checkable

**Declare the carriers as data, ordered, and let the order be the precedence
rule.**

A fact becomes a name and an ordered list of `(file, key path)` carriers.
`facts_of` iterates that declaration rather than naming files inline, and the
test asserts, for each fact and each declared carrier, that a workdir holding
**only** that carrier yields the fact. Ordering makes precedence explicit:
`environment_id` would declare `report.json:environment` and
`verify_info.json:environment_id` ahead of `report.json:run_environment`,
and the list is the answer to "which wins", written down instead of implied.

This is the move task 026 made for family parameters and task 041 made for a
view's declared `reads`. Both replaced knowledge living in a function body
with a declaration a test can iterate.

**And the reason the test had to be designed this way is warning 5 arriving
during design rather than after.** `docs/FAMILIES.md` §4.1 warning 5 says a
mutant that does not run the rule's own code proves only that the defect is
reproducible. The fact-to-carrier mapping currently lives in the body of
`facts_of`, so any test of it must **restate** the mapping — and would then
pass while the function drifted away from the restatement, which is the
warning exactly. The declaration is what lets the test run the rule instead of
a copy of it.

That warning was written after two defects had already been shipped. Here it
changed a design before anything was built, which is the first time it has
been used forward rather than as a post-mortem.

---

## Status

- The two-blocks finding is **ruled into task 043's scope**: carriers declared
  as data, ordered, the order being the precedence rule. Folded there rather
  than left as a fourth pass over the same function.
- The two latent readers (`libraries`, `python_version`) are recorded here and
  are the same repair.
- Nothing in this audit was changed. The measurements are reproducible from
  the receipts in `runs/` and `fixtures/arxiv-150k/report/`.
