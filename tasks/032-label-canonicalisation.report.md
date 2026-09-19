# Report: 032 (the label wrinkle) and 032b (the state half of the proof)

## Repo state expected vs found

Expected to branch `task-032` from `origin/main`: done, at `da2aa7b`. One
correction along the way, the developer's: the first attempt left the work on
`main` in the main checkout — the checkout had been moved to `main` by the
merge while the branch existed — and it was moved with `git stash`,
`git checkout -B task-032 origin/main`, `git stash pop`. Nothing was lost and
nothing was committed to `main`.

Expected the ruling at `tasks/oneground-proposals-two-paths.md`: found (the
developer corrected the filename they first gave).

Expected, for 032b, "the lab stream's pod state from session 20260918-205534
on disk in the worktree": **not found, and it does not exist.** Detail in
§3 — this is the finding that stopped 032b.

## 1. The ruling, merged (`cd9f547`, `94f85eb`)

`docs/PROPOSALS.md` §2.1 is replaced by the two-paths ruling and §2.4 gains
the card's half of it, with §3's collected refusals and §5's open questions
brought into line and §5a told that tier 1 is path 1. No renumbering was
needed: the ruling replaces one section in place and adds to another.
`tasks/oneground-proposals-two-paths.md` is deleted in the same commit, so
the ruling lives in one place.

Then the four rulings from the review, in `94f85eb`: `authored_by` as a
checked `proposal_provenance` claim citing `propose_info`; path 2 as two
phases with the translation persisted between them, and after translation
path 2 *is* path 1; an unreported model version as `null` with a stated
reason; and the sampling parameters as a closed list of five. §4's first
honest limit, which had come to read as though translation existed, was
rewritten — the developer named the section.

**Not implemented, and not asked for:** tier-1 cards do not yet carry
`authored_by: user`, and there is no `proposal_provenance` claim kind in
`report/claims.py`. Both are small and both are path-1 work that the ruling
now specifies; they are listed under *Observed, not done*.

## 2. The label wrinkle (`f147b9b`)

### What it was

Reproduced before anything was changed, in
`tasks/scratch/032-label-wrinkle.py`:

    semantic_sharded, through Config.make (what a policy does)
       all named        semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2]
       omit probe       semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2]   DIFFERENT

Every declared parameter behaved the same way, in all three families: written
at its default and left out were two labels, and therefore two rows in
`simulate.json` — a sweep could measure identical work twice and present it
as two configurations.

Each family's own `configs()` did *not* have the wrinkle, because each seeded
a dict of defaults before applying an `include` entry. So the defaults existed
three times per family — at every `config.get(key, X)` call, again in that
seed dict, and nowhere a reader could look them up — and nowhere
`Config.make` could reach. A policy (`proposals/policy.py`), the calibration
helper and `fixture/reference.py` all go through `Config.make`.

### What was done

`Param` gains `default`, with a `NO_DEFAULT` sentinel for a key that must be
named; `canonical_params` fills every declared **parameter** a caller left
out; `Config.make` canonicalises through it. Each family declares its defaults
once and reads them back through `_d(key)`, so the number a config is labelled
with and the number its build uses are the same one by construction. The two
seed dicts are gone.

Only `parameter` keys are filled, and the two exclusions are the point:

* a **build** setting is not filled — `deterministic=True` is a run someone
  asked for and `deterministic=False` is a different build, and task 029
  compared exactly those two by label (`029-kmeans-determinism.report.md`
  carries a label with `deterministic=True` in it);
* a **run** setting is not filled — `_with_shard_depth` adds `shard_depth`
  without re-labelling, so two sweeps of the same grid stay comparable row
  for row.

### Measurements

| | |
|---|---|
| families canonicalised | 3 |
| `config.get` call sites now reading the table | 28 (13 + 9 + 6) |
| default literals removed | 28 call sites + 2 seed dicts |
| new tests | 8, seven of them parametrised over the three families |
| `oneground/models` | **65 passed** |
| whole suite | **1010 passed, 2 skipped** in 392 s |
| identifier scan | **0 findings over 386 paths** |

**Against recorded data, which is the check that matters.** For every row in
`runs/*/simulate.json`, the label task 032 produces from that row's own
params was compared with the label the pre-032 code produced from the same
params: **15 unchanged, 0 moved.** Three more rows are refused outright by
026's parameter check — they are older rows carrying `shard_depth` in
`params` for families that do not declare it settable, which predates this
task. The three published fixture labels are pinned by their own test.

### The tests, and why each one

* both spellings give one label and one params dict (the wrinkle itself);
* both spellings **build the same index**, return the same ids and the same
  footprint — a label that collapsed two spellings the family measures
  differently would be worse than the wrinkle;
* a non-default value is still its own configuration (the negative control
  against over-collapsing);
* a build setting at its default is not collapsed, and `deterministic=False`
  still differs from `deterministic=True`;
* a run setting does not change a label;
* the three published labels are the ones canonicalisation produces;
* every read of a defaulted key in family source falls back to the table
  rather than to a literal (the one-source-of-truth property, asserted);
* and a negative control for the guard itself: the same comparison against
  the un-canonicalised label, which does differ.

### One hazard, recorded

The scripted pass that pointed call sites at the table also matched
`grid.get("shards", space.node_counts)` — a `.get` on a *grid*, not on a
config — which made `node_counts` an integer and broke `hash_sharded`'s
sweep. The reproduction script caught it immediately; all 28 rewritten sites
were then audited by hand and that one reverted. A rewrite keyed on the
argument name rather than the receiver is the kind of thing that passes a
grep and fails a run.

## 3. 032b: the state half is unproved, and the session that would prove it

### What is on disk, and what is not

Session **20260918-205534** ran `corpora/run_029_proof.sh` on a pod
(RTX PRO 4000, EU-RO-1, branch `task-029` at `dd689ee`, 288 s of compute).
Its output is in the second worktree at `runs/029-proof-pod/`, and it carries:

    build_info.json  centroids-deterministic.npy  characterization.json
    ground_truth.npy  ground_truth_scores.npy  host.txt  MANIFEST.sha256
    queries_ids.json  sample_ids.json  simulate.json  simulate_info.json

**There is no `state/` directory, in the fetched tree or in the tarball**, and
`simulate_info.json` from that run records no state. Its own session spec says
so in as many words: *"brings back simulate.json, simulate_info.json and the
centroids."* The run predates `--emit-state` on that branch.

So the claim 032b was asked to prove — that the emitted state columns are
byte-identical across the two environments — is **unproved, not disproved**.
Nothing on disk contradicts it and nothing supports it.

### What the claim would be, and why it is a fair one

State is written as `*.state.npz` receipts beside a declared
`state_info.json`. `oneground/models/state.py` fixes every zip entry's
timestamp and sorts the entries, *"so the same state produces the same bytes
and its sha256 in MANIFEST.sha256 means something"* — so byte-identity is the
right claim rather than a hopeful one. On the laptop's reference run the two
files are 8.0 MB (`single_node_hnsw`) and 18.0 MB (`semantic_sharded`), the
latter carrying twelve columns: the assignment half (`home_region`,
`nearest_region`, `centroid_dist`, `copy_count`, `copy_set`) and the
candidate half (`cand_id`, `cand_score`, `cand_shard`, `offsets`,
`survived_dedupe`, `true_ids`, `true_rank`).

The assignment columns are where a k-means difference would show, which is
what makes this the other half of 029's proof rather than a repetition of it:
029 compared the centroids and the measured rows, and the assignment columns
are what those centroids *did* to 150,000 vectors.

### The session, prepared and priced, not run

`sessions/032b-state-proof.yaml` and `corpora/run_032b_state_proof.sh`
(`bf8c625`): the same corpus, the same uploaded characterization, ground
truth and sample ids as 029's session, the same image, `simulate --emit-state`
instead of `simulate`, and the whole workdir fetched.

`oneground pod plan` on it, with the key read from the user environment into
the subprocess and never printed:

    gpu        : RTX PRO 4000   [NVIDIA RTX PRO 4000 Blackwell]  stock Low
    datacenter : EU-RO-1   (derived from the volume, not the spec)
    price      : $0.50 - $0.57/hr, confirmed at the TOP of the range
    COST CAP   : 1 h x up to $0.57/hr = up to $0.57   within max_usd $2.00
    Nothing was created. This is a dry run.

### The laptop half, run

`requirements.arxiv-150k.determinism.local.yaml` is the pod file's twin,
differing in exactly two things — where the corpus is and where the run
writes — so any difference between the two halves' state is a difference
between the environments rather than between two requirements files. The six
inputs the session uploads were copied from `runs/020-ref-arxiv` first, so
both halves simulate the same sample against the same ground truth.

    oneground simulate requirements.arxiv-150k.determinism.local.yaml --emit-state
    2 configurations measured in 9.7 min

at commit **`b0bfb11`**, which is what the session now pins. What it wrote:

| file | bytes | sha256 |
|---|---|---|
| `semantic_sharded__018da1b7.state.npz` | 18,025,619 | `34a15b42456934f2…` |
| `semantic_sharded__c95327ef.state.npz` | 18,025,573 | `77e369d411c05d8d…` |

Those two digests are the laptop's side of the claim. `corpora/compare_state.py`
takes the two `state/` directories and reports, per shared file, whether the
bytes match and — where they do not — which column differs, by how many
elements, and with what maximum delta. It judges nothing and exits 1 on a
residual.

### Two findings from the laptop half alone

**1. The two rows are the same build, and the state proves it.** The pod
file's `simulate` block produces two configurations: its `include` entry
writes `deterministic: true` explicitly and its grid does not, and a build
setting is deliberately not canonicalised into one label (§2). Comparing the
two files column by column: **23 of 24 entries identical, the exception being
`header.json`**, which records the configuration label. So the duplicate row
is duplicate work — about five minutes of it on the pod, inside the cap and
not worth changing the frozen pod file for, but worth knowing it is there.

**2. Today's state does not match the 15 September reference run's, and the
artifacts say why.** The same configuration's state file, same name, same
size, different bytes:

    today   (b0bfb11)        18,025,573   77e369d411c05d8d…
    15 Sept (020-ref-arxiv)  18,025,573   a965dc2987e8b825…

**18 of 24 columns differ**, including `partition.centroids` (126,720 of
196,608 elements), `assignment.home_region` (982 of 150,000 vectors) and
`assignment.copy_count` (899 of 150,000). The cause is recorded in the two
runs' own `simulate_info.json`: the 15 September run has no
`deterministic_note` at all, and this one says *"faiss pinned to one OpenMP
thread and its distance computations kept off the BLAS path"* — the rule that
`4cc4869` (task 029 step 3, 18 September) introduced. The old state is
therefore **not a valid baseline** for this comparison; only a pod run at the
pinned commit is.

That is the same lesson task 028c had to establish by measurement, arriving
unbidden: a state file from one commit subtracted from a state file from
another measures the commit. It is why the session pins, and why the runner
refuses to run unpinned.

### The pin

`sessions/032b-state-proof.yaml` sets
`ONEGROUND_PINNED_COMMIT: b0bfb118322409b1e4ec9cfaa1177ad3f17734bf`, and
`corpora/run_032b_state_proof.sh` refuses to measure anything unless
`git diff --quiet $PIN HEAD -- oneground/` is clean, naming the differing
files if it is not. It compares the package rather than `HEAD` on purpose: a
later commit that touches only a report or the session file is the same
simulator, and saying so is the honest check rather than the convenient one.
A pinned commit missing from a shallow clone is a refusal with what to run.

## Blocked on developer

1. **`oneground pod up sessions/032b-state-proof.yaml` is yours to start**,
   and I have not launched it. Up to $0.57 against a `max_usd` of $2.00, and
   it needs a typed `y`.
2. **Sequence it against the lab stream's task-030 work in that worktree.**
   The session must be launched from the worktree holding
   `runs/020-ref-arxiv`, because that is where its six uploaded inputs live
   and `runs/` is gitignored — and only one session should be in that
   directory at a time.
3. **The pod checkout must contain `b0bfb11`.** The runner checks
   `oneground/` against it and refuses otherwise; a shallow clone needs a
   deeper fetch first.
4. When the tarball is back: `python corpora/compare_state.py
   runs/032b-state-local/state <fetched>/state` is the whole comparison, and
   I will read the residual if there is one.

## Observed, not done

1. **Tier-1 cards do not carry `authored_by: user`**, and there is no
   `proposal_provenance` claim kind, though §2.4 now requires both. Small,
   path-1 work, and not in this brief.
2. **A recorded row's `params` does not always round-trip to its label.**
   Ten of the eighteen rows in `runs/*/simulate.json` carry `shard_depth` in
   `params`, so re-deriving a label from them produces one with
   `shard_depth=100` in it, or a refusal for the families that do not declare
   the key settable. This predates 032 and is the same family of wrinkle one
   step over: a key in `params` that the label does or does not reflect.
   Worth a decision about what `params` is *for* before anything reads it
   back.
3. **`sessions/029-determinism-proof.yaml`'s comment block is now slightly
   wrong** about what the session proved, since it claims the laptop side "is
   already on disk from the same command" for a comparison that never
   included state. Not this task's file to edit.

## Repo now contains

    docs/PROPOSALS.md                       §2.1 replaced, §2.4 extended, §3/§4/§5/§5a in line
    tasks/oneground-proposals-two-paths.md  deleted; the ruling lives in the paper
    oneground/models/base.py                Param.default, NO_DEFAULT, canonical_params, default_of
    oneground/models/*/model.py             defaults declared once, read through _d(key)
    oneground/models/test_parameters.py     8 tests for one label per configuration
    sessions/032b-state-proof.yaml          the state session, planned and unrun
    corpora/run_032b_state_proof.sh         its runner
    tasks/032-label-canonicalisation.report.md   this report
    tasks/scratch/032-label-wrinkle.py      the reproduction (untracked, .gitignore:62)
