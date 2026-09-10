# corpora/

Characterization tooling and public corpus loaders. This is where a corpus of
embeddings is turned into the measurements the rest of the tool reasons about,
and where the loaders and builders for the public corpora live —
`build_fixture.py` consumes a spec from `fixtures/` and produces every artifact
that spec describes, deterministically from its seeds. Canonical fixture builds
are CPU and follow a single deterministic path; GPU may be used for exploration
only, never for a published artifact.
