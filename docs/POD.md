# Pod sessions

How `oneground pod` works, where the money boundary is, what the caps do, and
how to recover a pod nobody is watching.

Heavy jobs — the canonical fixture builds — run on a RunPod GPU pod, usually
with the network volume mounted at `/workspace` (see `volume: none` below for
the sessions that need no volume at all). Before task 006 every session was the
developer pasting the twelve steps in `corpora/POD_SETUP.md` into a browser
terminal. `oneground pod` makes a session one command driven by the build
agent, without moving the decision about spending money.

The same code is what `verify.target: runpod` drives — task 011 — which is why
it is package code under `oneground/pod/` and not a script in `corpora/`.

---

## The money boundary

**The agent may prepare, dry-run, monitor, fetch and terminate. Only the
developer's typed `y` creates a billable resource — and the number they are
shown is the worst case, not the best.**

| subcommand | what it does | can it spend? |
|---|---|---|
| `plan <spec>` | resolve a session to a concrete, **range-priced** plan | no |
| `up <spec>` | prompt, deploy, **verify the true price**, sync, launch | **yes, after `y`** |
| `status [<id>]` | state, elapsed, cost so far, last log lines | no |
| `fetch <id>` | download the declared outputs | no |
| `down <id>` | terminate | no — it *saves* money |
| `watch <id>` | poll → DONE, cap, or **stall** → fetch → terminate | no |
| `ls` | every oneground pod, orphans flagged | no |

That boundary is enforced in three independent places, so no single mistake
crosses it:

1. **`api.RunPodClient` refuses billable endpoints.** `api.BILLABLE` lists the
   `(method, path)` pairs that can start or resume charging. Any of them raises
   `CreateCallBlocked` unless the client holds a confirmation token. The guard
   runs *before* the transport, so a blocked call makes no network request at
   all — it is not a request that failed, it is a request that never happened.
2. **The token can only come from a human.** `confirm.ask_to_create()` is the
   only code in the package that reads stdin, and the only thing that can
   construct a `CreateAuthorization`. It refuses when stdin is not a TTY.
3. **The CLI never unlocks a client except in `up`.** Every other subcommand
   builds a plain client. `test_pod.py` drives each of them against a recording
   transport and asserts the recording contains no billable call.

`DELETE /pods/{id}` is deliberately *not* on the billable list. Terminating
only ever stops the meter, which is why `down` asks nothing — a confirmation
prompt on the one action that always helps would train the developer to press
`y` without reading.

`POST /pods/{id}/start` and `/restart` **are** billable: resuming a stopped pod
resumes charging, and that is as much a spend as creating one.

### Why there is no `--yes`

There is no non-interactive create path, and adding one is a design change
rather than a convenience flag.

A `--yes` would delete the whole property in one word, and it would be added
for exactly the situation in which it is least safe: an unattended agent loop
that has decided, on its own, to spend money. The value of the boundary is that
it cannot be argued around at 2am by a process with no budget of its own.

Note the asymmetry, which is the actual design: the unattended path this
project needs is the *back* half of a session, not the front. `watch` polls a
pod a human already paid for and terminates it at the cap. Creation stays a
keystroke; teardown, which only ever saves money, is automatic.

If headless creation is ever genuinely needed, the right shape is a short-lived
authorization minted by the developer with its own cap and expiry — not a
boolean.

### The price you confirm is the worst case

A confirmation is only as good as the number in it. `plan` therefore quotes a
**range** and everything downstream — the prompt, the cap arithmetic, the
budget — uses the **top** of it:

```
price      : $0.34 - $0.72/hr   (live on-demand range, SECURE, EU-RO-1)
             confirmed at the TOP of the range, $0.72/hr
COST CAP   : 1 h x up to $0.72/hr = up to $0.72   within max_usd
```

and the prompt reads:

```
Create this pod at up to $0.72/hr (range $0.34-$0.72) with a hard cap of
1 hours = up to $0.72? [y/N]
```

The bottom of the range is `lowestPrice`, a floor across configurations. It is
used for availability, stock and the range's lower bound — it is the only
datacenter-scoped price the API offers — but it is **never** what anyone
confirms against. The top is the list price of the cloud actually being bought
(`securePrice` for SECURE, `communityPrice` for COMMUNITY).

The distinction is not academic. For RTX PRO 4500 the floor is **$0.34**, which
is its *community* price — and its `communityCloud` flag is **false**. The
floor was the price of a machine the account could not have been given. The
secure price is **$0.72**, and $0.72 is what task 006b was billed.

**If the worst case cannot be determined, the price is `couldn't-check` and
`up` refuses.** It never falls back to the floor: a floor presented as a price
is worse than no price, because it reads like an answer.

### The true price is verified after create

The range is a quote. The pod is the fact. Immediately after `POST /pods`,
`up` reads the pod's own `costPerHr` and compares it against what was
confirmed:

- within tolerance (default **5%**, `--price-tolerance`) → proceed, and record
  the true rate in the session file;
- above it → **terminate immediately**, print both numbers, exit non-zero;
- absent → terminate. An unpriced pod cannot be held against a cap.

`status` and `watch` cost against that recorded true rate, never against the
quote. Before it is known they fall back to the confirmed worst case, so the
estimate errs high rather than low.

### `max_usd` is enforced twice

Once **before** the pod exists — `max_hours × confirmed worst case` must fit
inside `max_usd`, or `up` refuses without asking anything — and again
**during** `watch`, as `elapsed × true rate`, which terminates at the cap.

In task 006b only the hours bound existed, so a pod at 2.1× the confirmed rate
stayed inside its dollar cap by arithmetic accident rather than by design.

### The watchdogs: a pod with nothing to wait for must not survive

Two, because a run can fail to start and it can also stop:

- **No-run** (`up`, `--log-timeout`, default **180 s**): after launching, poll
  for the run's log to appear. If it never does, the launch failed — terminate
  and exit non-zero.
- **Stall** (`watch`, `stall_minutes` per session, default **15**): if the log
  has not *grown* for that long, terminate and report a stall. Only growth
  resets the clock; an unreadable log does not, or an SSH outage would keep a
  dead pod alive indefinitely.

Set `stall_minutes` above the longest legitimate quiet period a session has.
`sessions/arxiv-build.yaml` uses 20, covering the `pip install` phase.

---

## Sessions

A session spec is a small YAML file under `sessions/`. The committed example is
`sessions/arxiv-build.yaml`, which is the canonical arxiv-150k build.

```yaml
gpu: ["RTX PRO 4500", "RTX PRO 6000"]   # display names, first available wins
volume: vecbench                        # by name; datacenter DERIVED from it
image: runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404
disk_gb: 20
env: {HF_HOME: /workspace/hf}
setup: corpora/POD_SETUP.md
run: bash corpora/run_arxiv_150k.sh
stall_minutes: 20                       # watch terminates if the log stalls
outputs:
  - {remote: /workspace/arxiv-150k-small.tgz, local: ./, extract: true}
  - {remote: /workspace/arxiv-150k-large.tgz, local: ../oneground-assets/}
caps: {max_hours: 1.0, max_concurrent: 1, max_usd: 1.50}
```

**The datacenter is never written down.** It is derived from the volume's
record, because a network volume can only be attached by a pod in its own
datacenter, and a spec that states the region twice is a spec that can state it
inconsistently. `plan` resolves the volume first, then asks for prices *in that
datacenter only* — a GPU type that exists globally may be unavailable there,
and its global price would be a fiction.

`gpu` is a preference list, tried in order; the first type actually offered in
that datacenter wins. `plan` prints the whole list with what each resolved to,
so an unavailable first choice is visible rather than silent.

### `volume: none` — when the region is chosen instead of derived

`volume:` is required, and it decides how the datacenter is picked. Naming a
volume derives the region from it, as above. `none` says this session needs no
network volume:

```yaml
gpu: ["RTX PRO 4500", "RTX 6000 Ada", "RTX 4090", "L4", "A40"]
volume: none                     # no network volume; region chosen by stock
volume_mount_path: /workspace    # an ordinary directory on the container disk
disk_gb: 60                      # everything the run writes lives here
```

|  | `volume: <name>` | `volume: none` |
|---|---|---|
| datacenter | **derived** from the volume | **chosen** by GPU availability |
| `volume_mount_path` | the mount | a directory on the container disk |
| survives the pod | yes | **no** |
| `disk_gb` sizes | the venv | the venv *and* everything the run writes |

The choosing rule is **the cheapest listed datacenter offering the first
available GPU in the list**. Preference order is honoured first — a cheap
region for a card the session did not ask for is a different answer, not a
better one — and only then does price choose between the regions offering that
card. Ties break on datacenter id, so two `plan` runs cannot silently move the
pod. Unlisted datacenters are skipped; the volume-derived path never consults
that list at all, so a session pinned to a volume keeps working in a region
that has stopped taking new pods.

One asymmetry to know before reading a price: `securePrice` — the number this
project confirms against — is reported **globally**, not per datacenter. Only
the `lowestPrice` floor varies by region. So "cheapest datacenter" is decided
on the floor, while the confirmed rate is the same everywhere, and `plan` says
so rather than implying a saving that is not there.

```
  volume     : none   (nothing outlives the pod)
  datacenter : US-WA-1   (chosen by GPU availability, 33 searched)
               cheapest of 1 offering RTX 6000 Ada, at $0.84/hr
  disk       : 60 GB container disk; /workspace is on it, not a volume

  datacenters offering RTX 6000 Ada, cheapest first:
    US-WA-1     $0.74 - $0.84/hr   stock Low   <- chosen
```

**Use it when nothing needs to outlive the pod.** The stackexchange-150k build
streams its 34 GB source instead of storing it and returns both outputs as
tarballs, so it holds nothing worth keeping — and pinning it to a volume would
have pinned it to that region's stock. That is not hypothetical: `up` was
refused in EU-RO-1, where `vecbench` lives, because the only cards on offer
there were an over-cap B200 and an AMD MI300X our CUDA build cannot use.

**Do not use it for anything you would mind losing.** The container disk dies
with the pod. `arxiv-150k` still names `vecbench`, because its 4 GB source
snapshot lives there and re-uploading it by hand is the thing the volume
exists to avoid.

### When a create is refused for want of capacity

`up` confirms a **rate**, not a card — the prompt names a price and a total and
no GPU. So when RunPod answers a create with *"there are no instances currently
available"*, `up` moves to the next `(datacenter, GPU)` from the plan and tries
again **without re-prompting**, as long as that candidate's confirmed worst
case is at or under the rate already agreed. Each attempt is logged. A dearer
candidate is never tried silently: it is reported as skipped, and the run ends
telling you what a second `y` would buy.

Only that one refusal is retried. Any other failed create may have produced a
pod whose id this process never saw, and retrying it could put two pods behind
one `y`, so those are raised rather than worked around. The session record
names the card that actually exists, with `planned_gpu` set when it differs
from the plan's first choice.

### Waiting for sshd

`RUNNING` is the *container's* state, not sshd's. Before the first command that
matters, `up` probes with `ssh … true`, retried with backoff for up to 180 s
(`--ssh-ready-timeout`), logging each attempt; the probe is allowed to fail, so
a few seconds of "connection refused" costs nothing. A pod that never becomes
reachable is terminated with `finished_because: ssh-never-ready`. How long it
actually took is recorded as `ssh_ready` in the session file, and any SSH
failure now records the full command it was running rather than the first three
words of the argv.

### What `plan` prints

`plan` is the dry run, and it is the *same code path* `up` uses to decide what
to deploy — so what the developer confirms is what gets built, not a summary of
it. `plan --payload` prints the exact `POST /pods` body.

```
  volume     : vecbench
  datacenter : EU-RO-1   (derived from the volume, not the spec)
  gpu        : RTX PRO 4500   [NVIDIA RTX PRO 4500 Blackwell]
               stock Low
  price      : $0.34 - $0.72/hr   (live on-demand range, SECURE, EU-RO-1)
               confirmed at the TOP of the range, $0.72/hr
  caps       : max_hours 1, max_usd $1.50, max_concurrent 1
  COST CAP   : 1 h x up to $0.72/hr = up to $0.72   within max_usd
  stall      : terminate if the log has not grown for 20 min
  considered : RTX PRO 4500=$0.34-$0.72/Low  RTX 6000 Ada=unavailable
```

---

## The caps

Caps are enforced **client-side, and they are the only limit there is.** RunPod
has no server-side spend ceiling behind this: a pod runs until it is
terminated or the account is empty. That is why `session.load()` refuses a spec
with no `caps` rather than treating a missing cap as unlimited.

| cap | enforced where | what it does |
|---|---|---|
| `max_usd` | `up` before the prompt, **and `watch` during the run** | refuses if `max_hours × confirmed max` exceeds it; terminates when `elapsed × true rate` reaches it |
| `max_hours` | `watch` | terminates the pod at that age, run finished or not |
| `max_concurrent` | `up`, before the prompt | refuses if that many sessions are already live |
| `stall_minutes` | `watch` | terminates if the run's log stops growing |
| `--log-timeout` | `up` | terminates if the run's log never appears at all |

`max_usd` is checked against the **worst case**, not the expected case: the
full `max_hours` at the **top** of the live price range. A plan that only fits
inside its budget if the build finishes early — or if the cheapest machine
happens to be allocated — is a plan that is over budget.

`status` reports two different cost numbers and does not blur them:

- **cost so far** — elapsed × the pod's **true** rate, once verified after
  create; before that, × the confirmed worst case, so it errs high. An
  estimate, available immediately, and the number the spend cap uses.
- **billed** — `GET /billing/pods`. The real figure, and it lags — it returned
  no rows at all for either of task 006b's pods, hours after termination.

---

## What a session actually does

`up`, after the `y`:

1. `POST /pods` with the resolved plan **and the image named by digest** (see
   below), then poll to `RUNNING` with an SSH mapping.
2. Wait for sshd to answer, then `git bundle create --all`, `scp` it over,
   clone it on the pod.
3. Upload the session's declared inputs.
4. Run the setup script. On the pre-baked image that **symlinks**
   `/opt/oneground-venv` rather than building a venv and running
   `pip install`; on any other image it builds one at `/root/.venv` on local
   disk (see below). Either way it prints which venv it got.
5. Launch the run under `setsid nohup`, stdout to
   `/workspace/oneground-session.log`.
6. Write `.oneground/sessions/<id>.json` (git-ignored) and stop.

Then `watch <id>` polls until the run prints `DONE` or the cap is hit, fetches
the declared outputs, and terminates.

### The image, and why it is a digest

Sessions run a **pre-baked image**, built by
[`docker/pod/Dockerfile`](../docker/pod/Dockerfile) on the same RunPod base:
the pinned dependencies in a venv at `/opt/oneground-venv`, the Qdrant release
binary, PostgreSQL + pgvector at the pins `run_verify_pod.sh` uses, and a
marker at `/opt/oneground-image/BAKED` carrying the versions — so a session
records *which* image it ran on rather than what apt happened to serve. It
carries **no repo**: the bundle still syncs, because a session exists to run
the commit under test. Full description in
[POD_IMAGE.md](POD_IMAGE.md).

It exists because task 015 lost six environment faults across five billed
sessions, every one of them setup rather than work. Doing that setup once, in
CI, costs a CI minute instead of a pod.

**Referenced by digest, never by a tag.** `docker/pod/IMAGE.lock` holds the
digest and `oneground/pod/image.py` reads it. A tag is a name that can be
moved, and two sessions naming one can run different bytes with nothing in
either receipt saying so. The rule worth stating on its own:

> **A missing digest is never a reason to fall back to a tag.** `reference()`
> raises, and `verify` refuses before anything is created. A session that
> silently ran different bytes than it recorded is worse than a session that
> did not start, and it is invisible in exactly the way the lock exists to
> prevent.

The documented escape hatch is explicit and one line — `verify.image` in the
session's requirements — and it then appears in the receipt as something a
person chose.

### The build is not reproducible, and the lock is checked accordingly

Task 017b rebuilt the same Dockerfile from the same `requirements.txt`,
uncached, and got a different digest: `12bd6a3e` against the locked
`81567d58`. The base resolved identically both times, so it was not the base
moving — apt and pip do not promise byte-identical responses over time, and
layer metadata carries timestamps regardless. **Both images are valid.**

So CI does not rebuild and compare, which is a check that cannot pass in a
steady state. It asks two different questions instead:

| check | what it answers |
|---|---|
| **pullable** | does the registry still serve the digest the lock names? The only question whose answer changes what a session does. |
| **co-change** | if a commit touched the image's build inputs, did the lock change in the same range? One-directional: re-locking without touching the recipe is fine, because a rebuild against an unchanged recipe produces a new and equally valid digest. |

The build inputs are **derived from the Dockerfile** — the file itself plus
every path it `COPY`s or `ADD`s from the context — rather than declared, so
the trigger set cannot drift from what the build actually reads.
`docker/pod/rebuild.sh` is what rebuilds, pushes, reads back the digest the
*registry* assigned, and rewrites the lock in place.

### The setup split

A session record carries `phase_times`, and `pod status` prints the gaps
between them:

    RunPod provisioning: create to RUNNING
    waiting for sshd
    repo sync: bundle, scp, clone on the pod
    uploading the session's declared inputs
    setup script (venv built, or symlinked from the image)
    starting the run

It exists so "the baked image saved five minutes" is a measurement rather than
an impression. A session recorded before task 017f has **no** split rather
than a fabricated one: deriving a breakdown from `created_at` would be exactly
the quoted boundary three reports declined to give.

### Why SSH, not `runpodctl`

Four reasons, and the first two are decisive:

1. `runpodctl` is not installed on the developer's machine, so choosing it
   would add a binary dependency to a project that pins everything.
2. `runpodctl send`/`receive` is a one-shot peer-to-peer transfer keyed by a
   short code a human reads off one terminal and types into another. Fine for a
   person moving one file; unusable for `watch`, which is by definition the
   unattended path.
3. Three of the four things a session needs are not transfers at all —
   launching under `nohup`, tailing the log, polling for `DONE`. Those need a
   shell either way, **and RunPod's REST API has no pod-log endpoint** (its
   OpenAPI document lists 23 paths; none of them is logs). So SSH is required
   regardless, and adding `runpodctl` would mean two channels where one does.
4. `ssh`/`scp` are present, and the developer already has an ed25519 key.

The repo reaches the pod as a **git bundle**, exactly as `POD_SETUP.md` has
done by hand since task 002: one file, no credentials on the pod, and it
carries history rather than a working-tree copy — which is also what keeps
`run_arxiv_150k.sh` at LF (task 002's CRLF trap).

> **A bundle carries commits, not the working tree.** Anything uncommitted does
> not reach the pod. `up` prints a warning listing the dirty paths rather than
> shipping something older than what the developer is looking at.

### The venv is on local disk — when one has to be built at all

On the pre-baked image there is nothing to build: setup symlinks
`/opt/oneground-venv`, and the `pip install` step that cost about five minutes
of billed time per session does not run.

On any other image, setup builds the venv at `/root/.venv` — container disk —
and symlinks it to `<repo>/.venv`. Populating a venv on the network volume took
roughly **30 minutes**, because `pip install` writes tens of thousands of small
files and each one is a round trip; on local disk it is minutes. `--copies`
matters, or the interpreter itself stays a symlink onto the mount.

The container disk does not survive termination, so the venv is rebuilt every
session. Nothing that must outlive the pod goes there — artifacts are written
under `/workspace`, which is the volume.

Under `volume: none` that last sentence does not hold: `/workspace` *is* the
container disk, so nothing written there survives either, and `disk_gb` has to
be big enough for the whole run. Such a session must return everything it
produces as declared `outputs`, which `watch` fetches before it terminates.

---

## Labels, and recovering an orphan

**RunPod has no label primitive.** Its `POST /pods` schema has no
`labels`/`tags` field, so the session label is carried twice:

- the pod **name**: `oneground-session-<id>` — what a human sees in the console
- an **env var**: `ONEGROUND_SESSION=<id>` — survives a rename

`ls` matches on either, and reconciles the live account against the local
records in `.oneground/sessions/`. RunPod is the source of truth for what
exists; the records are bookkeeping.

`ls` flags two things:

- **ORPHAN** — a oneground pod on the account with no local record. It was
  created from another machine, or the record was deleted. It is billing and
  nothing is watching it.
- **OVER CAP** — a pod older than its own `max_hours`. Usually means a `watch`
  was interrupted.

Both print the exact command to fix them. `down` accepts a **pod id** as well
as a session id, so an orphan with no record can still be terminated by the id
`ls` prints:

```
oneground pod ls
oneground pod down <session-id-or-pod-id>
```

A record whose pod is gone is reported as stale — nothing is billing, the file
is just out of date.

**If the tooling is broken entirely**, terminate in the RunPod web console.
Keep the network volume: it holds `vectors.npy`, `queries.npy` and
`sample.jsonl.zst`, which are the release asset and are not in any tarball.
Terminating a pod never touches the volume.

For a `volume: none` session there is nothing to keep and nothing to protect:
terminating discards everything on the pod. Fetch the outputs first if the run
got far enough to write them — `oneground pod fetch <id>` — because after the
terminate they are gone.

---

## The API key

`RUNPOD_API_KEY`, **from the environment only**. It is never read from a file,
a keyring, a prompt or a CLI flag — a key that can arrive by any other route is
a key that can be committed. It is never written to disk, never logged, and
`api.redact()` scrubs it from every error string, because API error bodies have
been known to echo the request back.

A shell started *before* the variable was set does not inherit it. That is the
usual cause of "not set in the environment" on a machine where it plainly is
set; open a new terminal.

Cloudflare fronts both RunPod APIs and rejects urllib's default User-Agent with
`HTTP 403, error 1010`. That is not an auth failure — the client sets its own
User-Agent, and no amount of checking the key fixes it.

---

## Tests

```
python oneground/pod/test_pod.py     # 36 unit tests, no runner dependency
pytest oneground/pod/test_pod.py -m "not live"
pytest oneground/pod/test_pod.py -m live    # read-only, needs the key
```

The unit tests run against a stubbed transport and create nothing. They assert,
among other things, that no subcommand except `up` reaches a billable endpoint,
that `up` refuses a non-interactive stdin, that only a bare `y` is consent, and
that no `--yes` flag exists — checked against the real parser, so adding one
fails the suite.

The single `live` test runs `plan` against the real API read-only and is
skipped when the key is absent, so a fresh clone runs green without an account.

---

## First live session

**9 September 2026.** The first session `oneground pod` ran end to end against
a real pod: `sessions/smoke.yaml`, the 2,000-document smoke fixture, on an
**RTX PRO 4500 Blackwell** in EU-RO-1 with the `vecbench` volume.

It took **two attempts**, and the first one is the more useful record.

| | attempt 1 | attempt 2 |
|---|---|---|
| session | `20260909-133506` | `20260909-140954` |
| pod | `siz33fs3xais06` | `6ca69zkayfpmtg` |
| elapsed | 20.5 min | **5.7 min** |
| outcome | run never started | `DONE`, fetched, extracted, terminated |
| cost (at the real $0.72/hr) | ~$0.246 | ~$0.069 |

### What attempt 1 found

The pod deployed, synced, and set up correctly, and then the run never
started — leaving a pod billing with nothing to wait for. Three defects, none
of which needed a pod to reproduce once they were understood:

1. **`nohup` cannot parse `VAR=value`.** It is a binary, not a shell, and it
   execs its first argument. The smoke session's `run:` begins with
   `SPEC=... SOURCE=...`, so `nohup` tried to exec a program named `SPEC=...`:

       nohup: failed to run command 'SPEC=fixtures/arxiv-smoke...':
       No such file or directory

   The command now goes through `bash -c` (`sshx.build_start_command`).

2. **Subprocess output was decoded with the console codepage.** pip prints
   bytes that are not valid cp1252, which killed a reader thread with
   `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`. Now pinned to
   UTF-8 with `errors="replace"`.

3. **`start_run` inherited the 600-second timeout**, so a launch that had
   already failed was waited on for ten minutes — half the session's cost.
   Now 60 seconds.

All three are covered by tests that run without a pod, including one that
executes the generated launch line in a real shell.

### What attempt 2 verified

The whole chain: deploy → wait for RUNNING → git-bundle sync → venv on local
disk → `nohup` launch → `DONE` detection → fetch → extract → **terminate**.
`watch` terminated the pod on its own, and `ls` reported zero pods afterwards.

The fixture the pod built and the fixture the laptop had built agree on
**every one of the 14 published values**, the largest difference being
`intrinsic_dimensionality` at **8e-06** — while `vectors.npy` differs in
bytes. A fourth environment, and the same result the project has had since
task 003b: builds agree on values, not on bytes.

The verifier on the fetched fixture reports **9 verified, 2 contradicted**.
The two are `vectors.npy` and `queries.npy`, which the small tarball does not
carry, so they remain the laptop's copies checked against the pod's manifest.
`sample.jsonl.zst` is not carried either and *verified*, which locates the
boundary precisely: **sampling is byte-reproducible across environments;
embedding is not**, and everything downstream of embedding inherits that.

### Two things this session exposed that are not yet fixed

- **The price the developer confirms is not the price they pay.** `plan` reads
  GraphQL `lowestPrice`, a floor across machine configurations. Both pods were
  confirmed at **$0.34/hr** and billed at **$0.72/hr** — 2.1x. The cap held
  only because `max_hours` is enforced in time, not dollars. `POST /pods`
  returns the true `costPerHr`, so `up` can compare it against the confirmed
  rate and terminate on a mismatch.
- **The session rented a GPU and embedded on CPU.** `sessions/smoke.yaml` asks
  for a GPU, but `fixtures/arxiv-smoke.fixture.yaml` pins `device: cpu`, and
  `build_info.json` records `device: cpu` on a pod with an RTX PRO 4500. For
  the smoke fixture that is pennies; nothing checks that a session's hardware
  and its fixture spec agree.

### What changed after it — 9 September 2026

The session above worked, and it exposed two defects in the boundary itself.
Both were fixed the same day, in task 006c, before any canonical build was
allowed to run on them.

**What happened.** The developer confirmed **$0.34/hr** and both pods billed
**$0.72/hr**. The `max_usd` cap was never breached, but only because
`max_hours` bounded the run in time — a `max_usd` of $0.20 would have been
passed straight through. Separately, attempt 1's pod billed for **ten minutes
with no run started**: the launch had failed instantly, `up` waited on it for
the full 600-second timeout, and nothing was watching for a run that would
never produce output.

**What changed.**

- `plan` quotes a **range** and the prompt confirms against its **top**. The
  $0.34 was `lowestPrice` — RTX PRO 4500's *community* price, for a cloud its
  own `communityCloud` flag says it is not sold on. No worst case, no create.
- After `POST /pods`, `up` reads the pod's real `costPerHr` and **terminates
  if it exceeds the confirmed rate by more than 5%**. The true rate is
  recorded, and cost is reported against it.
- `max_usd` is now enforced **during** the run as well as before it, at the
  true rate.
- Two watchdogs: `up` terminates if the run's log never appears (180 s), and
  `watch` terminates if the log stops growing (`stall_minutes`, default 15).
- `fetch` warns before extracting when a tarball carrying a `MANIFEST` lands
  in a directory holding files it does not carry — which is why 006b's
  verifier reported 2 contradicted and it looked like a corrupt build rather
  than two provenances in one directory.

The caps on `sessions/arxiv-build.yaml` moved from 4 h / $3.00 to **1 h /
$1.50** at the same time: build 3 took 19 minutes, and a cap should be
generous, not decorative.
