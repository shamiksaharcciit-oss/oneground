# Report: 068-volume-inspect-results-and-placement-priced

## Repo state expected vs found

Expected `sessions/036-volume-inspect.yaml` (task 067) unrun, and no
record of what `vecbench` actually holds for the three corpora. Session
20260925-193004 (pod `6cqzioes4klnkd`), bundled at `c5db6f9`, was already
up and running when this task started. Watched to `DONE`, fetched, pod
terminated (`state: gone from the account`, record says terminated).
Elapsed ~4-5 min; well inside the $0.50 cap. Branch `task-068` from `main`
at `c5db6f9`.

## What was done

**What is on the volume, and where.** The full receipt is
`036-volume-inspect/036-volume-inspect.json` (fetched, extracted, kept)
and `tasks/scratch/036-volume-inspect-log/oneground-session.log`. The
depth-4 listing under `/workspace` (38 entries, cloned repo and HF cache
excluded) plus the unrestricted name search together give a complete
picture:

    arxiv-150k          /workspace/arxiv-150k/{vectors.npy,queries.npy}  extracted
                         /workspace/arxiv-150k-large.tgz                 unextracted, on the volume
                         /workspace/arxiv-150k/sample.jsonl.zst          ABSENT (extracted dir is missing it)
    stackexchange-150k   nothing under /workspace matching any candidate name or the corpus's own directory name -- ABSENT ENTIRELY
    sec-filings-10k      /workspace/sec-filings-10k/documents.jsonl.zst  extracted, present, correctly placed

**Whether the three corpora are present under any layout.** Yes for
arxiv-150k and sec-filings-10k, in different senses; no for
stackexchange-150k. The one directory search found for stackexchange
(`/workspace/oneground/fixtures/stackexchange-150k`) is inside the cloned
repo checkout, not the volume's own data area, and holds none of the four
candidate filenames -- it is the ordinary git-tracked fixture skeleton
every session clones, not a sign any corpus data was placed there.

**Digests of what was found, checked against what this repo already
declares.** Every one of this repo's tracked `fixtures/<corpus>/
MANIFEST.sha256` files carries the reference:

    /workspace/arxiv-150k/vectors.npy
      volume:    141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa
      manifest:  141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa   MATCH
    /workspace/arxiv-150k/queries.npy
      volume:    dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b
      manifest:  dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b   MATCH
    /workspace/sec-filings-10k/documents.jsonl.zst
      volume:    8a1d8ebba8781360b6b26a2e5d0696aee549ef262700a18df31de63d95934f35
      manifest:  8a1d8ebba8781360b6b26a2e5d0696aee549ef262700a18df31de63d95934f35   MATCH

Every digest the inspection found matches this repo's own declared bytes
exactly -- **nothing on the volume has the right name and the wrong
content.** `arxiv-150k/sample.jsonl.zst` is not on the volume to check a
digest against directly, but the tarball that would produce it is: task
022b's own crosscheck of `arxiv-150k-large.tgz` (`arxiv-150k-v1.tgz`
there, same 483,468,013-byte size as `/workspace/arxiv-150k-large.tgz`)
streamed `fixtures/arxiv-150k/sample.jsonl.zst` from inside the archive and
confirmed it against this same manifest --
`404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655`. The
tarball on the volume carries the right bytes; they are simply not
extracted.

**The ruling: move the files, not point the script -- for the one corpus
where that question has an answer.** `arxiv-150k`'s `sample.jsonl.zst`
already exists, correctly, inside a tarball already on the volume, next to
a directory (`/workspace/arxiv-150k/`) that already holds its two sibling
files at the exact path the run script expects. There is no ambiguity to
resolve by pointing the script somewhere else -- the manifest, the
tarball, and the extracted directory all agree on one path, and only the
extraction is incomplete. `sec-filings-10k` needs neither move nor point:
it is already correct. Argued from what is on the volume, not from which
is easier: "point the script" would mean inventing a second, different
path convention to read `fixtures/arxiv-150k/sample.jsonl.zst` out of an
unextracted tarball or a repo checkout at run time, when the existing
convention (`$ASSETS/<corpus>/<file>`, flat, matching `arxiv-150k/
{vectors,queries}.npy`'s own placement) already has everywhere else it
needs to be.

**stackexchange-150k is not a reconciliation question at all.** It is
genuinely, completely absent from the volume -- not at a different path,
not partial in the sense of one missing file, not something either
"move" or "point" can fix, because there is nothing on the volume to move
and no path to point at. Stated plainly, per the brief: **this corpus
needs to be placed on the volume before `036-models.yaml` can run**, and
that is not folded into this report as a retry -- it is priced separately,
below, exactly as instructed.

**`sessions/036-place-corpora.yaml` and `corpora/
run_036_place_corpora.sh`** -- priced, not run, and the one thing the
brief did not ask for but this finding requires: it also completes
arxiv-150k's extraction, since that gap has the identical shape (a file
this repo already has bytes for, missing from the layout a run needs it
in) and leaving it for a second session would be the same mistake in
miniature. Does exactly two things, both read-only against the repo's own
declared digests and nothing else:

1. Extracts `sample.jsonl.zst` from `arxiv-150k-large.tgz`, already on the
   volume -- no upload.
2. Extracts `stackexchange-150k-large.tgz`'s three members --
   `vectors.npy`, `queries.npy`, `sample.jsonl.zst` -- uploaded via this
   session's own `inputs:` from `../oneground-assets/
   stackexchange-150k-large.tgz` (460.1 MB, present on this machine and
   verified locally, before this session spec was written, against
   `fixtures/stackexchange-150k/MANIFEST.sha256`: all three members match
   exactly).

Every extraction is verified against the repo's own tracked manifest
digest before the script reports success; a mismatch refuses and leaves
the wrong file in place rather than deleting it, so the volume never ends
up holding a plausible-looking file with the wrong bytes.

**Priced, honestly, including the one thing that could not be measured in
advance.** `input_size_cap_mb: 500` (the default is 50, explicitly refused
for anything this large without saying so). Every session priced so far
uploaded inputs measured in kilobytes; this uploads 460 MB over `scp`, and
this machine's own upload bandwidth has never been measured by this
project. The tarball's local extraction and verification took ~19 s on
this laptop's own disk, so the two extractions and four digest checks are
not the risk; the upload is, and the caps are built with `stall_minutes:
20` / `max_hours: 0.5` as real headroom for a slow one rather than a
guessed number dressed as a measurement. `oneground pod plan
sessions/036-place-corpora.yaml`: cost cap `0.5h x $0.72/hr = up to
$0.36`, within `max_usd 0.75`. Nothing was created.

## Measurements

- `oneground pod plan sessions/036-place-corpora.yaml`: cost cap $0.36,
  within `max_usd 0.75`. Nothing created.
- Local verification of `../oneground-assets/stackexchange-150k-large.tgz`
  (460,106,992 bytes): all three members' sha256 match `fixtures/
  stackexchange-150k/MANIFEST.sha256` exactly. `arxiv-150k-large.tgz` is
  not present on this machine to re-verify locally; its member's digest is
  taken from task 022b's own crosscheck of the same manifest, not
  reproduced fresh this task.
- Local dry run of `run_036_place_corpora.sh`'s extraction-and-verify logic
  (patched paths only) against the real stackexchange tarball: all three
  `verify()` calls pass with the exact digests above.

## Verification

Passed: watch/fetch/terminate on session 20260925-193004; every digest
comparison above, cross-checked against this repo's own tracked
`MANIFEST.sha256` files (not re-derived, read directly); `bash -n` and a
local dry run on `run_036_place_corpora.sh`; `oneground.pod.session.load()`
on the new spec; `oneground pod plan`, prices within cap, creates nothing.

Not verified: `arxiv-150k-large.tgz`'s member digest against a fresh local
extraction (the tarball is not on this machine) -- relied on task 022b's
own crosscheck instead, which is itself a receipt this repo already
carries, not a fresh claim. The 460 MB upload's real duration -- stated
above as the one unmeasured input to this session's price.

## Observed, not done

- `sec-filings-10k`'s placement was checked and found already correct;
  nothing was done for it, and nothing needs to be.
- Whether other pod sessions (the ones not driven by `036-*.yaml`) assume
  a volume layout this same inspection would also unsettle was not
  checked -- out of scope for this task, which was scoped to the three
  corpora `036-models.yaml` needs.

## Repo now contains

- `sessions/036-place-corpora.yaml` (new).
- `corpora/run_036_place_corpora.sh` (new).
- `036-volume-inspect/036-volume-inspect.json`,
  `tasks/scratch/036-volume-inspect-log/oneground-session.log`,
  `tasks/scratch/036-place-corpora-log/` (fetched receipts; gitignored,
  local only, listed here since they are the evidence the ruling above is
  built from).
- `tasks/068-volume-inspect-results-and-placement-priced.report.md` (new).

## Blocked on developer

The `y` at the terminal for `oneground pod up sessions/036-place-corpora.
yaml`. Once it runs and both corpora verify, `036-models.yaml` can be
re-planned and run without this blocker; nothing about that session
changes as a result of this one.
