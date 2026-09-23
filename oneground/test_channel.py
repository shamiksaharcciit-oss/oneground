"""The supervisor's loopback door, and the three conditions on its allowance.

Task 046. The lab's server may not make a request of its own -- the last
unbroken promise in its own header -- so the page talks to this process
directly and this process permits one origin to do it. The loosening is spent
here because the lab's no-CORS rule protects a server that serves *evidence*
and this serves an *action* already gated by a token: different properties,
so spending one is not spending the other.

These are the tests that keep it narrow.
"""

import http.client
import json
import os
import tempfile

import pytest

from oneground import jobs, supervisor

ORIGIN = "http://127.0.0.1:4321"
OTHER = "http://127.0.0.1:4322"


@pytest.fixture()
def ch(tmp_path):
    c = supervisor.Channel(supervisor.Supervisor(str(tmp_path)),
                           allow_origin=ORIGIN).start()
    try:
        yield c
    finally:
        c.stop()


def _call(ch, path, body=None, token="use", origin=None, method="POST"):
    conn = http.client.HTTPConnection("127.0.0.1", ch.port, timeout=30)
    headers = {"Content-Type": "application/json"}
    if token == "use":
        headers[supervisor.SUPERVISOR_TOKEN_HEADER] = ch.token
    elif token is not None:
        headers[supervisor.SUPERVISOR_TOKEN_HEADER] = token
    if origin:
        headers["Origin"] = origin
    raw = json.dumps(body).encode("utf-8") if body is not None else b""
    conn.request(method, path, body=raw, headers=headers)
    r = conn.getresponse()
    status, payload, got = r.status, r.read(), dict(r.getheaders())
    conn.close()
    try:
        return status, json.loads(payload), got
    except ValueError:
        return status, payload, got


# ------------------------------------------------ one origin, not a set
@pytest.mark.parametrize("bad", ["*", "http://a, http://b", "http://a http://b",
                                 "nope", "http://a/", "", "   "])
def test_an_allowance_that_is_not_one_origin_is_refused_at_construction(
        tmp_path, bad):
    """At construction, not at request time: a configuration mistake should
    not wait for a request to become visible."""
    with pytest.raises(supervisor.OriginRefused):
        supervisor.Channel(supervisor.Supervisor(str(tmp_path)),
                           allow_origin=bad)


def test_the_wildcard_refusal_says_why():
    with pytest.raises(supervisor.OriginRefused) as caught:
        supervisor._one_origin("*")
    assert "absence of one" in str(caught.value)


def test_a_second_origin_is_refused(ch):
    """The mutant for the allowance. Same request, same token, one field
    changed -- the origin -- and the answer has to change with it."""
    body = {"stage": "simulate", "invocation": ["simulate", "runs/x"]}

    status, _out, headers = _call(ch, "/enqueue", body, origin=ORIGIN)
    assert status == 200
    assert headers.get("Access-Control-Allow-Origin") == ORIGIN

    status, _out, headers = _call(ch, "/enqueue", body, origin=OTHER)
    # the job is still enqueued -- CORS is a browser rule, not an
    # authorisation -- and no allowance is echoed, so a browser will not let
    # the other page read this
    assert "Access-Control-Allow-Origin" not in headers, headers


def test_the_allowance_is_never_echoed_back_from_the_request(ch):
    """The classic way this is got wrong: reflecting whatever Origin arrived.
    A prefix or suffix of the permitted origin is a different origin."""
    for near in (ORIGIN + ".evil.test", "http://127.0.0.1:43210",
                 ORIGIN.upper(), " " + ORIGIN):
        _s, _o, headers = _call(ch, "/enqueue",
                                {"stage": "simulate",
                                 "invocation": ["simulate", "x"]},
                                origin=near)
        assert headers.get("Access-Control-Allow-Origin") != near, near


def test_a_preflight_from_the_one_origin_is_answered(ch):
    status, _out, headers = _call(ch, "/enqueue", None, token=None,
                                  origin=ORIGIN, method="OPTIONS")
    assert status == 204
    assert headers.get("Access-Control-Allow-Origin") == ORIGIN
    assert supervisor.SUPERVISOR_TOKEN_HEADER in \
        headers.get("Access-Control-Allow-Headers", "")
    assert headers.get("Vary") == "Origin"


def test_a_preflight_from_any_other_origin_is_refused(ch):
    status, out, headers = _call(ch, "/enqueue", None, token=None,
                                 origin=OTHER, method="OPTIONS")
    assert status == 403
    assert "permits one origin" in out["error"]
    assert "Access-Control-Allow-Origin" not in headers


def test_a_supervisor_told_no_origin_permits_none(tmp_path):
    """The default. A supervisor started without being told an origin is not
    quietly open to one."""
    c = supervisor.Channel(supervisor.Supervisor(str(tmp_path))).start()
    try:
        assert c.allow_origin is None
        _s, _o, headers = _call(c, "/enqueue",
                                {"stage": "simulate",
                                 "invocation": ["simulate", "x"]},
                                origin=ORIGIN)
        assert "Access-Control-Allow-Origin" not in headers
    finally:
        c.stop()


# ------------------------- the allowance is not a substitute for the token
def test_an_allowed_origin_without_a_token_is_refused(ch):
    """CORS says which page the browser will let read a reply. It says
    nothing about who may ask, and the two must not be confused."""
    status, out, headers = _call(ch, "/enqueue",
                                 {"stage": "simulate",
                                  "invocation": ["simulate", "runs/x"]},
                                 token=None, origin=ORIGIN)
    assert status == 403
    assert "token is required" in out["error"]
    # and nothing was enqueued by a request that was refused
    assert ch.sup.read() == []
    # the refusal still carries the allowance, so the page can read and show
    # it rather than seeing an unexplained network error
    assert headers.get("Access-Control-Allow-Origin") == ORIGIN


def test_a_wrong_token_from_the_allowed_origin_is_refused(ch):
    status, out, _h = _call(ch, "/enqueue",
                            {"stage": "simulate",
                             "invocation": ["simulate", "runs/x"]},
                            token="not-the-token", origin=ORIGIN)
    assert status == 403 and "token is required" in out["error"]
    assert ch.sup.read() == []


# ------------------------------------------------------------ the door
def test_enqueue_records_a_queued_job(ch):
    status, out, _h = _call(ch, "/enqueue",
                            {"stage": "simulate",
                             "invocation": ["simulate", "runs/x"]})
    assert status == 200
    assert out["job"]["state"] == "queued"
    assert [j.id for j in ch.sup.read()] == [out["job"]["id"]]


def test_the_supervisors_refusal_is_forwarded_verbatim(ch):
    """`pod up` is never a job. The channel does not rephrase the reason --
    the supervisor's sentence already names the ruling."""
    status, out, _h = _call(ch, "/enqueue",
                            {"stage": "pod up", "invocation": ["pod", "up"]})
    assert status == 400
    assert "cannot be automated by accident" in out["refusal"]
    assert out["error"] == out["refusal"]


def test_a_request_naming_no_invocation_is_refused(ch):
    status, out, _h = _call(ch, "/enqueue", {"stage": "simulate"})
    assert status == 400 and "names none" in out["error"]


def test_cancelling_a_terminal_job_is_refused(ch):
    status, out, _h = _call(ch, "/enqueue",
                            {"stage": "simulate",
                             "invocation": ["simulate", "runs/x"]})
    job_id = out["job"]["id"]
    job = ch.sup.read()[0]
    job.become(jobs.CANCELLED, partial=True)
    ch.sup._replace(job)
    status, out, _h = _call(ch, "/cancel", {"id": job_id})
    assert status == 409
    assert "must not rewrite what happened" in out["error"]


def test_the_address_file_names_the_build(ch):
    """A server and a supervisor on different checkouts would each be correct
    about themselves and wrong together -- the defect's fourth possible
    appearance, headed off where the two meet."""
    found = supervisor.address(ch.sup.runs_dir)
    assert found["url"] == ch.url and found["token"] == ch.token
    assert found["build"].endswith("oneground")
    assert found["pid"] == os.getpid()


def test_no_supervisor_is_a_real_answer():
    with tempfile.TemporaryDirectory() as tmp:
        assert supervisor.address(tmp) is None


def test_the_door_answers_post_and_nothing_else(ch):
    for method in ("GET", "PUT", "DELETE"):
        status, out, _h = _call(ch, "/enqueue", None, method=method)
        assert status == 405, method
        assert "answers POST" in out["error"]
