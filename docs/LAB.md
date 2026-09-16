# The lab — `oneground lab <workdir>`

The way into the lab for a corpus of your own. After you have run

```
oneground characterize requirements.yaml
oneground simulate requirements.yaml --emit-state
```

on your own vectors, the run's directory holds everything the lab needs.

```
oneground lab runs/my-run
```

starts a server on this machine, prints one line with its URL, and opens
nothing. `--open` opens the URL in a browser.

**Why a server rather than a file:** a generated file would have to carry the
corpus inside it, and a server reads the run directory as it is — so any corpus
size works, the recall panel has a command to hand you, and a slow host has
somewhere to render on release.

---

## What it needs and what it reads

`<workdir>` is a run's directory:

| | |
|---|---|
| `state/` | written by `simulate --emit-state`; required |
| `simulate.json`, `characterization.json` | required |
| `verify.json`, `report.json` | shown as present or absent |

If the directory holds several configurations of a family that differ in more
than ε, `--config <label>` picks one; `--family` picks the family (default
`semantic_sharded`). `--also <workdir>` adds another run of the same
configuration at other ε values, so its recall can be shown there too. Every
directory is read once, at startup, and never written.

## The two views

- **The ground.** Every base vector, coloured by how many regions it is copied
  into, with the copies histogram, vectors copied, storage amplification, p99
  copies and the routing ceiling@10. The state holds no positions, so the
  interface lays the vectors out by home region — one cell per region, vectors
  in id order — and says so. It is a layout, not a projection.
- **One query's trace.** Where the query was routed, the regions it probed and
  why, its true neighbours and how many live outside the routed region, and
  its recall panel. On the ground, the routed region, the other probed regions
  and the regions its neighbours live in are outlined.

Both are the views in `oneground/lab/views/`, drawn through the rendering
contract in `docs/STATE.md`. The server does not draw anything itself.

## The ε rule

- **Geometry recounts as ε moves:** copy counts, the histogram, storage, p99,
  shard sizes, the routing ceiling.
- **Recall, candidates and missed neighbours appear only at simulated ε.**
  Between simulated values the recall panel reads **not simulated at this
  epsilon**, lists the ε values that were simulated, gives the cost of
  simulating one in minutes from the runs' recorded timings, and shows the
  exact `oneground simulate … --emit-state` command, with the grid to put in
  your requirements file. **The lab never runs it.**
- **Nothing between simulated values is interpolated.** The ground's caption
  says when the ε on screen was not simulated.

## Render modes

A lab that redraws the ground on every move of the ε control must finish a
draw within one frame at p95, or what is on screen trails the control (task
023b). So at startup the server times a whole ground draw for this corpus, 20
times across the ε range, and chooses:

| mode | when | what the control does |
|---|---|---|
| **redraw on move** | ground draw p95 ≤ 16.7 ms | every move asks for a new drawing; at most one request is in flight, and the latest position is always drawn last |
| **render on release** | p95 > 16.7 ms | moving updates the ε readout and says which ε the ground on screen belongs to — "showing ε 0.20; release to redraw at 0.35"; letting go redraws |

The startup line prints the chosen mode with the measured p95. The interface
shows it at the top of the page, in the check footer, and in the ground's own
caption, so a screenshot carries it. `--mode move` or `--mode release`
overrides the choice; the caption then says it was chosen by `--mode` and what
measurement alone would have chosen.

The p95 covers the server's draw only. Sending the drawing and painting it in
the browser add to it; at 150,000 vectors the ground drawing is about 2 MB of
JSON.

---

## Security

### The model

- **Loopback by default.** It binds `127.0.0.1`. Any non-loopback `--host` is
  refused unless `--i-know` is also given, and then a warning names what is
  exposed.
- **Read-only.** No method but GET is answered, no file is written anywhere,
  and no request line is logged, since request lines carry the token. A test
  runs a session through every endpoint while watching every way the process
  could write a file, and checks the run directories' digests before and
  after.
- **No path from a request reaches the filesystem.** The only files served are
  the interface's own three, by exact path, from a fixed table. States are
  drawn, never sent. Traversal (`../`, encoded `%2e%2e`), absolute paths and
  directory listings are all answered 404, and tests try each.
- **No CORS, and a strict Content-Security-Policy.** No
  `Access-Control-Allow-Origin` is ever sent, and the page is served with
  `default-src 'none'` plus `'self'` for its own script, style and requests.
  The interface makes no request to another origin: no fonts, scripts or data
  from anywhere else.
- **An expected Host only.** Requests naming any Host but the address the lab
  bound are refused. That closes DNS rebinding, where a page on another site
  points its own name at this machine.
- **A token on every request.** The printed URL carries a random token
  (`secrets.token_urlsafe(32)`), required on every request — as the `token`
  query parameter or the `X-Oneground-Token` header — and compared in constant
  time. The page passes it to its own assets and requests.
- **Nothing measured.** The server imports nothing that measures and does not
  import numpy. The rendering contract's guard is run over its source, and
  over everything it imports, before it binds a port.

### What the token protects against

- **Another user's process on the same machine** reading your corpus's drawings
  off a loopback port they can connect to but whose URL they never saw.
- **A web page in your own browser** guessing the port and asking for data. It
  cannot read the response without CORS, cannot supply the token, and is
  refused on Host if it tries DNS rebinding.

### What it does not protect against

- **Anyone who has the URL.** The token is in it. A URL copied into a chat,
  saved in shell history, or captured in a screenshot opens the lab for as
  long as that process runs. Each start makes a new token.
- **Anything running as you.** A process with your permissions can read your
  terminal, your browser, or the run directory itself; the lab adds no
  protection against it.
- **The network, once you pass `--host` with `--i-know`.** The token is then
  the only thing between the run and anyone who can reach the port, and the
  connection is plain HTTP, so anyone on the path can read the token and every
  drawing.
- **The content of the run.** Drawings reveal region sizes, copy counts, query
  routes and neighbour ids. They do not contain vectors or text, but they are
  derived from your corpus, and the lab treats them as sensitive for that
  reason.

## Stopping

Ctrl-C stops the server, and it says so: `oneground lab: stopped. Nothing was
written.`
