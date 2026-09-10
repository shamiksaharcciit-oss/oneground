# fixtures/

Public corpora with frozen ground truth and published values. Each fixture is
one directory (`fixtures/<id>/`) built from a spec (`fixtures/<id>.fixture.yaml`)
by `corpora/build_fixture.py`, plus a `MANIFEST.sha256` carrying the sha256 of
every artifact it contains. Fixtures exist for learning and for verifying that
an installation reproduces published values — they are never a leaderboard, and
nothing is ever recommended from them. Every field in a spec is either a
*receipt* (re-derivable from the seeds and rules recorded beside it) or
*declared* (upstream bytes frozen). Values marked `TO_BE_FILLED` are set by the
first canonical build and never edited by hand afterwards.
