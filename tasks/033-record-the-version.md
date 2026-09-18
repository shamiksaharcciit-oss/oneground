# Task 033 — Record the version that produced the artifact

## Setup
Branch from `main` after 032 merges: `git checkout -b task-033 main`. Commit
`task 033:` and push after every commit. Do not touch the tag, `site/`, or any
published fixture value.

## Why

**Three tasks this month have paid for the same missing field.**

* **028b** had to date a commit and read two runs' library versions to work
  out which code measured the arxiv workdir's sharded rows, because
  `simulate_info.json` records what was imported and not what imported it.
* **028c** had to measure one configuration at three revisions to settle it,
  and the reading that finally did — *a build that always answers
  `recall_at_1` 0.874 did not produce the recorded 0.875* — is a proof by
  elimination that a single recorded string would have made unnecessary.
* **The library position** (`docs/LIBRARY.md` §2.2) cannot give a card a
  comparability verdict better than `couldnt_check`, for any card, ever,
  until a run records what built it. The paper says so in as many words and
  points here.

A receipt that cannot say what produced it is re-derivable only by someone
who already knows. Every other input to a measurement is recorded — the
seed, the pins, the corpus digests, the run-level settings — and the one that
decides what those inputs *mean* is not.

This is not a determinism task. 029 fixed what varies between environments;
this fixes what a reader can tell about two artifacts from different weeks.

## Do

1. **One function, one shape.** A single helper that returns what produced
   this process:

       {"version": "0.1.0",          # oneground.__version__
        "commit": "b0bfb11…" | null, # 40 hex, or null with a reason
        "dirty": true | false | null,
        "source": "checkout" | "wheel" | "unknown",
        "note": "…"}                 # why commit is null, when it is

   `version` is always available. `commit` is not: an installed wheel has no
   git, which task 022 made a first-class case rather than an edge one. So
   **`null` with a stated reason, never a guess and never a refusal** — the
   couldn't-check habit, applied to provenance exactly as `docs/LIBRARY.md`
   §2.1 applies it to a model version.

2. **Make the wheel case answerable, by construction.** `setup.py` already
   carries a `build_py` subclass that copies fixture files into the package
   tree at build time (task 022). The same hook can write the commit it was
   built from into the package, so an installed wheel answers `commit` as
   confidently as a checkout does. If that is done, `source: "wheel"` carries
   a real commit and `null` is left for the genuinely unknown — a source
   tree with no git, say. Decide it with the cost in front of you: a wheel
   built from a dirty tree must say `dirty: true` or the field lies.

3. **Write it into every declared info file**, beside the library versions
   that are already there:

   | file | written by |
   |---|---|
   | `build_info.json` | `characterize` |
   | `simulate_info.json` | `simulate` |
   | `verify_info.json` | `verify` |
   | `propose_info.json` | `propose` |
   | `state/state_info.json` | `simulate --emit-state` |
   | `report.json` | `report` (it has no separate info file) |
   | `calibration/history.jsonl` | each appended line |

   These are the *declared* halves of each pair, which is where a run
   describes itself, and adding a field to them moves no receipt's digest.

4. **Decide, and state, whether the receipts carry it too.** A receipt
   (`simulate.json`, `characterization.json`, `card.json`, `*.state.npz`) is
   re-derivable from seeds and rules, and the version is one of the rules —
   so there is a real argument for putting it in. **The cost is that every
   recorded digest of every receipt moves**, including the fixtures'
   `MANIFEST.sha256` files and the digests task 026 already had to explain in
   the release notes once. The brief does not decide this; it requires that
   the report decide it explicitly, with the affected digests counted, and
   that whatever is chosen is the same for all four.

   The one place a receipt must carry it either way is **`card.json`**, and
   it must carry *two*: the version that measured the baseline row, read from
   the workdir's `simulate_info.json`, and the version that measured the
   changed row, which is this run's. A card with one of those is a card that
   cannot support a comparability verdict.

5. **Say what an old artifact does.** A workdir written before this task has
   no version anywhere, and nothing can add one honestly. Reading one must
   produce `null` with a reason — *"written before task 033; the version was
   not recorded"* — and every consumer must treat that as couldn't-check
   rather than as a mismatch. **This fixes the future. It does not repair
   the arxiv workdir**, whose sharded rows 028c pinned to a pre-`dc85609`
   build by measurement, and that annotation stays where 028d put it.

6. **Show what changes for a reader.** In the report, one worked example per
   consumer, using artifacts that exist:

   * two `simulate_info.json` files whose versions differ, and the sentence a
     reader can now write without re-measuring anything;
   * a proposal card whose comparability verdict moves off `couldnt_check`
     because both rows carry the same version — produced by re-running one of
     the two cards in `runs/arxiv-150k-via-characterize/proposals/` after
     this lands;
   * `oneground fixture verify` on a fixture whose digests disagree, naming
     the version difference in the same run rather than leaving it to a
     diagnosis.

7. **Tests.** The helper returns a version always; `commit` is `null` with a
   non-empty reason wherever it cannot be known, and the test for that
   simulates the wheel case rather than asserting it in prose; every writer
   in the table above emits the field; a reader of an artifact without the
   field gets `null` and a reason rather than a `KeyError`; and the identifier
   scan still passes, because a commit is not a machine identifier but a
   `dirty` flag invites someone to record a branch name, which would be.

8. **Docs.** `docs/CLAIMS.md` or `docs/VALIDATION.md`, wherever the artifact
   vocabulary is defined: what the field means, that `null` is a real answer,
   and that a consumer may not treat a missing version as a match. Update
   `docs/LIBRARY.md` §2.2's *"the way to earn `comparable`"* sentence to point
   at the field rather than at a future.

## Acceptance

- Every file in the table carries the version and commit of the run that
  wrote it, or `null` with a stated reason.
- The wheel case is answered — either by the build hook or by an explicit
  `null` whose reason says why it was not worth the hook.
- The receipts decision is made in the report, with the affected digests
  counted, and applied uniformly.
- A card carries both rows' versions.
- An artifact written before this task reads as couldn't-check, not as a
  mismatch, and a test says so.
- Suite green, guard clean, identifier scan runs rather than skips, pushed
  after every commit.

## Do not

- Repair an old artifact by inferring a version from a date, a digest, or a
  commit range. 028c's proof by elimination is a report, not a repair.
- Change a published fixture value, or widen a tolerance to accommodate a
  digest that moved.
- Record a branch name, a remote URL, a build path or anything else that
  identifies whose machine this was; a version and a commit are facts about
  the code.
- Build the library's comparability verdict here. This task supplies the
  field it needs and stops.
