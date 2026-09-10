"""RunPod API client, with the billable endpoints locked behind a token.

Two APIs are in play, because neither alone does the job:

    REST    https://rest.runpod.io/v1      pods, network volumes, templates,
                                           billing. The modern surface, and it
                                           carries everything except prices.
    GraphQL https://api.runpod.io/graphql  `gpuTypes(...) { lowestPrice }`,
                                           the only place an hourly price
                                           scoped to a datacenter can be read.
                                           REST has no /gputypes path: it 400s
                                           with "that path ... does not exist
                                           in the specification".

Both are read with the same bearer token.

The create guard
----------------
`BILLABLE` lists the (method, path-template) pairs that can start, or resume,
costing money. `request()` raises `CreateCallBlocked` for any of them unless
`allow_create(token)` has been called with a token minted by
`confirm.ask_to_create()`. The guard runs before the transport is touched, so
a blocked call makes no network request at all.

DELETE /pods/{id} is deliberately *not* billable: terminating only ever stops
the meter, which is why `down` needs no confirmation. `POST /pods/{id}/start`
and `/restart` *are* billable -- resuming a stopped pod resumes charging, and
that is as much a spend as creating one.

Secrets
-------
The key is read from the environment, held in memory, and sent only in the
Authorization header. `redact()` replaces it with `<redacted:RUNPOD_API_KEY>`
in any string; every error this module raises passes through it, because API
error bodies have been known to echo the request back.
"""

import json
import os
import re
import urllib.error
import urllib.request

REST_BASE = "https://rest.runpod.io/v1"
GRAPHQL_URL = "https://api.runpod.io/graphql"

ENV_VAR = "RUNPOD_API_KEY"

# Cloudflare sits in front of both APIs and rejects urllib's default
# User-Agent ("Python-urllib/3.12") with HTTP 403, Cloudflare error 1010 --
# "banned ... based on your browser's signature". It is not an auth failure and
# no amount of checking the key will fix it, so the UA is set explicitly and
# named here rather than being rediscovered from a confusing 403.
USER_AGENT = "oneground-pod/0.1 (+https://oneproof.dev)"

# Endpoints that can begin, or resume, being charged for. Path templates are
# matched after concrete ids are collapsed, so a real pod id in the path does
# not slip past the check.
BILLABLE = frozenset({
    ("POST", "/pods"),
    ("POST", "/pods/{id}/start"),
    ("POST", "/pods/{id}/restart"),
    ("POST", "/pods/{id}/resume"),
    ("POST", "/endpoints"),
    ("POST", "/networkvolumes"),
    ("POST", "/templates"),
})

# GraphQL is used read-only. Anything that is not a `query` is refused
# regardless of its name: RunPod's deploy mutations live at this URL, and an
# allowlist of mutation names would fail open as the API grows.
_QUERY_RE = re.compile(r"^\s*(query\b|\{)")


class PodApiError(RuntimeError):
    """An API call failed. The message is always redacted.

    `status` is the HTTP status when there was one, so a caller can tell "this
    pod is gone" from "the account is unreachable" without parsing a message.
    """

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def is_gone(exc):
    """True when the error says the resource does not exist.

    RunPod answers DELETE on an already-terminated pod with 404, which is the
    normal end state of a pod killed in the console -- not a failure. The
    status code is the signal; the message is checked only for errors raised
    by a transport that did not set one.
    """
    if getattr(exc, "status", None) == 404:
        return True
    return "HTTP 404" in str(exc)


class CreateCallBlocked(PodApiError):
    """A billable endpoint was reached without developer confirmation.

    This is a bug in the caller, not a condition to retry or work around.
    """


def redact(text, key=None):
    """Replace the API key wherever it appears in a string.

    Falls back to the environment when no key is passed, so it is safe to call
    from an error path that does not have the client in scope.
    """
    if text is None:
        return None
    s = str(text)
    k = key if key is not None else os.environ.get(ENV_VAR)
    if k:
        s = s.replace(k, "<redacted:%s>" % ENV_VAR)
    return s


def key_from_env(env=None):
    """The API key, from the environment only.

    Never falls back to a file, a keyring, a prompt or a CLI flag: a key that
    can arrive by any other route is a key that can be committed.
    """
    e = os.environ if env is None else env
    k = e.get(ENV_VAR)
    if not k or not k.strip():
        raise PodApiError(
            "%s is not set in the environment.\n"
            "Set it in the developer's user environment and start a new "
            "terminal -- a shell started before it was set does not inherit "
            "it. oneground never reads the key from a file or a flag."
            % ENV_VAR)
    return k.strip()


def normalise_path(path):
    """Collapse concrete ids so a path can be matched against BILLABLE.

    '/pods/abc123/start' -> '/pods/{id}/start';  '/pods' -> '/pods'.
    Query strings are dropped before matching.
    """
    parts = [p for p in path.split("?")[0].split("/") if p]
    out = []
    for i, p in enumerate(parts):
        # Under a REST collection every second segment is an id.
        out.append(p if i % 2 == 0 else "{id}")
    return "/" + "/".join(out)


def is_billable(method, url_or_path):
    """True if this call could start or resume charging.

    Accepts a full URL or a bare path so both the client and the tests can ask
    the same question of the same function.
    """
    path = url_or_path
    if path.startswith(REST_BASE):
        path = path[len(REST_BASE):]
    elif path.startswith("http"):
        # A non-REST absolute URL: only GraphQL is ever used, and only for
        # queries, which graphql() enforces separately.
        return False
    return (method, normalise_path(path)) in BILLABLE


class RecordingTransport:
    """Test double: records every call, replays canned responses.

    Used by test_pod.py to assert that no subcommand except `up` reaches a
    billable endpoint. It lives beside the client rather than in the test file
    so the recorded shape and the real one cannot drift apart.

    `responses` maps a substring of the URL to the object to return; the key
    "*" is the fallback. The **longest** matching pattern wins, not the first
    one in dict order -- "/pods" and "/pods/{id}" are both substrings of a
    single-pod URL, and dict-order matching silently handed the list response
    to a caller expecting one pod.
    """

    def __init__(self, responses=None):
        self.calls = []              # [(method, url, body_or_None)]
        self.responses = dict(responses or {})

    def __call__(self, method, url, body, headers, timeout):
        self.calls.append((method, url, body))
        best = None
        for pattern, resp in self.responses.items():
            if pattern != "*" and pattern in url:
                if best is None or len(pattern) > len(best[0]):
                    best = (pattern, resp)
        resp = best[1] if best else self.responses.get("*", {})
        return resp() if callable(resp) else resp

    def billable_calls(self):
        """Every recorded call that could have cost money."""
        return [(m, u) for m, u, _ in self.calls if is_billable(m, u)]

    def graphql_calls(self):
        return [(m, u, b) for m, u, b in self.calls if u == GRAPHQL_URL]


def _urllib_transport(method, url, body, headers, timeout):
    """Default transport. stdlib only -- no new runtime dependency."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:800]
        except Exception:
            pass
        raise PodApiError(redact("%s %s -> HTTP %s %s"
                                 % (method, url, e.code, detail)),
                          status=e.code) from None
    except urllib.error.URLError as e:
        raise PodApiError(redact("%s %s -> %s" % (method, url, e.reason))) from None
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        raise PodApiError(redact("%s %s -> non-JSON response: %s"
                                 % (method, url, raw[:300]))) from None


class RunPodClient:
    """Read-only by construction; billable calls need an explicit token.

    The transport is injectable so the tests can drive the real client logic --
    the guard included -- with no network.
    """

    def __init__(self, key=None, transport=None, timeout=60):
        self._key = key if key is not None else key_from_env()
        self._transport = transport or _urllib_transport
        self._timeout = timeout
        self._create_token = None

    # -- the money boundary -------------------------------------------------
    def allow_create(self, token):
        """Unlock the billable endpoints for this client instance.

        `token` must be the object returned by `confirm.ask_to_create()`, the
        only code in the package that reads stdin. Anything else -- True,
        "yes", a string off a flag -- is rejected, so the unlock cannot be
        spelled by accident or by a caller that never met a human.
        """
        from . import confirm
        if not isinstance(token, confirm.CreateAuthorization):
            raise CreateCallBlocked(
                "allow_create() needs a CreateAuthorization from "
                "confirm.ask_to_create(); got %s. There is no other way to "
                "unlock a billable call, and no --yes flag."
                % type(token).__name__)
        token.check_valid()
        self._create_token = token
        return self

    def create_allowed(self):
        return self._create_token is not None

    def _headers(self):
        return {"Authorization": "Bearer " + self._key,
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT}

    def _guard(self, method, path):
        if is_billable(method, path) and not self.create_allowed():
            raise CreateCallBlocked(
                "%s %s is a billable endpoint and this client holds no "
                "developer confirmation. Only `oneground pod up` may reach "
                "it, and only after a typed 'y'." % (method, path))

    # -- REST ---------------------------------------------------------------
    def request(self, method, path, body=None):
        self._guard(method, path)
        return self._transport(method, REST_BASE + path, body,
                               self._headers(), self._timeout)

    def list_pods(self):
        r = self.request("GET", "/pods")
        return r if isinstance(r, list) else (r or {}).get("data", [])

    def get_pod(self, pod_id):
        return self.request("GET", "/pods/" + pod_id)

    def list_network_volumes(self):
        r = self.request("GET", "/networkvolumes")
        return r if isinstance(r, list) else (r or {}).get("data", [])

    def terminate_pod(self, pod_id):
        """DELETE is not billable -- it only ever stops the meter."""
        return self.request("DELETE", "/pods/" + pod_id)

    def pod_billing(self, pod_id):
        return self.request("GET", "/billing/pods?podId=" + pod_id)

    def create_pod(self, spec):
        """The one billable call. Blocked unless allow_create() was handed a
        token from an interactive confirmation."""
        return self.request("POST", "/pods", body=spec)

    # -- GraphQL (read-only) ------------------------------------------------
    def graphql(self, query, variables=None):
        if not _QUERY_RE.match(query):
            raise CreateCallBlocked(
                "only GraphQL `query` operations are permitted; this package "
                "never sends a mutation (RunPod's deploy mutations live at "
                "this URL)")
        headers = self._headers()
        body = {"query": query}
        if variables:
            body["variables"] = variables
        r = self._transport("POST", GRAPHQL_URL, body, headers, self._timeout)
        if isinstance(r, dict) and r.get("errors"):
            raise PodApiError(
                redact("graphql: " + json.dumps(r["errors"])[:600], self._key))
        return (r or {}).get("data", {}) or {}

    def gpu_price_ranges(self, data_center_id, cloud_type="SECURE"):
        """Price *range* per GPU type in one datacenter, for one cloud type.

        Task 006b billed $0.72/hr against a confirmed $0.34/hr. The $0.34 was
        `lowestPrice.uninterruptablePrice`, which is a floor across
        configurations -- and, for RTX PRO 4500, it is literally the
        *community* price of a GPU whose `communityCloud` flag is false. The
        session runs on SECURE, whose list price is $0.72. So the number the
        developer confirmed was the price of a machine they could not have
        been given.

        This returns both ends, and the caller confirms against `usd_max`:

            usd_min   the datacenter floor (`lowestPrice`)
            usd_max   the list price for the cloud actually being bought
                      (`securePrice` / `communityPrice`)

        `lowestPrice` is still called, and deliberately: it is the only
        datacenter-scoped signal the API offers -- `gpuTypes(input:)` rejects a
        `dataCenterId` argument, so `securePrice` is global. Dropping it would
        mean quoting prices for GPU types the resolved datacenter does not
        stock, which is a regression of the property task 006 built. It is used
        here for availability, stock, and the *bottom* of the range. It is
        never the number anyone confirms against.

        A type with `usd_min` None is not offered in that datacenter. A type
        with `usd_max` None cannot be priced at all -- the caller must report
        couldn't-check and refuse to create, never fall back to the floor.
        """
        cloud = (cloud_type or "SECURE").upper()
        q = ("query { gpuTypes { id displayName memoryInGb "
             "secureCloud communityCloud securePrice communityPrice "
             "lowestPrice(input:{gpuCount:1, dataCenterId:%s}) "
             "{ uninterruptablePrice stockStatus } } }"
             % json.dumps(data_center_id))
        out = {}
        for g in self.graphql(q).get("gpuTypes", []) or []:
            lp = g.get("lowestPrice") or {}
            floor = lp.get("uninterruptablePrice")
            if cloud == "COMMUNITY":
                list_price = g.get("communityPrice")
                offered_on_cloud = bool(g.get("communityCloud"))
            else:
                list_price = g.get("securePrice")
                offered_on_cloud = bool(g.get("secureCloud"))

            if floor is not None and list_price is not None:
                usd_min = min(floor, list_price)
                usd_max = max(floor, list_price)
            else:
                usd_min = floor
                usd_max = list_price

            out[g["displayName"]] = {
                "id": g["id"],
                "display_name": g["displayName"],
                "memory_gb": g.get("memoryInGb"),
                "usd_min": usd_min,
                "usd_max": usd_max,
                "floor": floor,
                "list_price": list_price,
                "cloud_type": cloud,
                "offered_on_cloud": offered_on_cloud,
                "stock": lp.get("stockStatus"),
            }
        return out
