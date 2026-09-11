"""The Stack Exchange reader, on a synthetic dump.

The corpus itself is 34 GB and lives on the pod, so everything here runs
against parquet shards written by the test. What is being checked is the
sampling *rule* -- questions only, stratified by year in proportion to volume,
uniform within year, seeded and reproducible -- which is a property of the code
and not of the data.

`clean_body` is checked against real Stack Overflow shapes (fenced code,
indented code, links, HTML) because the rule it implements is stated in the
fixture spec and a fixture whose text rule drifted from its spec would publish
values for a corpus it does not describe.
"""

from collections import Counter

import pytest

from .stackexchange import (QUESTION, clean_body, sample_records, shard_paths,
                            year_of)

pytest.importorskip("pyarrow")


# ------------------------------------------------------------- clean_body
def test_fenced_code_is_dropped():
    assert clean_body("before\n```\nrm -rf /\n```\nafter") == "before after"


def test_indented_code_is_dropped():
    assert clean_body("why does this fail?\n\n    import os\n    os.exit()\n") \
        == "why does this fail?"


def test_a_link_keeps_its_label_and_loses_its_url():
    assert clean_body("see [the docs](https://example.invalid/x) now") \
        == "see the docs now"


def test_residual_html_is_stripped():
    assert clean_body("a <b>bold</b> claim") == "a bold claim"


def test_whitespace_is_collapsed():
    # No line here starts with a tab or four spaces: that would be an indented
    # code block, which the previous test shows is dropped rather than
    # collapsed.
    assert clean_body("a\n\n b   c\r\nd") == "a b c d"


def test_an_empty_or_null_body_is_empty_not_an_error():
    assert clean_body(None) == ""
    assert clean_body("") == ""


def test_year_of_reads_the_leading_four_digits():
    assert year_of("2016-03-28T11:22:33.444") == 2016
    assert year_of(None) is None
    assert year_of("not a date") is None


# ------------------------------------------------------- a synthetic dump
def _write_dump(tmp_path, per_year, n_shards=3):
    """A parquet dump shaped like mikex86/stackoverflow-posts.

    Answers are interleaved with questions, as in the real dump, so the
    PostTypeId filter is exercised rather than assumed.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = []
    pid = 0
    for year, n in sorted(per_year.items()):
        for i in range(n):
            pid += 1
            rows.append({
                "Id": pid, "PostTypeId": QUESTION,
                "Title": f"How do I do thing {pid} in year {year}?",
                "Body": "This is a question body. " * 20,
                "Tags": ["python", "tag%d" % (i % 7)],
                "CreationDate": f"{year}-06-15T12:00:00.000",
                "ContentLicense": "CC BY-SA 4.0",
            })
            pid += 1
            rows.append({                      # an answer, must be ignored
                "Id": pid, "PostTypeId": 2, "Title": None,
                "Body": "This is an answer body. " * 20, "Tags": [],
                "CreationDate": f"{year}-06-15T12:00:00.000",
                "ContentLicense": "CC BY-SA 4.0",
            })

    d = tmp_path / "dump"
    d.mkdir()
    per = (len(rows) + n_shards - 1) // n_shards
    for s in range(n_shards):
        chunk = rows[s * per:(s + 1) * per]
        if not chunk:
            continue
        tbl = pa.Table.from_pylist(chunk)
        pq.write_table(tbl, str(d / f"posts-{s:05d}-of-{n_shards:05d}.parquet"))
    return str(d)


def _spec(n, **over):
    samp = {"year_range": [2008, 2023], "min_body_chars": 200,
            "body_chars": 500, "reservoir_per_year": 5000}
    samp.update(over)
    return {"sampling": samp}


def test_answers_are_excluded_on_a_synthetic_dump(tmp_path):
    src = _write_dump(tmp_path, {2010: 200, 2020: 200})
    recs = sample_records(src, _spec(50), 50, seed=1)
    assert len(recs) == 50
    assert all(r["title"] for r in recs)
    assert all(r["body"].startswith("This is a question body")
               for r in recs), "an answer body reached the sample"


def test_years_are_allocated_in_proportion_to_volume_on_a_synthetic_dump(tmp_path):
    """3:1 in the corpus must come out 3:1 in the sample."""
    src = _write_dump(tmp_path, {2012: 900, 2019: 300})
    recs = sample_records(src, _spec(400), 400, seed=7)
    got = Counter(r["creation_date"][:4] for r in recs)
    assert got["2012"] == 300 and got["2019"] == 100, got


def test_the_same_seed_gives_the_same_sample_on_a_synthetic_dump(tmp_path):
    src = _write_dump(tmp_path, {2011: 400, 2018: 400})
    a = sample_records(src, _spec(120), 120, seed=20260911)
    b = sample_records(src, _spec(120), 120, seed=20260911)
    assert [r["id"] for r in a] == [r["id"] for r in b]


def test_a_different_seed_gives_a_different_sample_on_a_synthetic_dump(tmp_path):
    src = _write_dump(tmp_path, {2011: 400, 2018: 400})
    a = sample_records(src, _spec(120), 120, seed=1)
    b = sample_records(src, _spec(120), 120, seed=2)
    assert [r["id"] for r in a] != [r["id"] for r in b]


def test_years_outside_the_range_are_excluded_on_a_synthetic_dump(tmp_path):
    src = _write_dump(tmp_path, {2007: 500, 2015: 500})
    recs = sample_records(src, _spec(100, year_range=[2008, 2023]), 100, seed=3)
    assert {r["creation_date"][:4] for r in recs} == {"2015"}


def test_a_short_body_is_excluded_on_a_synthetic_dump(tmp_path):
    src = _write_dump(tmp_path, {2015: 300})
    # Every body is 500 chars of "This is a question body. ", so a floor above
    # that excludes everything and the reader must say so rather than return
    # an empty sample.
    with pytest.raises(ValueError) as e:
        sample_records(src, _spec(10, min_body_chars=100000), 10, seed=1)
    assert "no eligible posts" in str(e.value)


def test_a_reservoir_smaller_than_the_quota_is_refused_not_biased(tmp_path):
    """Silently drawing 100 out of a reservoir of 10 would bias that year
    towards whatever the reservoir happened to keep."""
    src = _write_dump(tmp_path, {2013: 2000})
    with pytest.raises(ValueError) as e:
        sample_records(src, _spec(500, reservoir_per_year=10), 500, seed=1)
    msg = str(e.value)
    assert "reservoir_per_year" in msg and "2013" in msg
    assert "do not lower the quota" in msg


def test_the_record_carries_the_per_post_licence_on_a_synthetic_dump(tmp_path):
    """The fixture's CC BY-SA notice reports the distribution over the sample,
    so the reader has to carry it per record rather than assume one value."""
    src = _write_dump(tmp_path, {2016: 200})
    recs = sample_records(src, _spec(20), 20, seed=1)
    assert all(r["content_license"] == "CC BY-SA 4.0" for r in recs)


def test_tags_become_a_space_separated_category_string(tmp_path):
    """`primary_category` splits on whitespace and takes the first token, so
    the first tag is the primary category -- the same shape arXiv's
    `categories` field has."""
    src = _write_dump(tmp_path, {2016: 200})
    recs = sample_records(src, _spec(20), 20, seed=1)
    assert all(r["categories"].split()[0] == "python" for r in recs)


def test_shards_are_read_in_sorted_filename_order(tmp_path):
    src = _write_dump(tmp_path, {2014: 60}, n_shards=3)
    paths = shard_paths(src)
    assert paths == sorted(paths)
    assert len(paths) == 3
