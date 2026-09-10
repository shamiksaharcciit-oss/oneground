# Task 014 — `oneground 0.1.0-preview`

## Expected repo state
013 committed; `task-012` merged into master (developer does the merge
first — stop if `git log` shows no 012 commits on master). Tree clean.

## Why
The teaser on 16 September carries a working install line. This task
makes that true from a stranger's machine: a public repo with a clean
first commit, a release asset with digests, `pip install oneground`
producing the four commands, and docs that claim only what ships.

## Do
1. **History hygiene, on a new orphan branch `public`** (master keeps
   the full history privately): squash to one commit "oneground
   0.1.0-preview" containing everything except `tasks/scratch/`,
   `.oneground/`, `runs/`, session records, and any file that names a
   pod id, an IP, or a developer path (the developer's home directory) — grep for all
   three and report hits before removing. `tasks/` briefs and reports
   stay; they are the receipt trail and part of the pitch. Verify the
   squash by `git diff master public --stat` and list what was dropped.
2. **Version and packaging**: `oneground/__init__.py` → `0.1.0-preview`
   (PEP 440: `0.1.0rc1` with the display name "0.1.0-preview" in
   `--version`); `pyproject.toml` complete: description, licence
   Apache-2.0, classifiers, Python ≥ 3.12, dependencies from
   `requirements.txt` with the `pywin32` marker, optional extras
   `[qdrant]`, `[pod]`, `[calibrate]`; console script `oneground`.
   Build sdist + wheel; install the wheel into a **fresh** venv on this
   machine and run `oneground --version`, `oneground characterize
   requirements.example.yaml` against a 2k synthetic `.npy`, and
   `oneground fixture verify arxiv-smoke`. That is the stranger's path;
   report each command's output.
3. **Release asset**: `arxiv-150k-v1.tgz` from
   `~/oneground-assets/arxiv-150k-large.tgz` — verify its
   three member digests against the fixture MANIFEST before renaming;
   write `RELEASE_NOTES.md` with the digests, the licence line (CC0
   metadata), and the `oneground fixture verify arxiv-150k` instruction.
   Do not upload; the developer attaches it to the GitHub release.
4. **Docs pass** — every file under `docs/` and both READMEs: no
   present-tense claim for anything not in this release. The lab, the
   proposal loop, pgvector, StackExchange, `qps_max`: all "planned" with
   the dates from the promise block. `docs/CHARTER.md` status table
   current. Add `CONTRIBUTING.md` (the four contribution units, the
   conformance gate for adapters, the calibration gate) and
   `CODE_OF_CONDUCT.md` (Contributor Covenant, unmodified).
5. **Tests on the public branch**: full suite from a fresh clone of
   `public` — the gitignored-`runs/` test must skip cleanly, and no test
   may depend on a developer path.
6. **Tag** `v0.1.0-preview` on `public`. Report the commit hash.
7. `docs/RELEASE.md`: the release procedure as run, so v0.1 repeats it.

## Acceptance
- Fresh-venv wheel install runs the three commands successfully.
- `public` branch: one commit, no pod ids, IPs, or developer paths
  (grep proof in the report).
- Release notes carry the three asset digests matching the MANIFEST.
- Docs: grep for "simulat", "verif", "lab", "proposal", "pgvector"
  reviewed by hand; report each present-tense claim kept and why.

## Developer runs (after the report)
- create the public GitHub repo `oneground` (Apache-2.0), push `public`
  as its `main`, push the tag, create the release, attach the asset,
  paste the release notes. Then `pip install oneground` is real once
  PyPI is done — PyPI publish is a developer step with the token; the
  agent prepares `twine check` output only.

## Do not
- Push anywhere. Publish to PyPI. Rewrite master's history. Touch
  `site/teaser/`.
