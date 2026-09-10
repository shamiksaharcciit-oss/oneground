# Pod setup — canonical arxiv-150k build

## Using `oneground pod` (start here)

Since task 006 a pod session is one command, driven by the build agent:

    python -m oneground.pod plan sessions/arxiv-build.yaml   # dry run, priced
    python -m oneground.pod up   sessions/arxiv-build.yaml   # asks before spending
    python -m oneground.pod watch <id>                       # DONE -> fetch -> terminate

`sessions/smoke.yaml` is the same path over the 2,000-document smoke fixture,
for a few cents — run that first after any change to `oneground/pod/`.

**Read `docs/POD.md`** for how sessions work, where the money boundary sits
(the agent may plan, monitor, fetch and terminate; only a typed `y` creates
anything), what the caps do, and how to recover an orphaned pod.

The helper does steps 1–9 and step 12's download. It does **not** do the Kaggle
credentials in step 7, which stay a developer action.

## The manual path (fallback)

Everything below is the by-hand version, kept as the reference and for when the
helper cannot be used. It is what produced builds 1–3.

Developer runs. RunPod pod with the `vecbench` network volume mounted at
`/workspace`. Python 3.12.

Steps in order.

## 1. Bundle the repo (on the laptop)

    git bundle create oneground.bundle --all

A bundle carries the full history in one file and needs no GitHub credentials
on the pod.

## 2. Upload the bundle

Upload `oneground.bundle` to `/workspace` on the pod (RunPod's file browser,
or `scp` to the pod's SSH endpoint).

## 3. Clone on the pod

    cd /workspace
    git clone oneground.bundle oneground
    cd oneground
    git checkout master

## 4. Virtualenv — on local disk, not the network volume

Build the venv on the pod's **container disk** at `/root/.venv` and symlink it
into the repo. `/workspace` is the network volume: populating a venv there took
roughly **30 minutes** because `pip install` writes tens of thousands of small
files and every one is a round trip. On local disk the same install is minutes.

    python3.12 -m venv --copies /root/.venv
    ln -sfn /root/.venv /workspace/oneground/.venv
    . /root/.venv/bin/activate
    python -m pip install --upgrade pip

`--copies` matters: without it the venv's interpreter is itself a symlink, and
a symlink chain that crosses onto the network mount gives back part of what
moving off it was meant to save.

The trade-off is deliberate. The container disk does not survive termination,
so the venv is rebuilt on every session — a few minutes each time, against
thirty saved. Nothing that must outlive the pod goes there: the artifacts are
written under `/workspace`, which is the volume, and that is what the release
asset is downloaded from.

`oneground pod up` runs exactly these steps for you (`oneground/pod/cli.py`,
`_setup_script`), so a session started with the helper needs none of this
section by hand.

## 5. Dependencies

    pip install -r requirements.txt

These are the versions every measurement so far was produced with. Do not
resolve them freshly — `build_info.json` records what actually ran, and the
orchestrator compares it against this file.

## 6. Kaggle client

    pip install kaggle

## 7. Kaggle credentials

Create `~/.kaggle/kaggle.json` containing the API token from
kaggle.com → Account → Create New API Token:

    mkdir -p ~/.kaggle
    # paste the token file, then:
    chmod 600 ~/.kaggle/kaggle.json

## 8. Download the dataset

    kaggle datasets download -d Cornell-University/arxiv -p /workspace --unzip

This leaves `/workspace/arxiv-metadata-oai-snapshot.json` (~4 GB unzipped).
The run script hashes it and prints the sha256 — that value is the spec's
`source.snapshot_sha256`.

## 9. Run the build

    cd /workspace/oneground
    mkdir -p logs
    nohup bash corpora/run_arxiv_150k.sh > logs/run.log 2>&1 &
    tail -f logs/run.log

Run it with **no environment variables set**. The `SPEC`, `SOURCE`, `TARBALL`
and `SKIP_PROJECTION` variables in the script exist only so its logic could be
tested on the smoke fixture; their defaults are the canonical build.

The last two lines on success are:

    DONE
    /workspace/arxiv-150k-small.tgz

## 10. Expected wall clock

Roughly **2–3 hours**. Basis: the smoke build embedded 2,000 documents in
566 s on a 4-vCPU laptop with torch on 2 threads (3.53 docs/s). Extrapolated
linearly, 150,000 documents is ~11.8 h at that rate; 16 vCPU should give
roughly 4x, so ~3 h for embedding, plus exact ground truth, characterization
and UMAP.

Embedding is ~86% of the smoke run and dominates here too. The least
predictable step is the UMAP projection over 150,000 x 768 — it was never run
at this size, so treat the upper end as soft. If the log sits on
`UMAP projection` for more than an hour, that is worth reporting, not worth
killing on its own.

## 11. Memory guard

The pod has 40 GB and the build should stay well under it. Watch anyway:

    watch -n 30 free -g

**If free RAM drops below 2 GB during embedding, stop the run and report.**
Do not let it swap — a swapping build produces the same numbers far slower, or
gets OOM-killed halfway and leaves a partial fixture directory.

To stop: `pkill -f build_fixture.py`, then report the last 40 lines of
`logs/build-arxiv-150k.log`.

## 12. When it finishes

1. Download `/workspace/arxiv-150k-small.tgz` into the local repo.
2. Terminate the pod. **Keep the `vecbench` volume** — it holds
   `vectors.npy`, `queries.npy` and `sample.jsonl.zst` for the release asset.
   Those are deliberately not in the tarball.
3. Send the orchestrator: the `TO_BE_FILLED` block from the log, the last 40
   lines of `logs/build-arxiv-150k.log`, and the `source.snapshot_sha256`
   printed near the top of the run.

Task 003 publishes those values and flips `status: built`. Do not edit the
spec's `TO_BE_FILLED` fields by hand.

## Build 3 — the reproducibility build

Build 3 repeats build 2 in the same pinned environment and adds nothing to the
measurement. Its purpose is that the builder now records torch (task 003c), so
build 3's `build_info.json` carries the version and CUDA device that build 2's
spec fields only declare. It is also the first run that produces the ground
view and the release asset.

The one thing that must not be repeated from build 1: **do not create the venv
with `--system-site-packages`.** That is how build 1 inherited the pod
template's numpy 2.1.2 instead of the pinned 2.5.3, and why builds 1 and 2
differ.

    cd /workspace/oneground
    python3.12 -m venv --copies /root/.venv    # no --system-site-packages,
    ln -sfn /root/.venv .venv                  # and on local disk (step 4)
    . .venv/bin/activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt

Check the pins took before spending an hour on a build that will not count:

    python -c "import numpy, torch, faiss, sentence_transformers, umap; print(numpy.__version__, torch.__version__, torch.version.cuda, torch.cuda.is_available())"

Expect `2.5.3` for numpy and a `+cuXXX` suffix on torch with
`torch.cuda.is_available()` True on a GPU pod. A bare `2.14.0` with `None`
means the CPU wheel was installed and the build would run on CPU.

Then the same one command as before:

    mkdir -p logs
    nohup bash corpora/run_arxiv_150k.sh > logs/run.log 2>&1 &
    tail -f logs/run.log

Build 3 produces **two** tarballs, and the last three lines on success are:

    DONE
    /workspace/arxiv-150k-small.tgz
    /workspace/arxiv-150k-large.tgz

`arxiv-150k-small.tgz` is the review bundle, now also carrying the three
`ground_view_*.parquet` tables the hero image is drawn from.
`arxiv-150k-large.tgz` is the release asset: `vectors.npy`, `queries.npy` and
`sample.jsonl.zst`, the artifacts a clone reports as couldn't-check. Download
both; keep the volume until the release asset is uploaded.

The run now also exports the ground view, which recomputes the fixture's
geometry and asserts it against the spec's published values. If those
assertions fail the run exits non-zero after the verifier has already passed —
that is a real disagreement between the picture and the numbers, and it should
be reported, not worked around.

## Troubleshooting

**`bad interpreter: /usr/bin/env bash^M`** — the script reached the pod with
Windows line endings (this happens if the working tree was copied directly
instead of cloned from the bundle). Fix:

    sed -i 's/\r$//' corpora/run_arxiv_150k.sh

**`ERROR: source not found`** — step 8 did not complete, or unzipped to a
different name. Check `ls -la /workspace/*.json`.

**`ERROR: no virtualenv`** — run the script from the repo root with `.venv`
present; it looks for `.venv/bin/activate`.
