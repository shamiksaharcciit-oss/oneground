"""Near-duplicate rate over a corpus of documents, before any chunking.

`docs/CHUNKING.md` defines near-duplicate rate on *chunk vectors*, at a stated
cosine threshold, by exact k-NN. That is the right measure for comparing
chunking strategies and it is what task 031 will use. It cannot be the
baseline those comparisons are read against, for a plain reason: a chunk
vector exists only once a chunking has been chosen, so a duplicate rate
computed from chunk vectors already contains the strategy under test.

So the baseline is lexical and model-free: Jaccard similarity over word
shingles of the extracted text. It depends on no embedding model, no chunk
size and no threshold anyone could tune after seeing a result. What it
answers is the question a reader of a chunking comparison actually has --
*how much of this duplication was already in the corpus?* -- and on a corpus
of SEC filings the answer is not incidental. A 10-K repeats the previous
year's 10-K at length, and thousands of filers repeat each other's risk
factor and accounting-policy boilerplate nearly verbatim.

It is reported as a lexical rate and never compared directly against a cosine
rate on chunk vectors. Two different measures of two different things, both
published, neither converted into the other.

**Exactness.** MinHash with LSH banding proposes candidate pairs; every
candidate is then scored by exact Jaccard on the full shingle sets, and only
exact scores are reported. LSH can in principle miss a pair, so the banding
is chosen to make that negligible at the reported threshold and the
probability is published beside the rate rather than assumed away -- see
`recall_at`. All-pairs exact would be 50 million set intersections over
documents of 60,000 shingles each, which is not a measurement anyone can
afford; this is the honest version of affording it.
"""

import hashlib

import numpy as np

SHINGLE_WORDS = 5
NUM_PERM = 128
BANDS = 32
ROWS = NUM_PERM // BANDS          # 4
THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.90)
PRIMARY_THRESHOLD = 0.80
EXACT_RECALL = 0.999
"""The rate is reported across a range, not at one cutoff, and why.

0.80 stays the primary threshold, for comparability with whatever
`docs/CHUNKING.md`'s chunk-vector measure settles on. But a single high
cutoff would report this corpus as having no duplication at all, which is
false. Measured before the build, on three filers' consecutive 10-Ks
(Nicholas Financial, Medallion Financial, Henry Schein), the same company's
adjacent-year filings score Jaccard 0.49 to 0.62, and two years apart 0.34 to
0.50. The repetition is massive and sits below 0.80.

The range was fixed from that pilot and written down before the corpus was
built, so that the cutoffs could not be moved afterwards to suit a result.
The pilot measured three companies and is not the rate; the build measures
all 10,000 and is.

Where LSH recall falls below EXACT_RECALL the rate is published as a lower
bound rather than a rate -- at 0.50 the banding proposes a true pair with
probability 0.874, so a 0.50 figure can only be too small. That is a
couldn't-check on part of the number and it is labelled, not rounded up.
"""

_PRIME = np.uint64(4294967311)    # the first prime above 2**32
_BASE = np.uint64(1000003)        # polynomial base for the rolling shingle hash
_PERM_BLOCK = 32                  # permutations hashed at once, to bound memory

# Everything below stays inside uint64 by construction: shingle hashes and the
# permutation coefficients are all below _PRIME < 2**32 + 16, so the product
# a*x peaks near 1.8e19 against uint64's 1.8446744e19 and never wraps. This is
# the reason for 32-bit hashing rather than 64-bit: a 64-bit MinHash needs
# big-integer arithmetic, which at 10,000 documents of 60,000 shingles each is
# hours of Python. The cost is a birthday collision rate of about 1 in 2**32
# per shingle pair, far below the precision the rate is reported to.


def recall_at(jaccard, bands=BANDS, rows=ROWS):
    """Probability LSH proposes a pair at this true Jaccard similarity.

    A band matches when all `rows` of its rows agree, with probability
    s**rows; a pair is proposed unless every band misses. Published beside
    the rate so the reader can see what "exact on candidates" is worth: at
    the primary threshold of 0.80 this is above 0.999.
    """
    return 1.0 - (1.0 - jaccard ** rows) ** bands


def _word_id(word, cache):
    """A stable 32-bit id for a word, memoised across the corpus.

    Memoised because it has to be: a 10-K holds around 60,000 words and the
    corpus 10,000 filings, so hashing every occurrence separately is 600
    million digests. Filings repeat each other heavily, which is the very
    property being measured, so the cache hits almost always.
    """
    v = cache.get(word)
    if v is None:
        v = int.from_bytes(hashlib.blake2b(word.encode("utf-8"),
                                           digest_size=4).digest(), "little")
        cache[word] = v
    return v


def shingles(text, k=SHINGLE_WORDS, cache=None):
    """The set of k-word shingles of a document, as 32-bit hashes.

    Lower-cased and whitespace-normalised: case and spacing are what two
    filings agreeing on boilerplate are least likely to agree on, and keeping
    them would report a difference in typography as a difference in content.

    The shingle hash is a polynomial over the words' ids, evaluated with k
    vector multiplies rather than a digest per shingle.
    """
    cache = {} if cache is None else cache
    words = text.lower().split()
    if len(words) < k:
        return np.empty(0, dtype=np.uint64)
    ids = np.fromiter((_word_id(w, cache) for w in words),
                      dtype=np.uint64, count=len(words))
    n = len(words) - k + 1
    h = np.zeros(n, dtype=np.uint64)
    for t in range(k):
        h = (h * _BASE + ids[t:t + n]) % _PRIME
    return np.unique(h)


def _permutations(seed, num_perm=NUM_PERM):
    """Seeded (a, b) pairs for the universal hash family a*x + b mod p."""
    rng = np.random.default_rng(seed)
    a = rng.integers(1, int(_PRIME), size=num_perm).astype(np.uint64)
    b = rng.integers(0, int(_PRIME), size=num_perm).astype(np.uint64)
    return a, b


def signature(shingle_hashes, a, b):
    """One document's MinHash signature, in blocks to bound memory."""
    if shingle_hashes.size == 0:
        return np.full(a.size, np.iinfo(np.uint64).max, dtype=np.uint64)
    x = shingle_hashes[:, None]
    out = np.empty(a.size, dtype=np.uint64)
    for lo in range(0, a.size, _PERM_BLOCK):
        hi = min(lo + _PERM_BLOCK, a.size)
        out[lo:hi] = ((x * a[None, lo:hi] + b[None, lo:hi]) % _PRIME).min(axis=0)
    return out


def signatures(texts, seed):
    """Signatures and exact shingle sets for a corpus, in input order."""
    a, b = _permutations(seed)
    cache = {}
    sets, sigs = [], []
    for t in texts:
        s = shingles(t, cache=cache)
        sets.append(s)
        sigs.append(signature(s, a, b))
    return (np.vstack(sigs) if sigs else np.empty((0, NUM_PERM), np.uint64)), sets


def candidate_pairs(sigs, bands=BANDS, rows=ROWS):
    """Pairs sharing a whole band. Deterministic: sorted, no set iteration."""
    pairs = set()
    n = sigs.shape[0]
    for band in range(bands):
        block = sigs[:, band * rows:(band + 1) * rows]
        keys = {}
        for i in range(n):
            k = block[i].tobytes()
            keys.setdefault(k, []).append(i)
        for bucket in keys.values():
            if len(bucket) < 2:
                continue
            for x in range(len(bucket)):
                for y in range(x + 1, len(bucket)):
                    pairs.add((bucket[x], bucket[y]))
    return sorted(pairs)


def exact_jaccard(sa, sb):
    """|A and B| / |A or B| on two sorted unique uint64 arrays."""
    if sa.size == 0 or sb.size == 0:
        return 0.0
    inter = np.intersect1d(sa, sb, assume_unique=True).size
    union = sa.size + sb.size - inter
    return inter / union if union else 0.0


def near_duplicate_rate(texts, seed, thresholds=THRESHOLDS):
    """The receipt: the share of documents with a near-duplicate, per threshold.

    Returns the rate at each threshold, the number of candidate pairs LSH
    proposed, how many survived exact scoring, and the LSH recall at each
    threshold -- everything needed to read the number without trusting it.
    """
    sigs, sets = signatures(texts, seed)
    cands = candidate_pairs(sigs)
    scored = [(i, j, exact_jaccard(sets[i], sets[j])) for i, j in cands]

    n = len(texts)
    out = {}
    for t in thresholds:
        has = np.zeros(n, dtype=bool)
        npairs = 0
        for i, j, s in scored:
            if s >= t:
                has[i] = has[j] = True
                npairs += 1
        recall = recall_at(t)
        out[f"{t:.2f}"] = dict(rate=float(has.mean()) if n else 0.0,
                               documents=int(has.sum()),
                               pairs=npairs,
                               lsh_recall=round(recall, 6),
                               kind="exact" if recall >= EXACT_RECALL
                                    else "lower bound")
    return dict(documents=n,
                shingle_words=SHINGLE_WORDS,
                num_perm=NUM_PERM, bands=BANDS, rows=ROWS, seed=seed,
                candidate_pairs=len(cands),
                measure="lexical Jaccard over word shingles, exact on candidates",
                primary_threshold=PRIMARY_THRESHOLD,
                by_threshold=out)
