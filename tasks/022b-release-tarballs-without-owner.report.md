# Report: 022b-release-tarballs-without-owner

## Repo state expected vs found

| expected | found |
|---|---|
| `main` at `713b9b2`, the final 022 commit | yes; `tasks/020-simulator-state.md` untracked, left alone |
| `v0.1.0` not yet retagged | on `383c7a1`, **not moved** |
| the two release tarballs in `~/oneground-assets/` | yes, plus `arxiv-150k-large.tgz`, a byte-identical copy of the old `arxiv-150k-v1.tgz` (`cmp`) |

## What was done

### 1. What the tarballs carried

An inspection script (`inspect_tgz.py`, kept in the scratch directory) reads the gzip member header (RFC 1952: MTIME, OS, FNAME,
FCOMMENT, FEXTRA) and every tar header (uid, gid, uname, gname, mode, mtime,
pax headers), without reading the contents.

| archive | gzip header | every member's owner |
|---|---|---|
| `stackexchange-150k-v1.tgz` | clean: mtime 0, no name, no comment | **uid 197609, gid 197609, uname = this machine's local user name**, gname empty |
| `arxiv-150k-v1.tgz` | clean | uid 0, gid 0, uname `root`, gname `root`: **no leak** |
| `arxiv-150k-large.tgz` (not a release asset name) | clean | the same as the old arXiv tarball |
| `smoke-small.tgz`, **tracked in the repository** | clean | uid 0, gid 0, `root`/`root`; its text member `logs/build-arxiv-smoke.log` scans clean |

No pax headers in any of them. The user name is not written in this report.

### 2. Both release tarballs repacked

For each, in a scratch directory, never touching `~/oneground-assets/` until
every check had passed:

1. every member of the **original** streamed out of the archive and hashed
   against `fixtures/<id>/MANIFEST.sha256`: all match;
2. extracted, then repacked in the original member order:

       tar --format=ustar --owner=0 --group=0 --numeric-owner -cf - \
           fixtures/<id>/vectors.npy fixtures/<id>/queries.npy fixtures/<id>/sample.jsonl.zst \
         | gzip -n > <id>-v1.tgz

   `ustar`, so there are no pax extended headers; `gzip -n`, so the gzip
   header stores no name or timestamp;
3. the **repacked** archive's headers dumped: uid 0, gid 0, uname and gname
   empty, gzip header clean;
4. every member of the **repacked** archive streamed out of it and hashed
   against the manifest: all match. **The contents are provably unchanged:**
   the same three sha256 values, read from inside each new archive;
5. the extended identifier scan (below) run on each new archive: 0 findings.

Then the originals were moved to `~/oneground-assets-superseded/`, outside the
assets directory, and kept, not deleted. The repacked files took their names
in `~/oneground-assets/`, and their digests were re-checked in place.
`arxiv-150k-large.tgz` was left as it is: it is not a release asset name, and
its `root` owner is not a finding.

**Two header fields changed besides the owner:** member modes are now
`0644` (the arXiv tarball had `0666`), because extraction on this system
writes `0644` and `tar` recorded what it read. Member mtimes are the
originals'. Neither identifies anyone.

### 3. The identifier scan looks inside archives

`oneground/environment.py`:

- **`archive_findings(path)`** reports, for one tar archive:
  - any owner uid or gid other than 0;
  - any owner name other than a generic account (`root` and the like), whoever
    it names, since another person's name would leak just the same;
  - the gzip header's stored FNAME and FCOMMENT, member and link names, and pax
    headers, through the same `scan_text` rules as tracked files;
  - the text of every member up to 1 MB (a build log is a file like any
    other).

  An archive that cannot be read is reported as `unreadable archive, not
  checked`, never passed.
- **`asset_archive_findings(dirs)`** runs that over every `.tgz`, `.tar.gz` and
  `.tar` under the asset directories (default `~/oneground-assets`, the
  directory `fixture verify` reads). It returns None when no such directory
  exists: nothing scanned is not the same answer as clean.
- **`identifier_findings()`**, the tracked-tree walk, now opens tracked
  archives instead of skipping every `.tgz` by suffix. Findings are reported as
  `<archive>!<member>`.

`oneground/test_environment.py`, six synthetic tests:
- a named non-zero owner is caught;
- a numeric-owner archive is clean, and so is `root`;
- a home path in the gzip FNAME is caught (the header written by hand, because
  `gzip.GzipFile` stores only a basename), and so is one in a text member, at
  its line;
- an unreadable archive is reported;
- the asset scan says None with nothing to scan, and finds a leak where there
  is one;
- the tracked walk opens a tracked archive.

Plus one real test:
**`test_no_release_asset_archive_carries_owner_metadata`** scans this machine's
asset directory, and skips with the directory named where there is none.

**It catches the leak it was built for.** Run before the swap, against the
original `stackexchange-150k-v1.tgz` still in `~/oneground-assets/`, the real
test failed with six findings: `owner id uid 197609 gid 197609` and `owner
name` for each of the three members. After the swap it passes.

### 4. The digests, where they are recorded

- `RELEASE_NOTES.md`, *The release assets*: new sizes and sha256 values, and a
  sentence on how they were packed.
- `oneground/fixture/verify.py`, `RELEASE_ASSETS`: the new sizes, which
  `fixture verify` prints to a reader whose asset is missing. A test already
  holds this table equal to the release notes.
- `oneground/fixture/test_verify.py`: the one test that quoted the arXiv size
  now reads it from `RELEASE_ASSETS`.

Earlier task reports (018, 018d, 022) and `docs/VERIFY.md` quote the old
digests and sizes as what was measured at the time. They are records and are
not rewritten.

## Measurements

**The new release assets:**

```
arxiv-150k-v1.tgz
  483,467,899 bytes   (was 483,468,013)
  sha256  437ac5db45cdb2c1c8cc21707816d508981327a0152d86283151be032d3310f2
          (was 0b7a0209fa4085683950e4715d49597c820cadc575b4a4fe85ef2d4f5365c015)

stackexchange-150k-v1.tgz
  460,106,909 bytes   (was 460,106,978)
  sha256  2871c61333bbe80adf124ff64ff15831ebd593f24bf180a3ae71edf72054484e
          (was 5d2a2be15c2c062e8b0f1ca9c24520c9e326e7d580ab411fcdbb71459181a66a)
```

The full repack logs, the original's members and the repacked archive's
members each hashed from inside the archive:

```
=== arxiv-150k-v1.tgz
--- the original
  483468013 bytes
  sha256 0b7a0209fa4085683950e4715d49597c820cadc575b4a4fe85ef2d4f5365c015 *arxiv-150k-v1.tgz
--- the original's members against fixtures/arxiv-150k/MANIFEST.sha256 (streamed from the archive)
  fixtures/arxiv-150k/vectors.npy               460,800,128  141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa  matches
  fixtures/arxiv-150k/queries.npy                 6,144,128  dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b  matches
  fixtures/arxiv-150k/sample.jsonl.zst           49,920,799  404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655  matches
  all members match the manifest
--- extract, then repack with no user metadata
  $ tar --format=ustar --owner=0 --group=0 --numeric-owner -cf - \
        fixtures/arxiv-150k/vectors.npy fixtures/arxiv-150k/queries.npy fixtures/arxiv-150k/sample.jsonl.zst \
      | gzip -n > arxiv-150k-v1.tgz
--- the repacked archive's headers
== <scratch>/022b2/out/arxiv-150k-v1.tgz
  gzip: flags 0x0  mtime 0 (none)  os 3  fname None  fcomment None  extra None
  fixtures/arxiv-150k/vectors.npy
      type b'0' size 460,800,128 mode 0o644 mtime 1788953141
      uid 0 gid 0 uname '' gname ''
  fixtures/arxiv-150k/queries.npy
      type b'0' size 6,144,128 mode 0o644 mtime 1788953141
      uid 0 gid 0 uname '' gname ''
  fixtures/arxiv-150k/sample.jsonl.zst
      type b'0' size 49,920,799 mode 0o644 mtime 1788952392
      uid 0 gid 0 uname '' gname ''
  tar format guess: 2 (0 ustar, 1 gnu, 2 pax)
--- the repacked archive's members against fixtures/arxiv-150k/MANIFEST.sha256 (streamed from the archive)
  fixtures/arxiv-150k/vectors.npy               460,800,128  141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa  matches
  fixtures/arxiv-150k/queries.npy                 6,144,128  dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b  matches
  fixtures/arxiv-150k/sample.jsonl.zst           49,920,799  404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655  matches
  all members match the manifest
--- the repacked archive
  483467899 bytes
  sha256 437ac5db45cdb2c1c8cc21707816d508981327a0152d86283151be032d3310f2 *arxiv-150k-v1.tgz
--- GNU tar lists it
  -rw-r--r-- 0/0       460800128 2026-09-09 13:25 fixtures/arxiv-150k/vectors.npy
  -rw-r--r-- 0/0         6144128 2026-09-09 13:25 fixtures/arxiv-150k/queries.npy
  -rw-r--r-- 0/0        49920799 2026-09-09 13:13 fixtures/arxiv-150k/sample.jsonl.zst
```

```
=== stackexchange-150k-v1.tgz
--- the original
  460106978 bytes
  sha256 5d2a2be15c2c062e8b0f1ca9c24520c9e326e7d580ab411fcdbb71459181a66a *stackexchange-150k-v1.tgz
--- the original's members against fixtures/stackexchange-150k/MANIFEST.sha256 (streamed from the archive)
  fixtures/stackexchange-150k/vectors.npy       460,800,128  067d8ffbdf16f08f0a43e3fa1fccb3ca4a62093cd8f00069038f7d88bee17f30  matches
  fixtures/stackexchange-150k/queries.npy         6,144,128  465a37757bd7dd1daef7ac2bf9a62a9c32deb8d32e907493cc75c22e4ac76b54  matches
  fixtures/stackexchange-150k/sample.jsonl.zst   26,813,350  2ab675cc3c20a0ff97602c26d070c24d307a97a4f69529ea37d7fd145c74ef0e  matches
  all members match the manifest
--- extract, then repack with no user metadata
  $ tar --format=ustar --owner=0 --group=0 --numeric-owner -cf - \
        fixtures/stackexchange-150k/vectors.npy fixtures/stackexchange-150k/queries.npy fixtures/stackexchange-150k/sample.jsonl.zst \
      | gzip -n > stackexchange-150k-v1.tgz
--- the repacked archive's headers
== <scratch>/022b2/out/stackexchange-150k-v1.tgz
  gzip: flags 0x0  mtime 0 (none)  os 3  fname None  fcomment None  extra None
  fixtures/stackexchange-150k/vectors.npy
      type b'0' size 460,800,128 mode 0o644 mtime 1789330058
      uid 0 gid 0 uname '' gname ''
  fixtures/stackexchange-150k/queries.npy
      type b'0' size 6,144,128 mode 0o644 mtime 1789330058
      uid 0 gid 0 uname '' gname ''
  fixtures/stackexchange-150k/sample.jsonl.zst
      type b'0' size 26,813,350 mode 0o644 mtime 1789330059
      uid 0 gid 0 uname '' gname ''
  tar format guess: 2 (0 ustar, 1 gnu, 2 pax)
--- the repacked archive's members against fixtures/stackexchange-150k/MANIFEST.sha256 (streamed from the archive)
  fixtures/stackexchange-150k/vectors.npy       460,800,128  067d8ffbdf16f08f0a43e3fa1fccb3ca4a62093cd8f00069038f7d88bee17f30  matches
  fixtures/stackexchange-150k/queries.npy         6,144,128  465a37757bd7dd1daef7ac2bf9a62a9c32deb8d32e907493cc75c22e4ac76b54  matches
  fixtures/stackexchange-150k/sample.jsonl.zst   26,813,350  2ab675cc3c20a0ff97602c26d070c24d307a97a4f69529ea37d7fd145c74ef0e  matches
  all members match the manifest
--- the repacked archive
  460106909 bytes
  sha256 2871c61333bbe80adf124ff64ff15831ebd593f24bf180a3ae71edf72054484e *stackexchange-150k-v1.tgz
--- GNU tar lists it
  -rw-r--r-- 0/0       460800128 2026-09-13 22:07 fixtures/stackexchange-150k/vectors.npy
  -rw-r--r-- 0/0         6144128 2026-09-13 22:07 fixtures/stackexchange-150k/queries.npy
  -rw-r--r-- 0/0        26813350 2026-09-13 22:07 fixtures/stackexchange-150k/sample.jsonl.zst
```

**The extended scan:**
- on the two repacked archives: 0 findings each;
- over the tracked tree, archives opened: 0 findings;
- over `~/oneground-assets` after the swap: 0 findings.

**Full suite:** **819 passed, 0 failed, 0 skipped** (9 m 04 s): the 812 of `713b9b2` plus the seven new archive tests. The live RunPod plan test passed on this run.

**Other checks:** leak scan, the one known synthetic `DESKTOP-` probe in
`oneground/test_environment.py`; `tasks/scratch/018-docs-numbers.py`: ALL CHECKS PASSED.

## Verification

- Both tarballs repacked with `--owner=0 --group=0 --numeric-owner` and no user
  metadata: done, and headers dumped to show it.
- Each member's sha256 checked against its fixture manifest after repacking:
  all six match, read from inside the new archives.
- New whole-file digests recorded for the release notes: done.
- The arXiv tarball checked for the same leak: it had none (uid 0, `root`),
  and was repacked anyway so both carry empty owner names.
- The identifier scan looks inside `.tgz`/`.tar.gz` under the assets
  directory, and inside tracked archives: done. Its real test failed on the
  leaky original, and passes on the repacked file.

**Couldn't-check:**
- **The published release assets on GitHub.** Nothing was uploaded; that is
  the developer's. Whether the `v0.1.0-preview` release (or anywhere else)
  already carries the leaky `stackexchange-150k-v1.tgz` was not checked from
  here. If it does, replacing the local file does not unpublish it.
- **A fresh extraction and full `fixture verify` of the repacked tarballs.**
  Not re-run. The members are byte-identical by sha256, and the value
  recomputation reads the members, not the headers.

## Observed, not done

- **The repacked archives are not bit-reproducible:** a repack on another
  machine or a different gzip would give other whole-file digests for the same
  members. What is stable is the member digests in the manifests. A
  `--sort=name --mtime=… ` recipe with a pinned gzip level would make the
  tarball itself a receipt.
- `arxiv-150k-large.tgz` is a duplicate of the old arXiv tarball under a name
  no document uses. It is clean by the scan's rule (`root`, uid 0). It could be
  removed.
- The superseded originals are in `~/oneground-assets-superseded/` and can be
  deleted once the release is published from the new ones.

## Repo now contains

Changed:

    oneground/environment.py           archive_findings, asset_archive_findings; tracked archives opened
    oneground/test_environment.py      6 synthetic tests, 1 real one
    oneground/fixture/verify.py        RELEASE_ASSETS sizes
    oneground/fixture/test_verify.py   the arXiv size read from RELEASE_ASSETS
    RELEASE_NOTES.md                   new sizes and digests; how they were packed

New:

    tasks/022b-release-tarballs-without-owner.report.md

Outside the repository:

    ~/oneground-assets/arxiv-150k-v1.tgz            repacked
    ~/oneground-assets/stackexchange-150k-v1.tgz    repacked
    ~/oneground-assets-superseded/                  the two originals, kept

## Blocked on developer

1. **Upload the two repacked tarballs** from `~/oneground-assets/` as the
   release assets, replacing any copy of `stackexchange-150k-v1.tgz` already
   published. Their digests are above and in `RELEASE_NOTES.md`.
2. **Push `main` and retag `v0.1.0` at this commit** (the one whose subject
   begins `task 022b:`), then rebuild the artifacts and re-run the fresh-venv
   check.
