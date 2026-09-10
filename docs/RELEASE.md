# Releasing oneground

The procedure as it was actually run for `0.1.0-preview`, so v0.1 repeats it
rather than reinventing it. Every command here was executed; nothing is
aspirational.

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

| where | value | for |
| --- | --- | --- |
| `oneground/__init__.py` `__version__` | `0.1.0rc1` | PEP 440; what pip compares and what the wheel is named |
| `oneground/__init__.py` `__display_version__` | `0.1.0-preview` | what the release page, the teaser and `--version` say |
| `pyproject.toml` `version` | `0.1.0rc1` | must match `__version__` |

Neither is derived from the other, so neither can drift into a shape the other
cannot read. `oneground --version` prints both.

## 2. Build and check

```
rm -rf dist build *.egg-info
.venv\Scripts\python.exe -m build
.venv\Scripts\python.exe -m twine check dist/*
```

Both artifacts must pass `twine check`. `dist/`, `build/` and `*.egg-info/`
are gitignored: the release attaches the ones you just built, not whatever is
on disk from last time.

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
oneground fixture verify arxiv-150k --asset ./arxiv-150k
```

`--asset` names the extracted folder outright, for both the digest half and
the value half.

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
