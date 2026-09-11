"""What a source calls the five fields the fixture builder needs.

The builder needs exactly five things from a source record: an id, a title, a
body, a category label, and a date. arXiv calls them `id`, `title`,
`abstract`, `categories`, `update_date`. Stack Exchange calls them `Id`,
`Title`, `Body`, `Tags`, `CreationDate`. Nothing else about the builder cares
which is which, so the spec declares the mapping and the builder reads it.

**The record keys are not renamed.** `sample.jsonl.zst` is a receipt, and its
bytes are `json.dumps` of the record dicts -- so canonicalising arXiv's
`abstract` to `body` would change every digest arxiv-150k has published. A
reader returns records under its *own* field names, and this map tells the
generic code which name to look under. That is why the defaults below are
arXiv's: a spec with no `field_map` behaves exactly as it did before task 016,
byte for byte.
"""

CANONICAL = ("id", "title", "body", "categories", "date")

# arXiv's names, so an existing spec needs no `field_map` to keep working.
DEFAULTS = {
    "id": "id",
    "title": "title",
    "body": "abstract",
    "categories": "categories",
    "date": "update_date",
}

# The date below which a record counts as "before" for the drift pair. arXiv's
# published characterization was computed at this value, so it is the default
# and changing it for arxiv-150k would contradict the spec's own numbers.
DEFAULT_DRIFT_CUTOFF = "2019-01-01"


class FieldMapError(ValueError):
    """A spec's `source.field_map` does not name all five fields."""


def field_map(spec):
    """The canonical -> source-field-name map for this spec.

    Unknown canonical names are refused rather than ignored: a typo in
    `field_map` that silently fell back to arXiv's `update_date` would build a
    fixture whose drift pair was computed on a field that does not exist.
    """
    declared = ((spec.get("source") or {}).get("field_map")) or {}
    unknown = sorted(set(declared) - set(CANONICAL))
    if unknown:
        raise FieldMapError(
            f"source.field_map names {unknown}, which the builder does not "
            f"use; it needs exactly {list(CANONICAL)}")
    fm = dict(DEFAULTS)
    fm.update(declared)
    return fm


def drift_cutoff(spec):
    """The date the drift pair splits on, as an ISO `YYYY-MM-DD` string.

    Declared per fixture because the right cutoff is a property of the corpus:
    it is chosen to split the corpus roughly 60/40, and arXiv's 2019 boundary
    is nowhere near that for a corpus that starts in 2008.
    """
    return ((spec.get("sampling") or {}).get("drift_cutoff")
            or DEFAULT_DRIFT_CUTOFF)
