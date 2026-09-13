"""What CI checks about the pod image. Task 017d.

Two checks, and deliberately **not** a third.

`pod image` run #4 failed because CI rebuilt the image and compared the new
digest against the committed one. That check cannot pass in a steady state.
The base resolved identically both times
(`sha256:c7ff5829...`), but our own apt and pip layers pull from services that
do not promise byte-identical responses over time, and layer metadata carries
build timestamps regardless. Run #1 produced `sha256:81567d58...`; run #4
produced `sha256:12bd6a3e...` from the same Dockerfile and the same
requirements.txt. Neither is wrong. The committed digest names an image that
exists, was pushed, and has been pulled and run by two pod sessions -- 017c
proved Postgres starts on it -- so a red run sat next to a good image on every
push.

Rebuild-to-compare answers "are these bytes reproducible", which they are not
and were never going to be. What a reader actually needs to know is:

    1. pullable   the digest the lock names still exists and can be fetched.
                  This is the question a session asks, and the only one whose
                  answer changes what a session does.

    2. co-change  if a commit touched the image's build inputs, the lock must
                  have changed in the same range. This is what keeps the pin
                  honest: not "does a rebuild reproduce it" but "did whoever
                  changed the recipe also re-lock what it produces".

**CI never builds the image.** Building it is a local, deliberate act --
see `docker/pod/rebuild.sh` -- because the digest it produces has to be copied
into the lock by the person who changed the Dockerfile, in the same commit.

THE TRIGGER SET
---------------
Derived from the Dockerfile rather than declared, so it cannot drift from what
the build actually reads: the Dockerfile itself, plus every path it `COPY`s or
`ADD`s. Today that is exactly `requirements.txt`.

It is deliberately NOT "everything under docker/pod/". The session scripts that
sync at run time -- `corpora/run_verify_pod.sh`, `restart_engine.sh` and the
like -- are not in the image and cannot change its bytes. Commit 696dd03
touched only those and fired a full image workflow for nothing.

`docker/pod/IMAGE.lock` is not a build input either. It is the build's output,
recorded; requiring it to change when it changes would be circular.
"""

import os
import re
import subprocess

from .image import LOCK_NAME, read_lock, reference

DOCKERFILE = os.path.join("docker", "pod", "Dockerfile")
WORKFLOW = os.path.join(".github", "workflows", "pod-image.yml")

# `COPY --chown=x:y --from=stage src... dest` -- flags first, destination last.
_COPY_RE = re.compile(r"^\s*(COPY|ADD)\s+(.*)$", re.IGNORECASE)


class ImageCheckError(RuntimeError):
    """A check could not be run at all, as distinct from failing."""


def _logical_lines(text):
    """Dockerfile lines with backslash continuations joined, comments dropped."""
    out, buf = [], ""
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not buf and line.lstrip().startswith("#"):
            continue
        if line.rstrip().endswith("\\"):
            buf += line.rstrip()[:-1] + " "
            continue
        out.append(buf + line)
        buf = ""
    if buf:
        out.append(buf)
    return out


def copy_sources(dockerfile_text):
    """Every path a COPY or ADD reads from the build context.

    Skips `--from=` copies: those read from an earlier build stage, not from
    the context, so a file in the repository does not affect them. Skips
    remote ADD sources for the same reason -- a URL is not a repo path.
    """
    found = []
    for line in _logical_lines(dockerfile_text):
        m = _COPY_RE.match(line)
        if not m:
            continue
        parts = m.group(2).split()
        flags = [p for p in parts if p.startswith("--")]
        operands = [p for p in parts if not p.startswith("--")]
        if any(f.lower().startswith("--from=") for f in flags):
            continue
        if len(operands) < 2:
            continue
        for src in operands[:-1]:                 # the last operand is dest
            if src.startswith(("http://", "https://")):
                continue
            found.append(src.strip('"').lstrip("./"))
    return found


def build_inputs(root=None):
    """Sorted repo-relative paths whose change should re-lock the image.

    The Dockerfile plus whatever it copies. Raises if the Dockerfile is not
    there, because silently returning a short list would make the co-change
    check pass for the wrong reason.
    """
    root = root or "."
    path = os.path.join(root, DOCKERFILE)
    if not os.path.exists(path):
        raise ImageCheckError(f"{DOCKERFILE} is missing; cannot derive the "
                              "image's build inputs")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    inputs = {DOCKERFILE.replace(os.sep, "/")}
    inputs.update(copy_sources(text))
    return sorted(inputs)


# ------------------------------------------------------------ 1. pullability
# Two ways to ask the registry for a manifest, tried in order. Both read the
# manifest and pull no layers, which is what keeps this cheap enough for every
# push -- the image is gigabytes.
#
# `buildx imagetools` is first because `docker manifest inspect` cannot read an
# OCI manifest on an older client. Measured here on Docker 20.10.17:
#
#     $ docker manifest inspect alpine:latest
#     unsupported manifest media type and no default available:
#         application/vnd.oci.image.manifest.v1+json
#
# against a *public* image that plainly exists. Our own image is built by
# buildx and pushed to GHCR, so it is an OCI manifest too. A check that
# depended on the client's manifest-format support would have gone red for a
# reason that has nothing to do with whether a session can start -- which is
# the same class of false red this task exists to remove.
_INSPECTORS = (
    ["docker", "buildx", "imagetools", "inspect", "--raw"],
    ["docker", "manifest", "inspect"],
)


def pullable(ref=None, root=None, runner=None):
    """(ok, detail). Does the registry still serve the digest the lock names?"""
    run = runner or _run
    if ref is None:
        ref = reference(root)

    attempts = []
    for base in _INSPECTORS:
        cmd = list(base) + [ref]
        code, out, err = run(cmd)
        if code == 0:
            return True, "%s is pullable (%s)" % (ref, " ".join(base[:3]))
        attempts.append((" ".join(base), (err or out or "").strip()))

    lines = [f"the digest in {LOCK_NAME} is not pullable.",
             f"  reference: {ref}"]
    for cmd, why in attempts:
        lines.append(f"  {cmd}: {why or '(no output)'}")
    lines.append(
        "A session pins this digest; if the registry cannot serve it, no "
        "session can start. Rebuild and re-lock with docker/pod/rebuild.sh.")
    return False, "\n".join(lines)


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


# -------------------------------------------------------------- 2. co-change
def changed_files(base, head, root=None, runner=None):
    """Repo-relative paths changed in `base..head`.

    A missing or unknown base (a first push, a force-push, a shallow clone
    whose grafts hide it) is reported rather than guessed at: returning an
    empty list would silently pass the co-change check.
    """
    run = runner or _run
    cwd = root or "."
    code, out, err = run(["git", "-C", cwd, "diff", "--name-only",
                          f"{base}..{head}"])
    if code != 0:
        raise ImageCheckError(
            f"could not diff {base}..{head}: {(err or out).strip()}")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def co_change(changed, inputs, lock_name=None):
    """(ok, detail). If a build input moved, the lock must have moved with it.

    The rule is one-directional on purpose. Touching the Dockerfile without
    re-locking is drift, and that fails. Re-locking without touching the
    Dockerfile is fine -- a rebuild against the same recipe produces a new,
    equally valid digest, which is exactly what run #4 demonstrated.
    """
    lock_name = (lock_name or LOCK_NAME).replace(os.sep, "/")
    changed = {c.replace(os.sep, "/") for c in changed}
    inputs = {i.replace(os.sep, "/") for i in inputs}

    touched = sorted(changed & inputs)
    if not touched:
        return True, ("no image build input changed in this range; the lock "
                      "does not need to move")
    if lock_name in changed:
        return True, ("build inputs changed (%s) and %s changed with them"
                      % (", ".join(touched), lock_name))
    return False, (
        "the image's build inputs changed but %s did not.\n"
        "  changed: %s\n"
        "  %s was not updated in this range.\n"
        "\n"
        "The lock records what the recipe produces, so the two move together "
        "or the pin stops describing the image. CI does not rebuild -- builds "
        "are not byte-reproducible, so a rebuilt digest would differ from a "
        "correct lock and prove nothing.\n"
        "\n"
        "Rebuild locally and commit the lock with the change:\n"
        "    bash docker/pod/rebuild.sh\n"
        % (lock_name, ", ".join(touched), lock_name))


# --------------------------------------------------------------- re-locking
def write_lock_digest(image, digest, tag=None, root=None, path=None):
    """Rewrite the lock's key=value lines in place, keeping every comment.

    The lock is mostly prose -- why a digest and not a tag, what run #4 showed,
    what the bootstrap case is -- and that prose is the reason the file is
    worth reading. A rewrite that dropped it to emit four clean lines would
    make the file cheaper to generate and worthless to a reader.

    Returns the list of (key, old, new) it changed.
    """
    path = path or os.path.join(root or ".", LOCK_NAME)
    if not digest.startswith("sha256:"):
        raise ImageCheckError(f"{digest!r} is not a sha256 reference")
    wanted = {"image": image,
              "digest": digest,
              "reference": f"{image}@{digest}"}
    if tag:
        wanted["tag"] = tag

    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines(True)

    changed, seen = [], set()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") or "=" not in line:
            continue
        key = line.partition("=")[0].strip()
        if key not in wanted:
            continue
        seen.add(key)
        old_v = line.partition("=")[2].strip()
        if old_v != wanted[key]:
            changed.append((key, old_v, wanted[key]))
            lines[i] = "%s=%s\n" % (key, wanted[key])

    missing = sorted(set(wanted) - seen)
    if missing:
        raise ImageCheckError(
            f"{path} has no {', '.join(missing)} line to update. The lock is "
            "edited in place rather than regenerated, so the keys have to be "
            "there already.")

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)
    return changed


# ------------------------------------------------------------------- the CLI
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="oneground.pod.imagecheck",
                                 description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inputs", help="print the derived build-input set")
    p = sub.add_parser("pullable", help="the locked digest must be fetchable")
    p.add_argument("--root", default=".")
    c = sub.add_parser("co-change", help="a build-input change must re-lock")
    c.add_argument("--base", required=True)
    c.add_argument("--head", required=True)
    c.add_argument("--root", default=".")
    w = sub.add_parser("relock", help="write a freshly pushed digest into the lock")
    w.add_argument("--image", required=True)
    w.add_argument("--digest", required=True)
    w.add_argument("--tag", default=None)
    w.add_argument("--root", default=".")
    args = ap.parse_args(argv)

    if args.cmd == "relock":
        changed = write_lock_digest(args.image, args.digest, args.tag,
                                    root=args.root)
        if not changed:
            print(f"{LOCK_NAME} already names {args.digest}; nothing to do.")
            return 0
        for key, was, now in changed:
            print("  %s\n    was %s\n    now %s" % (key, was, now))
        print("\n%s updated. Commit it WITH the change that caused the "
              "rebuild -- the co-change check requires them in one range."
              % LOCK_NAME)
        return 0

    if args.cmd == "inputs":
        for p_ in build_inputs():
            print(p_)
        return 0

    if args.cmd == "pullable":
        lock = read_lock(args.root)
        if not (lock.get("digest") or ""):
            # The bootstrap case, kept from task 017: an empty lock is not
            # drift, it is a fixture that has not been built yet. Run #4
            # reached this branch and it behaved correctly.
            print("::warning::%s has no digest yet (bootstrap). Nothing to "
                  "pull; build and lock with docker/pod/rebuild.sh." % LOCK_NAME)
            return 0
        ok, detail = pullable(root=args.root)
        print(detail if ok else "::error::%s" % detail)
        return 0 if ok else 1

    ok, detail = co_change(changed_files(args.base, args.head, args.root),
                           build_inputs(args.root))
    print(detail if ok else "::error::%s" % detail)
    return 0 if ok else 1


if __name__ == "__main__":                                  # pragma: no cover
    import sys
    sys.exit(main())
