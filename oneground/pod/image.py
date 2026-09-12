"""The pod image, read from its lock file. Task 017 item 1.

Sessions reference the pre-baked image **by digest**. A tag is a name that can
be moved; two sessions naming the same tag a week apart can run different
bytes, and nothing in either receipt would say so. That is the same reason the
compose files refuse `qdrant:latest`, and the reason `POD_IMAGE` was pinned
rather than floated.

The one rule worth stating on its own: **a missing digest is never a reason to
fall back to a tag.** Falling back would be the exact substitution the lock
file exists to prevent, and it would be invisible -- the session would run, the
numbers would look fine, and the receipt would name an image nobody can
reproduce. `reference()` raises instead, and the caller decides whether to use
the documented fallback base image explicitly.
"""

import os

LOCK_NAME = os.path.join("docker", "pod", "IMAGE.lock")


class ImageLockError(RuntimeError):
    """The lock cannot answer which bytes to run."""


def lock_path(root=None):
    return os.path.join(root or ".", LOCK_NAME)


def read_lock(root=None):
    """The lock file as a dict. Missing file gives an empty dict."""
    path = lock_path(root)
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def is_baked(root=None):
    """True when the lock names a real digest."""
    d = read_lock(root).get("digest") or ""
    return d.startswith("sha256:")


def reference(root=None):
    """`ghcr.io/owner/oneground-pod@sha256:...`, or raise.

    Raises rather than returning the tag or the fallback, because a session
    that silently ran a different image than the one it recorded is worse than
    a session that did not start.
    """
    lock = read_lock(root)
    if not lock:
        raise ImageLockError(
            f"no {LOCK_NAME}. The pre-baked pod image is described there; "
            "build it with the `pod image` workflow, or run the session "
            "against the fallback base image explicitly.")
    digest = lock.get("digest") or ""
    image = lock.get("image") or ""
    if not digest:
        raise ImageLockError(
            f"{LOCK_NAME} has no digest: the image has not been built yet. "
            "Push the branch so .github/workflows/pod-image.yml builds it, "
            "copy the digest from the job summary into the lock, and commit. "
            "Until then a session must name the fallback image explicitly -- "
            "this does not fall back on its own, because a tag substituted "
            "for a digest is the thing the lock exists to prevent.")
    if not digest.startswith("sha256:"):
        raise ImageLockError(
            f"{LOCK_NAME} digest is {digest!r}, which is not a sha256 "
            "reference. Sessions pin bytes, not names.")
    if not image:
        raise ImageLockError(f"{LOCK_NAME} has a digest but no image name.")
    stated = lock.get("reference")
    built = f"{image}@{digest}"
    if stated and stated != built:
        raise ImageLockError(
            f"{LOCK_NAME} is inconsistent: reference={stated!r} but "
            f"image@digest is {built!r}.")
    return built


def fallback(root=None):
    """The base image a session used before the baked one existed."""
    return read_lock(root).get("fallback_image") or ""


def describe(root=None):
    """What `pod plan` prints, and what the report records.

    Always says which of the two it is. "the image" is not a fact a reader can
    check; a digest is.
    """
    lock = read_lock(root)
    if is_baked(root):
        return {
            "baked": True,
            "reference": reference(root),
            "image": lock.get("image"),
            "digest": lock.get("digest"),
            "tag": lock.get("tag") or None,
            "note": "pre-baked oneground pod image, pinned by digest",
        }
    return {
        "baked": False,
        "reference": lock.get("fallback_image") or None,
        "image": lock.get("fallback_image") or None,
        "digest": None,
        "tag": None,
        "note": ("the pre-baked image has no digest in "
                 f"{LOCK_NAME} yet, so this session runs the fallback base "
                 "image and installs Postgres, pgvector, Qdrant and the venv "
                 "at run time, as every session through task 016 did"),
    }
