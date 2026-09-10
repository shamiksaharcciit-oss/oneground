#!/usr/bin/env python3
"""
Validate .github/workflows/pages.yml without running it.

    python .github/scripts/validate-pages-workflow.py

**Run this after any edit to the Pages workflow.** A workflow is only really
tested by pushing it, and a broken one fails in the place where a failure is
most expensive; these are the things that can be checked before that:

  * the file parses, and carries the keys a Pages deployment needs -- the
    `github-pages` environment, `pages: write` and `id-token: write`, and a
    concurrency group that does not cancel a deploy in flight;
  * the upload step points at `site/teaser` and sets `include-hidden-files`,
    without which the action's tar drops `.nojekyll` from the artifact and
    says nothing;
  * every `uses:` is pinned to a 40-hex commit SHA rather than a tag, **each
    SHA is a real commit in the repository it names, and each matches the
    version its trailing comment claims** -- so a pin cannot quietly drift
    from the version beside it;
  * the one `run:` step names a script that exists and imports nothing outside
    the standard library, so the runner installs nothing;
  * the files the artifact depends on are present, and CNAME is the domain and
    nothing else.

Reads only. Needs PyYAML, and network access to api.github.com for the four
SHA checks -- those are reported as `couldnt_check` when the API cannot be
reached, and never as a failure, because an unreachable API says nothing about
the workflow. Exit status is non-zero only if something actually failed.
"""
import ast
import json
import os
import re
import sys
import urllib.request

import yaml

# Paths are resolved from the repository root, two levels up from this file,
# so the tool gives the same answer from any working directory.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF = os.path.join(ROOT, ".github", "workflows", "pages.yml")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

ok = True


def check(label, good, detail=""):
    global ok
    print(f"  {'OK  ' if good else 'FAIL'} {label}" + (f"   {detail}" if detail else ""))
    ok = ok and good
    return good


def api(url):
    req = urllib.request.Request(url, headers={"User-Agent": "oneground-t3"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main():
    text = open(WF, encoding="utf-8").read()
    doc = yaml.safe_load(text)

    print("structure")
    # PyYAML resolves the bare key `on` to the boolean True.
    triggers = doc.get("on", doc.get(True))
    check("parses as YAML", isinstance(doc, dict))
    check("name", doc.get("name") == "pages", doc.get("name"))
    check("push to main", triggers.get("push", {}).get("branches") == ["main"])
    check("workflow_dispatch", "workflow_dispatch" in triggers)
    perms = doc.get("permissions", {})
    check("permissions pages:write + id-token:write + contents:read",
          perms.get("pages") == "write" and perms.get("id-token") == "write"
          and perms.get("contents") == "read", str(perms))
    conc = doc.get("concurrency", {})
    check("concurrency does not cancel in flight",
          conc.get("cancel-in-progress") is False, str(conc))

    job = doc["jobs"]["deploy"]
    check("job declares the github-pages environment",
          job.get("environment", {}).get("name") == "github-pages")
    check("environment url comes from the deploy step",
          "steps.deployment.outputs.page_url" in
          str(job.get("environment", {}).get("url", "")))

    steps = job["steps"]
    upload = [s for s in steps if "upload-pages-artifact" in str(s.get("uses"))]
    check("uploads exactly one artifact", len(upload) == 1)
    if upload:
        w = upload[0].get("with", {})
        check("uploads site/teaser", w.get("path") == "site/teaser", w.get("path"))
        check("include-hidden-files is on (or .nojekyll is dropped)",
              w.get("include-hidden-files") is True, str(w.get("include-hidden-files")))

    print("\npins")
    comments = dict(re.findall(r"uses:\s*(\S+)\s*#\s*(v[\d.]+)", text))
    for step in steps:
        u = step.get("uses")
        if not u:
            continue
        repo, _, ref = u.partition("@")
        if not check(f"{repo} pinned by SHA", bool(SHA_RE.match(ref)), ref):
            continue
        want_tag = comments.get(u)
        try:
            commit = api(f"https://api.github.com/repos/{repo}/commits/{ref}")
            exists = commit.get("sha") == ref
        except Exception as e:
            print(f"       couldnt_check: {type(e).__name__} {e}")
            continue
        check(f"{repo} SHA is a real commit", exists, ref[:12] + "…")
        if want_tag:
            try:
                r = api(f"https://api.github.com/repos/{repo}/git/ref/tags/{want_tag}")
                o = r["object"]
                tag_sha = (api(o["url"])["object"]["sha"]
                           if o["type"] == "tag" else o["sha"])
                check(f"{repo} SHA is {want_tag}", tag_sha == ref, want_tag)
            except Exception as e:
                print(f"       couldnt_check {want_tag}: {type(e).__name__} {e}")

    print("\nthe run: step")
    runs = [s for s in steps if s.get("run")]
    check("exactly one run step", len(runs) == 1)
    script = runs[0]["run"].split()[-1] if runs else ""
    script_path = os.path.join(ROOT, script)
    check("its script exists", os.path.exists(script_path), script)
    if os.path.exists(script_path):
        tree = ast.parse(open(script_path, encoding="utf-8").read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or "").split(".")[0])
        third_party = imported - set(sys.stdlib_module_names) - {""}
        check("script is stdlib-only, so the runner installs nothing",
              not third_party, ", ".join(sorted(imported)))

    print("\nthe files the workflow depends on")
    for p in ("site/teaser/.nojekyll", "site/teaser/CNAME",
              "site/teaser/index.html", "site/teaser/data/MANIFEST.sha256"):
        check(p, os.path.exists(os.path.join(ROOT, p)))
    cname = open(os.path.join(ROOT, "site/teaser/CNAME"),
                 encoding="utf-8").read().strip()
    check("CNAME is the domain and nothing else",
          cname == "oneground.oneproof.dev", repr(cname))

    print("\nALL CHECKS PASSED" if ok else "\nCHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
