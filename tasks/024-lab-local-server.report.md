# Report: 024-lab-local-server

## Repo state expected vs found

- **Branch:** as expected. `task-020` in the worktree, eight commits on `383c7a1` with the brief at `f92eb57`, clean tree. `main`, the tag and `site/teaser/` untouched; no rebase.
- **The brief:** `tasks/024-lab-local-server.md`, committed on the branch.
- **The design study:** `docs/design/` holds only `tokens.css` and `tokens.md`, so the ground and query trace "as the design study shows them" were taken from the teaser (`site/teaser/`, read, not edited), which is the one place both are already drawn.
- **Nothing unexpected otherwise.** One pre-existing log line surfaced while testing; see Observed.

## What was done

**(1) The command.** `oneground lab <workdir>`:
- **Starts a server and prints one line** with the URL, the render mode and why, the configuration and the startup time. It opens nothing; `--no-browser` is the default, `--open` opens one.
- **Flags:** `--port` (default ephemeral), `--host` (default `127.0.0.1`), `--i-know`, `--mode move|release`, `--family`, `--config` (when a run holds configurations differing in more than ε), and `--also <workdir>` (another run of the same configuration at other ε, read-only, so its recall can be shown there).
- **Ctrl-C, SIGTERM and Ctrl-Break** stop it cleanly: `oneground lab: stopped. Nothing was written.`
- **`UNGUARDED`, with its reason.** It writes no artifact and starts no measurement, following the precedent of `calibrate show`, and the environment guard's two printed lines would break the one startup line. It runs its own guard instead (below).
- **Refusals:** a directory without `state/`, `simulate.json` or `characterization.json` is refused, naming what is missing and the two commands that produce it.

**(2) Read-only, provably.**
- **No write path.** Only GET is answered (405 otherwise); the server holds the loaded run, the token, the measured mode, the verified digests and its three interface files, all fixed at startup, and no other state.
- **No request logging:** request lines carry the token.
- **The test:** a session through every endpoint, refused requests included, while every way the process could write a file (`open` in any write mode, `makedirs`, `mkdir`, `remove`, `unlink`, `rename`, `replace`, `rmdir`) is watched. It asserts no attempt, and every file under both run directories byte-identical with none added.
- **On real runs,** the same, measured from outside the process: below.

**(3) A transport, never a second renderer.**
- **Every drawing sent is the view's own.** `/api/ground` and `/api/trace` return `contract.draw(view, …).as_dict()` of the views in `oneground/lab/views/`, serialised and unchanged; a test compares response bytes with drawing the view directly, and they are equal. No endpoint draws anything a view does not.
- **One run reader.** The composer logic — which states a run holds, the declared set of simulated ε, the cost and the action — moved from `corpora/render_from_state.py` into `oneground/lab/runs.py`, and both the script and the server use it. `render_from_state.py` keeps its command line and output; task 020's acceptance still passes through it (Verification).
- **The guard, for a transport.** The view guard forbids HTTP and file reads, which a server must do, so `guard.py` gains a transport profile: no measuring import and, for the server's own modules, no numpy at all (a module that cannot hold an array cannot compute one), no vector arithmetic, no vector data, no `eval`/`exec`/`__import__`. `check_transport()` reads `server.py` and `runs.py`. The server runs `check_views()` and `check_transport()` before it binds a port, and refuses to start if either finds anything.
- **Over everything it imports.** A test imports the server in a clean process, requires that no measuring module was loaded (faiss, scikit-learn, scipy, torch, umap, the model families, `measures`, `truth`, `simulate`, `characterize`, `verify`, `calibrate`, `fixture`, `adapters`, `pod`, `report`), and reads every oneground module it pulled in with the transport rules. Two files may break exactly one rule, each with its reason: `models/state.py` and `lab/contract.py` name `partition.centroids`, one to define it and one to refuse it.

**(4) Render mode, chosen by measurement.**
- **The measurement.** At startup the server times 20 whole ground draws for this corpus across the ε range (after 3 warm-up draws) and applies 023b's rule: *redraw on move* only if p95 ≤ one 16.7 ms frame, otherwise *render on release*.
- **Where it shows.** The mode, the measured p95 and why are in the startup line, at the top of the page, in the check footer, and in the ground's own caption (`contract.RenderMode.sentence()`), so a screenshot carries it.
- **`--mode` overrides** with the same caption behaviour: the caption says it was chosen by `--mode` and what measurement alone chose.

**(5) The ε contract, unchanged.** The ground recounts as ε moves. Recall, candidates and missed neighbours appear only at simulated ε; between them the recall panel reads *not simulated at this epsilon*, names the simulated values, gives the cost in minutes from the recorded timings, and shows the exact `oneground simulate … --emit-state` command with the grid. The server never runs it.

**(6) The interface.** `oneground/lab/static/`: `index.html`, `lab.css` (the tokens from `docs/design/tokens.css` verbatim) and `lab.js`.
- **The ground.** The state holds no positions, so vectors are laid out by home region — one cell per region, in id order — and coloured by copy count with the teaser's derived ramp. The figure caption says it is a layout, not a projection. Counters show vectors copied, storage, p99 and routing ceiling@10; the drawing's caption and gaps sit below.
- **The query trace.** Scoring, routing with reasons, true neighbours with the outside count, and the recall panel; on the ground, the routed region, the other probed regions and the neighbours' regions are outlined.
- **The control.** In *redraw on move*, every move asks for a drawing, with at most one request in flight and the latest position drawn last. In *render on release*, moving only updates the readout and says "showing ε A; release to redraw at B", and letting go redraws.
- **No external requests.** No font, script or data from any other origin; no `@font-face`; no inline script or style (the CSP would refuse them). A test reads the shipped files for any external reference. The check footer states the workdir, each directory's digests verified, the render mode, and the token's scope.

**(7) Security.**
- **Loopback by default;** a non-loopback `--host` is refused without `--i-know`, and with it a warning names what is exposed. The command checks the host before loading anything.
- **No path from a request reaches the filesystem:** the only files served are the interface's three, by exact path from a fixed table; states are drawn, never served. `../`, encoded `%2e%2e` and `%2F`, absolute paths and directory listings all return 404.
- **No CORS** header is ever sent. A strict CSP (`default-src 'none'`, `'self'` for script, style and requests, `frame-ancestors 'none'`), `no-referrer`, `nosniff` and `no-store` are set on every response.
- **Host check:** a request naming any Host but the addresses bound is refused, which closes DNS rebinding.
- **The token.** `secrets.token_urlsafe(32)`, required on every request as a query parameter or header, compared in constant time. What it protects against and what it does not is in `docs/LAB.md`.

**(9) Docs.** `docs/LAB.md`: the command, the two views, the ε rule, the render modes, the security model and its limits, and why a server rather than a file.

## Measurements

**(8) On real runs**, started exactly as a user would, from the worktree root, with each run's other-ε run added (`tasks/scratch/024-proof.py`). The startup lines, verbatim. The tokens belong to sessions that have since exited.

arXiv 150k:

```
oneground lab: http://127.0.0.1:53759/?token=0xiyK-W5K5ZcQGCRniTVhNpnUQ6wzgncp2dT75ybOL0  |  render on release: ground draw p95 78.3 ms over 20 draws against a 16.7 ms frame  |  semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2] in runs/020-ref-arxiv  |  ready in 2.3 s
```

StackExchange 20k:

```
oneground lab: http://127.0.0.1:53802/?token=FJQAqKQ8V581UsRVsdIBsBi-FQ14V4REIGYXsHW_buM  |  render on release: ground draw p95 17.1 ms over 20 draws against a 16.7 ms frame  |  semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2] in runs/020-ref-stackexchange  |  ready in 2.7 s
```

| | arXiv 150k | StackExchange 20k |
|---|---|---|
| startup: process launch to the line | 2.7 s | 3.0 s |
| chosen mode, measured p95 | render on release, 78.3 ms | render on release, 17.1 ms |
| simulated ε in the declared set | 0.1, 0.2, 0.3 | 0.0, 0.1, 0.2, 0.3 |
| memory held (interpreter working set), after startup → after the session | 87.9 → 90.1 MB, peak 100.6 MB | 78.9 → 79.2 MB, peak 79.2 MB |
| requests in the session, all answered 200 | 37 | 37 |
| ground drawing body | 1,777,330 bytes | 224,105 bytes |
| ground request round trip, 8 ε values | 144–168 ms | 26–72 ms |
| manifests verified by the lab at startup | 18 of 18 entries, 4 directories | 19 of 19 entries, 4 directories |
| files hashed before and after, both run directories | 55: none changed, none added | 42: none changed, none added |
| stop | `oneground lab: stopped. Nothing was written.`, exit 0, empty stderr | the same |

- **The session:** the page and its two assets, `/api/check`, `/api/run`, and at 8 ε values each (the base, 0, simulated values, values between them, and 0.5) the ground plus the query trace for queries 0, 15 and the last.
- **Memory** is the interpreter's working set from `Win32_Process`. My first run of the proof read the launcher's PID instead: on Windows the venv's `python.exe` starts the real interpreter as a child and holds about 4 MB itself. That reading was wrong and is not used here.
- **The round trip** is what a user waits for after releasing the control: the draw, serialising the drawing, and sending it. The p95 the mode is chosen from covers the draw only.

**Is the startup measurement pessimistic?** Both runs chose release, and at 20k task 023b's interleaved measurement had put a ground draw at p95 11.2 ms, which would be move. I measured before changing anything (`tasks/scratch/024-mode-repeat.py`): each run loaded once, the server's own measurement taken four times in a row.

| reading | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| 20k p95 → mode | 16.3 ms → **move** | 17.8 → release | 36.3 → release | 26.2 → release |
| 150k p95 → mode | 178.0 ms → release | 171.4 → release | 53.8 → release | 79.6 → release |

- **No cold start.** Reading one is neither consistently the slowest nor the fastest, so there is nothing a larger warm-up would fix, and none was added.
- **The host drifts, as task 023b found.** On this laptop today, 150k is 54–178 ms: release under any reading.
- **At 20k this host sits on the frame boundary:** the same code chose move once and release three times. The server does what the brief and 023b specify, and release is always the honest side — nothing on screen trails the control. But on a host near 16.7 ms, the mode depends on the second the server started. See Blocked on developer.

## Verification

- **`oneground/lab/test_server.py`: 16 of 16:**
  - a full session writes nothing, with every write path watched and digests unchanged;
  - responses are the views' drawings byte for byte, including a trace from an `--also` state and a not-simulated panel with its cost and command;
  - the transport guard passes over `server.py` and `runs.py`, catches each kind of computation (numpy, a measuring import, a relative import of models, `@`, `.dot`, a vector attribute, the vector column, `eval`), and allows HTTP and file reads;
  - everything the server imports passes, with no measuring module loaded;
  - every route refuses a missing, wrong or empty token, and accepts header or query;
  - 20 traversal, absolute-path and listing attempts return 404 and leak no state bytes;
  - loopback accepted, and `0.0.0.0`, a LAN address, `::` and a hostname refused without `--i-know`, whose warning names the network, the token, the drawings and the digests;
  - `python -m oneground.cli lab <wd> --host 0.0.0.0` exits 2 without printing a URL;
  - a foreign Host is refused;
  - POST, PUT, PATCH, DELETE and OPTIONS return 405, and no `Access-Control-*` header is sent even to an Origin;
  - bad query and ε parameters return 400;
  - the mode boundary sits at exactly one frame, and `--mode` keeps the measured choice;
  - the measured mode appears in the startup line, `/api/run` and the ground's caption, and an override says so;
  - the interface references no other origin and has no inline script or style;
  - a directory that is not a run is refused, naming what is missing.
- **`oneground/lab/test_lab.py`: 27 of 27,** including the composer tests, now run through `runs.py`.
- **`oneground/test_environment.py` 42, `test_cli.py` 8, `models/test_conformance.py` 23, `test_packaging.py` 13:** all pass. `oneground lab` is on `UNGUARDED` with its reason, and the coverage test accepts it.
- **Full suite** (`pytest oneground corpora`, from the worktree root): **839 passed, 3 skipped, 0 failed**, in 414.0 s. That is 16 more than task 023's 823: the server tests. The 3 skips are the same environment gates as before: no local `runs/arxiv-150k-via-characterize` verify or report workdir, at `oneground/report/test_claims.py:443`, `oneground/report/test_end_to_end.py:348` and `oneground/verify/test_matched.py:1182`.
- **Re-run after `render_from_state.py` moved onto `runs.py`: two checks, which prove different things.**
  - **The published figures still reproduce.** Task 020's unchanged acceptance script (sha256 `9fc0a0d9…`) passes 20 of 20 on the arXiv state rendered through the refactored composer. This is necessary, and it is all this check shows: it reads the figures the teaser published and nothing else, so a change to any other field would pass it.
  - **The composer's output is unchanged.** The same rendering equals task 020's `render.json` in all 24 fields task 020 wrote, across 2,000 queries (`tasks/scratch/021-render-equivalence.py`). This is what covers the fields the acceptance script does not read. It compares those 24 fields only; fields added since task 020, such as the ground's caption and ceiling, are outside it.
- **Identifier scan:** every changed and new file scanned before the commit, and the committed tree after.

## Observed, not done

- **The mode is unstable near the frame.** Above; the rule was not changed.
- **A Windows WMI failure logged during tests.** `oneground/test_environment.py` prints `Windows fatal exception: code 0x8007000e` (`E_OUTOFMEMORY`) with a stack through `platform._wmi_query`, called from faiss's `loader.py` (`platform.machine()`) on import. pytest's faulthandler prints it, the exception is handled, and the run passes 42 of 42. No lab module is in the stack, and `oneground/environment.py` already records this WMI query raising under memory pressure. I did not bisect it to an older commit.
- **The p95 is the server's draw, not what a user waits for.** At 150k a ground request round trip is 144–168 ms, so even a host whose draw fit the frame would trail a dragged control by the transfer and the browser's JSON parse. The brief defines the measurement as the draw, and that is what is implemented; `docs/LAB.md` says the p95 covers the draw only.
- **The ground drawing is 1.8 MB of JSON at 150k.** It is sent whole on each redraw. A columnar or binary encoding would shrink it, but it would be a second serialisation of a drawing, and I didn't add one.
- **Fonts are not bundled**, as in the teaser: system faces with the tokens' fallback stacks.
- **I did not open the interface in a browser** from this session. The page, its assets and every API response were exercised over HTTP by the tests and the proof, and the no-external-request property is enforced by the CSP and checked in the files. How it looks has not been viewed.
- **The first proof run's memory figure was wrong** (the launcher's PID) and was corrected before being reported.

## Repo now contains

On `task-020`, not pushed, one new commit after `f92eb57`:
- **New:**
  - `oneground/lab/server.py`: the transport.
  - `oneground/lab/runs.py`: the one run reader.
  - `oneground/lab/static/index.html`, `lab.css`, `lab.js`: the interface.
  - `oneground/lab/test_server.py`: 16 tests.
  - `docs/LAB.md`.
  - This report.
- **Changed:**
  - `oneground/lab/contract.py`: `RenderMode`, `FRAME_MS`, the mode names, `load_header`.
  - `oneground/lab/guard.py`: the transport profile, `check_transport`, and the per-rule allowlist.
  - `oneground/lab/views/ground.py`: the render mode joins the caption.
  - `oneground/models/state.py`: `read_header`, additive.
  - `oneground/cli.py`: `oneground lab`, and its `UNGUARDED` entry.
  - `corpora/render_from_state.py`: onto `runs.py`, same command line and output.
  - `pyproject.toml`: the interface files ship as package data.

No measured value, tolerance, seed, gate, fixture file or published figure was changed.

## Blocked on developer

- **The mode rule near the frame.** On this laptop a 20k run straddles 16.7 ms: one reading chose move and three chose release. 023b's rule is implemented as written. Whether to add a margin (release unless p95 is well inside the frame), take more draws, or keep the rule and let the startup line say which it was, is a design decision, and I didn't make it.
- **The rebase is still held.** On the 23rd, before anything else, `task-020` is rebased onto `main`, which has moved (a licence file, and task 022 in progress). The branch will then be ten commits deep.
