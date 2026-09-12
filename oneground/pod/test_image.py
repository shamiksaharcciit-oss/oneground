"""The pod image lock. Task 017 item 1.

The property under test is a refusal. A tag substituted for a missing digest
would produce a session that runs, produces numbers that look fine, and
records an image nobody can reproduce -- which is worse than not starting,
and is invisible in exactly the way the lock exists to prevent.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from oneground.pod import image as podimage  # noqa: E402

DIGEST = ("sha256:5f2e1c8a4b7d0e3f6a9c2b5d8e1f4a7c0b3d6e9f2a5c8b1d4e7f0a3c6b9d2e5f")
IMAGE = "ghcr.io/someowner/oneground-pod"


def _lock(root, body):
    d = os.path.join(root, "docker", "pod")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "IMAGE.lock"), "w", encoding="utf-8") as f:
        f.write(body)
    return root


def test_a_locked_digest_is_the_reference():
    with tempfile.TemporaryDirectory() as t:
        _lock(t, f"image={IMAGE}\ndigest={DIGEST}\ntag=abc1234\n"
                 f"reference={IMAGE}@{DIGEST}\n")
        assert podimage.is_baked(t) is True
        assert podimage.reference(t) == f"{IMAGE}@{DIGEST}"
        d = podimage.describe(t)
        assert d["baked"] is True and d["digest"] == DIGEST


def test_an_empty_digest_raises_and_never_returns_a_tag():
    """The whole point. `tag=` is present and must not be used."""
    with tempfile.TemporaryDirectory() as t:
        _lock(t, f"image={IMAGE}\ndigest=\ntag=abc1234\n"
                 "fallback_image=runpod/pytorch:1.1.0\n")
        assert podimage.is_baked(t) is False
        with pytest.raises(podimage.ImageLockError) as e:
            podimage.reference(t)
        assert "has not been built" in str(e.value)
        assert "abc1234" not in str(e.value), "the tag was offered as a way out"


def test_a_missing_lock_raises_rather_than_guessing():
    with tempfile.TemporaryDirectory() as t:
        assert podimage.is_baked(t) is False
        with pytest.raises(podimage.ImageLockError):
            podimage.reference(t)


def test_a_digest_that_is_not_a_sha256_is_refused():
    with tempfile.TemporaryDirectory() as t:
        _lock(t, f"image={IMAGE}\ndigest=latest\n")
        assert podimage.is_baked(t) is False
        with pytest.raises(podimage.ImageLockError) as e:
            podimage.reference(t)
        assert "not a sha256" in str(e.value)


def test_an_inconsistent_reference_is_refused():
    """image@digest and the stated reference disagreeing means one of them is
    stale, and running either would be a guess."""
    with tempfile.TemporaryDirectory() as t:
        _lock(t, f"image={IMAGE}\ndigest={DIGEST}\n"
                 f"reference={IMAGE}@sha256:0000\n")
        with pytest.raises(podimage.ImageLockError) as e:
            podimage.reference(t)
        assert "inconsistent" in str(e.value)


def test_describe_says_which_of_the_two_it_is():
    """`pod plan` prints this; "the image" is not a checkable fact."""
    with tempfile.TemporaryDirectory() as t:
        _lock(t, f"image={IMAGE}\ndigest=\n"
                 "fallback_image=runpod/pytorch:1.1.0-cu1300\n")
        d = podimage.describe(t)
        assert d["baked"] is False
        assert d["reference"] == "runpod/pytorch:1.1.0-cu1300"
        assert "no digest" in d["note"]
        assert podimage.fallback(t) == "runpod/pytorch:1.1.0-cu1300"


def test_comments_and_blank_lines_are_not_values():
    with tempfile.TemporaryDirectory() as t:
        _lock(t, "# digest=sha256:deadbeef\n\n"
                 f"image={IMAGE}\n\ndigest={DIGEST}\n")
        assert podimage.reference(t) == f"{IMAGE}@{DIGEST}"


def test_the_committed_lock_is_readable_and_self_consistent():
    """Not synthetic: the lock actually in this repo.

    It is allowed to have no digest -- that is its state until the workflow
    has run -- but it must parse, and it must not claim to be baked without
    one.
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    lock = podimage.read_lock(root)
    assert lock, "docker/pod/IMAGE.lock is missing or unparseable"
    assert lock.get("image", "").endswith("/oneground-pod"), lock.get("image")
    assert lock.get("fallback_image"), "no fallback recorded"
    if podimage.is_baked(root):
        assert podimage.reference(root).startswith(lock["image"] + "@sha256:")
    else:
        assert not (lock.get("digest") or "").strip()
        with pytest.raises(podimage.ImageLockError):
            podimage.reference(root)
