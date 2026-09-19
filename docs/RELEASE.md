# Releasing oneground

The procedure as it was actually run: twice, for `0.1.0-preview` and again
for a dated `0.1.0`. Every command here was executed; nothing is
aspirational.

**Only the first of those two was published.** The `0.1.0` run built and
checked the wheel and the sdist and produced the findings below, and then the
dated release it was for was dropped — the product ships once, when it is
ready and tested, with no date. Its tag has been deleted, because it named a
commit that will never be published. The procedure is unaffected: it is what
will be run when the product does ship, and the version columns below are a
record of what was set on the run that exercised it, not a promise about what
the next one will be called.

**Run everything through the pinned interpreter.** On Windows that is
`.venv\Scripts\python.exe`, explicitly — bare `python` is the system
interpreter, which is how task 013 spent a session producing artifacts outside
the pins. Every canonical-artifact command now refuses that, but a release is
exactly when you want the refusal to never fire.

---

## 0. Preconditions

```
git status --short                 # clean, apart from anything you mean to leave
.venv\Scripts\python.exe -m pytest oneground -q
```

The suite must be green **in the venv**. A release cut from an unpinned
interpreter is a release whose artifacts carry `pinned: false`.

## 1. Version

Two strings, deliberately:

A record of the two runs, not a table of what comes next:

| where | `0.1.0-preview` (published) | `0.1.0` (built, not published) | for |
| --- | --- | --- | --- |
| `oneground/__init__.py` `__version__` | `0.1.0rc1` | `0.1.0` | PEP 440; what pip compares and what the wheel is named |
| `oneground/__init__.py` `__display_version__` | `0.1.0-preview` | `0.1.0` | what the release page, the teaser and `--version` say |
| `pyproject.toml` `version` | `0.1.0rc1` | `0.1.0` | must match `__version__` |

Neither is derived from the other, so neither can drift into a shape the other
cannot read. For a **final** release the two coincide; the fields stay,
because the next pre-release separates them again and a field that appears
only when it differs is a field nobody remembers to set. `oneground --version`
prints both when they differ and one when they do not.

`oneground/test_packaging.py` checks the rest of it, and did not exist before
0.1.0: that the pyproject version is the package's own, that every pin in
every extra is the version `requirements.txt` names rather than one somebody
wrote, that nothing is declared without an exact pin, and that a bare
`pip install oneground` fixes every package `environment.PINNED` checks. The
0.1.0-preview procedure caught the invented-pin defect by hand; this is the
same check, run every time.

**And every adapter must have an extra.** `pip install oneground[pgvector]`
failed for three tasks after the pgvector adapter shipped, because nobody
added the extra and nothing looked. The test walks `oneground/adapters/` and
requires each directory to have an extra installing something that
directory's `adapter.py` actually imports.

## 2. Build and check

```
rm -rf dist build *.egg-info
.venv\Scripts\python.exe -m build
.venv\Scripts\python.exe -m twine check dist/*
```

Both artifacts must pass `twine check`. `dist/`, `build/` and `*.egg-info/`
are gitignored: the release attaches the ones you just built, not whatever is
on disk from last time.

**Build the wheel from the checkout, never from an unpacked sdist.** The build
hook stamps the wheel with the commit it was built from, and an unpacked sdist
is not a git checkout, so a wheel built from one carries
`commit: null, note: "built from a tree with no readable git checkout"` — and
every artifact that installation later writes says the same. It is honest and
it is useless: the version and commit are what let a reader tell two artifacts
from different weeks apart (`docs/VALIDATION.md`). Measured, not assumed: an
sdist unpacked and built here produced exactly that, while the same wheel
built from the checkout named its commit.

## 3. The stranger's path

**This is the step that finds things.** Install the wheel into a genuinely
fresh venv and run the commands a stranger would, in that order:

```
python -m venv %TEMP%\og-fresh
%TEMP%\og-fresh\Scripts\python.exe -m pip install dist\oneground-<version>-py3-none-any.whl
%TEMP%\og-fresh\Scripts\oneground.exe --version
%TEMP%\og-fresh\Scripts\oneground.exe characterize <a 2k synthetic corpus>
%TEMP%\og-fresh\Scripts\oneground.exe fixture verify arxiv-smoke
```

`fixture verify` needs the repository tree (fixtures do not ship in the
wheel), so run it from a clone. That is the real stranger's path: clone, pip
install, run.

For 0.1.0-preview this step found that `oneground characterize` raised
`TypeError: run() got an unexpected keyword argument 'env_stamp'` — broken for
two commits, under a green 466-test suite, because every test called
`characterize.run` directly and nothing drove the CLI. Do not skip it because
the suite is green. The suite being green is the reason to do it.

## 4. The release asset

Verify the tarball's members against the fixture manifest **before** renaming
anything:

```
.venv\Scripts\python.exe tasks\scratch\014-verify-asset.py
```

It streams each member out of the tarball and compares to
`fixtures/<id>/MANIFEST.sha256`. An asset whose bytes do not match makes
`oneground fixture verify` contradict on every stranger's machine, which is
the exact opposite of what the asset is for.

Then copy to the release name and digest the whole file:

```
copy %USERPROFILE%\oneground-assets\arxiv-150k-large.tgz ^
     %USERPROFILE%\oneground-assets\arxiv-150k-v1.tgz
```

Put the whole-file sha256 and all three member digests in `RELEASE_NOTES.md`.

**One asset per full fixture**, so 0.1.0 has two. The second was cut from the
loose artifacts rather than copied, with the same three members at the same
paths inside the archive:

```
tar -czf %USERPROFILE%\oneground-assets\stackexchange-150k-v1.tgz ^
    fixtures/stackexchange-150k/vectors.npy ^
    fixtures/stackexchange-150k/queries.npy ^
    fixtures/stackexchange-150k/sample.jsonl.zst
```

Then verify it the same way -- stream every member out of the finished tarball
and compare to the fixture MANIFEST -- before the digest goes anywhere. A
tarball digested without its members checked is a digest of whatever happened
to be copied.

## 5. Docs pass

Grep for every capability word and read each hit by hand:

```
grep -ri "pgvector\|stackexchange\|qps_max\|the lab\|proposal" docs README.md
```

The failure mode is **both** directions. For 0.1.0-preview the README's "What
is planned" section still listed simulate, verify, report and Tier 2 as
unimplemented, months after they shipped — and understating is not safer than
overstating. A reader who finds `oneground report` working after being told it
does not exist stops trusting the page, and the page's whole claim is that it
does not exaggerate.

Check `docs/CHARTER.md`'s status table against the git log.

## 6. The public branch

**Only on the first release.** `main` *is* the public history from
0.1.0-preview onward, so 0.1.0 skipped this step entirely: there is no private
`master` left to cut from, and nothing to squash. What still applies every
time is the leak scan, which has moved up to run against the tracked tree
rather than against a branch about to be created -- `oneground/environment.py`
provides it and `oneground/test_environment.py` runs it in the suite, and it
found a live leak on `main` when task 017 added it.

The rest of this section is the record of how the cut was made, kept because
nothing else records it.

### What happens to the branches

This is a one-way cut, not a pair of branches kept in step:

```
master  ──(cut once)──▶  public  ──(rename)──▶  main      the only history from here
   │
   └──▶ archive/private-history                           kept locally, never merged back
```

- `public` is cut **once**, from the release commit, as an orphan branch with
  a single commit.
- It is renamed `main` **locally, before the push**, and becomes the **sole**
  history from then on. Renaming first is what makes the push a plain
  `git push -u origin main` rather than a refspec that has to explain itself.
- The old `master` is kept locally as `archive/private-history`. Nothing ever
  merges back into it, and nothing merges out of it. It exists so the working
  — the failed pod sessions, the scratch scripts, the dead ends — is not lost,
  not so it can be resumed.

**What goes in the cut is the release and nothing after it.** For
0.1.0-preview that meant task 015 was already under way on its own branch and
was deliberately excluded: 015 is v0.1. Check `git log` before cutting and be
sure the commit you are cutting from is the one the version names.

```
git branch -m master archive/private-history
git branch -m public main
```

`master` keeps the full history privately until that rename. `public` is an
orphan branch with one commit.

```
git checkout --orphan public
git rm -r --cached . >nul
git add <everything that ships>
git commit -m "oneground <version>"
git diff master public --stat        # what was dropped, and it must be only that
```

**Scan before you squash**, not after:

```
.venv\Scripts\python.exe tasks\scratch\014-leak-scan.py
```

Three classes: developer paths, pod ids, IP addresses. Read every hit. Some
are false positives — `1.2.3.4` and `10.0.0.1` in the pod tests are synthetic
fixtures, not anyone's machine — and deciding that requires looking, not
pattern-matching.

The `tasks/` briefs and reports stay. They are the receipt trail and part of
the pitch: they record what each measurement cost, including the runs that
failed. That is a deliberate choice to publish the working, and it is what
makes the rest of the claims checkable.

## 7. Tag

```
git tag -a v<version> -m "oneground <version>"
git log --oneline -1 public
```

## 7b. Redacting a developer path

The scan in step 6 finds them; deciding what to do with each is a judgement,
and 0.1.0-preview's rulings are worth carrying forward:

- **Developer paths are redacted**, not removed with their file.
  `C:\Users\<name>\oneground-assets\...` becomes `~/oneground-assets/...`.
  Dropping every file that mentions one would have deleted `docs/VERIFY.md`
  and most task reports, which is the receipt trail the release is partly
  for.
- **Pod ids are kept.** A terminated RunPod id is not a credential and grants
  nothing, and `environment_id: <id>` is *how* the same-environment rule is
  demonstrated. Removing them leaves claims whose evidence has been deleted.
- **Synthetic addresses are not leaks.** `1.2.3.4` and `10.0.0.1` in the pod
  tests are fixtures. Read every hit; do not pattern-match.

Two traps, both hit on the first pass:

1. **Mixed separators.** Replacing only the prefix leaves
   `~/oneground-assets\arxiv-150k\vectors.npy`, which Windows tolerates and
   POSIX does not. Normalise the whole path.
2. **`~` has to resolve.** `intake.resolve()` expands it now; before 014 it
   did not, and a redacted requirements file would have produced a path with
   a literal tilde in it. A redaction that breaks the file it redacts is
   worse than the leak.

An external runner should never need your layout at all:

```
oneground fixture verify arxiv-150k --asset <where you extracted it>/fixtures/arxiv-150k
```

`--asset` names the extracted folder outright, for both the digest half and
the value half. The tarball's members are `fixtures/arxiv-150k/vectors.npy`,
`queries.npy` and `sample.jsonl.zst`, so the folder is always
`fixtures/<id>` under wherever it was extracted. `--asset ./arxiv-150k`, which
this section used to show, points one level short: every value comes back
couldn't-check with "the release asset is not present".

## 8. Developer runs

Everything above is local and reversible. Everything below is not, and none of
it is done by the agent:

- create the public GitHub repository (Apache-2.0)
- push `public` as `main`, and push the tag
- create the release, attach `arxiv-150k-v1.tgz`, paste `RELEASE_NOTES.md`
- `twine upload` to PyPI with the token

The agent prepares `twine check` output and stops. Publishing needs
credentials and is irreversible; both are reasons it is a person's decision.

---

## What this procedure has caught

Kept because a procedure's value is in what it finds, and a list of near
misses is more persuasive than a list of steps.

| release | step | what it caught |
| --- | --- | --- |
| 0.1.0-preview | 3 | `oneground characterize` raised TypeError on every invocation; broken for two commits under a green suite |
| 0.1.0-preview | 2 | `[qdrant]` and `[calibrate]` extras pinned versions that were invented rather than read from `requirements.txt` |
| 0.1.0-preview | 5 | the README listed four shipped commands as unimplemented |
| 0.1.0 | 2 | **no `[pgvector]` extra existed at all.** The adapter shipped in 015 and `verify`'s readiness probe has imported psycopg since 017c; `pip install oneground[pgvector]` failed on a release claiming two engines |
| 0.1.0 | 2 | no test in the repository read `pyproject.toml`. The preview's invented-pin defect was fixed by hand and nothing stopped it returning |
| 0.1.0 | 5 | the README's "What is planned" listed pgvector, `qps_max` and a second corpus — all three shipped in 015, 016 and 017. Understating, exactly as the preview did, in the other direction |
| 0.1.0 | 5 | `docs/VALIDATION.md` still quoted task 011 declining to implement `qps_max`; `docs/VERIFY.md` still listed Qdrant's gRPC path as absent; `docs/INTAKE.md` still said only arxiv-150k was matchable |
