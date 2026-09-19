"""The chunking comparison, driven by a requirements file (task 031 step 7).

Three strategies over one declared subsample of sec-filings-10k, paths A and
B, one report. Runnable on a pod or, at a reduced document count, locally.

**Tokenise once, share the offsets.** Every strategy reads the same token
offsets for a document, so tokenising per strategy would triple the CPU cost
of the run and change nothing. On a 100-document sample the shared pass took
82.8 s; doing it three times would have cost 248 s to produce identical
offsets. It is the difference between one CPU cost and three, and at the
corpus scale this run does not attempt it is the difference between a session
and an afternoon.

**Receipts are written the moment each stage completes**, for the reason task
030 learned twice: a run terminated before its last step must leave behind
whatever it had finished, not nothing.
"""

import argparse
import json
import os
import pathlib
import random
import sys
import time

import numpy as np
import yaml
import zstandard as zstd

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground.chunk import measures as M                    # noqa: E402
from oneground.chunk import report as RP                     # noqa: E402
from oneground.chunk import selfretrieval as SR              # noqa: E402
from oneground.chunk import strategies as ST                 # noqa: E402
from oneground.embed import embed, load_model                # noqa: E402
from oneground.receipts import write_json_stable             # noqa: E402


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _lines(path):
    """Stream the compressed corpus a line at a time, holding one line."""
    with open(path, "rb") as f, zstd.ZstdDecompressor().stream_reader(f) as r:
        buf = b""
        while True:
            c = r.read(1 << 22)
            if not c:
                break
            buf += c
            *done, buf = buf.split(b"\n")
            for l in done:
                if l.strip():
                    yield l
        if buf.strip():
            yield buf


def load_documents(path, n, seed):
    """The declared subsample: order by accession, uniform draw under `seed`.

    Two passes, and the second is the point. The first reads only each
    document's accession -- 10,000 short strings -- so the draw can be made
    over the declared ordering; the second materialises only the chosen
    documents.

    A single pass that built every document and then sampled would hold the
    whole corpus: 3.58 GB of text as Python objects, which is 4 to 5 GB of
    process memory to keep 350 MB of it. It does not fit on the developer's
    7.6 GB laptop -- the first attempt at this produced no output at all and
    had to be killed -- and there is no reason to ask a pod for it either.
    The cost is one extra decompression pass, about a minute.
    """
    path = os.path.expanduser(path)
    t0 = time.time()
    accessions = [json.loads(l)["accession"] for l in _lines(path)]
    accessions.sort()
    log(f"corpus: {len(accessions):,} documents indexed in "
        f"{time.time()-t0:.0f}s (accessions only)")
    if n >= len(accessions):
        wanted = set(accessions)
    else:
        wanted = set(random.Random(seed).sample(accessions, n))
    t0 = time.time()
    docs = []
    for l in _lines(path):
        d = json.loads(l)
        if d["accession"] in wanted:
            docs.append(d)
    docs.sort(key=lambda d: d["accession"])
    log(f"subsample materialised in {time.time()-t0:.0f}s")
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("requirements")
    ap.add_argument("--documents", type=int, default=None,
                    help="override the declared subsample size (a smoke run)")
    ap.add_argument("--anchors", type=int, default=None,
                    help="override the declared anchor count (a smoke run)")
    ap.add_argument("--corpus", default=None,
                    help="override corpus.documents (the pod's volume path)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--batch", type=int, default=128)
    args = ap.parse_args()

    req = yaml.safe_load(open(args.requirements, encoding="utf-8"))
    out = pathlib.Path(req["run"]["workdir"])
    out.mkdir(parents=True, exist_ok=True)
    sub = req["corpus"]["subsample"]
    n_docs = args.documents or sub["documents"]

    extraction = RP.Extraction(req["extraction"]["tool"],
                               req["extraction"]["version"])

    t_start = time.time()
    corpus_path = args.corpus or req["corpus"]["documents"]
    docs = load_documents(corpus_path, n_docs, sub["seed"])
    chars = sum(d["chars"] for d in docs)
    log(f"subsample: {len(docs):,} documents, {chars/1e6:.1f} M chars "
        f"(seed {sub['seed']})")

    # ---- tokenise once, share the offsets -------------------------------
    from transformers import AutoTokenizer
    tok = ST.ModelTokens(
        AutoTokenizer.from_pretrained(req["tokenizer"]["model"]),
        name=req["tokenizer"]["model"])
    t0 = time.time()
    offsets = [tok.offsets(d["text"]) for d in docs]
    t_tok = time.time() - t0
    log(f"tokenised once, shared by all three strategies: {t_tok:.0f}s "
        f"({chars/t_tok/1e6:.2f} M chars/s)")

    texts = {d["accession"]: d["text"] for d in docs}
    units = {d["accession"]: [(s["start"], s["end"], s["item"])
                              for s in d["sections"]] for d in docs}

    # ---- anchors, drawn from the RAW text, shared by every strategy -----
    a = dict(req["anchors"])
    if args.anchors:
        a["count"] = args.anchors
    t0 = time.time()
    anchors = SR.sample_anchors(texts, a["count"], a["seed"],
                                min_tokens=a["min_tokens"])
    log(f"anchors: {len(anchors):,} drawn from the raw text in "
        f"{time.time()-t0:.0f}s (seed {a['seed']}); the same set is used for "
        f"every strategy, so the comparison is like for like")

    model, weights_sha = load_model(req["tokenizer"]["model"],
                                    device=args.device, max_seq_length=512)

    # queries: one embedding pass per perturbation, shared across strategies
    queries = {}
    for p in a["perturbations"]:
        qt = SR.perturb(anchors, p, a["seed"])
        t0 = time.time()
        queries[p] = embed(model, qt, args.batch, show_progress_bar=False)
        log(f"  queries[{p}]: {len(qt):,} embedded in {time.time()-t0:.0f}s")

    mm = req["measures"]
    results, cost = [], {}
    for spec in req["strategies"]:
        name, params = spec["name"], spec["params"]
        log(f"--- {name} {params}")
        t0 = time.time()
        chunks = []
        for d, o in zip(docs, offsets):
            u = units[d["accession"]] if name == "structure" else None
            chunks.extend(ST.chunk_document(
                d["text"], name, params, doc_id=d["accession"],
                tokenizer=_Pre(o), units=u))
        t_cut = time.time() - t0
        log(f"  {len(chunks):,} chunks in {t_cut:.0f}s")

        t0 = time.time()
        # Progress ON for the chunk pass. It is the only long quiet stretch
        # in the run -- roughly fifteen minutes per strategy at corpus scale
        # -- and `pod watch` terminates a session whose log has stopped
        # growing. A noisy log is cheaper than a stall watchdog killing a
        # session that was working.
        vecs = embed(model, [c.text for c in chunks], args.batch,
                     show_progress_bar=True)
        t_embed = time.time() - t0
        cost[name] = {"chunks": len(chunks), "cut_seconds": round(t_cut, 1),
                      "embed_seconds": round(t_embed, 1),
                      "chunks_per_second": round(len(chunks) / t_embed, 1)}
        log(f"  embedded in {t_embed:.0f}s "
            f"({len(chunks)/t_embed:.0f} chunks/s)")

        t0 = time.time()
        spans = [(s, e, "item") for d in docs for (s, e, _l) in units[d["accession"]]]
        path_a = M.path_a(
            chunks, spans=spans,
            units=[u for d in docs for u in units[d["accession"]]],
            tokenizer=ST.WhitespaceTokens(), floor=mm["length_floor"],
            cap=mm["length_cap"],
            duplicate_threshold=mm["duplicate_threshold"],
            duplicate_seed=mm["duplicate_seed"],
            duplicate_baseline=mm["duplicate_baseline"])
        log(f"  path A in {time.time()-t0:.0f}s")

        path_b = {}
        for p in a["perturbations"]:
            t0 = time.time()
            path_b[p] = SR.self_retrieval(chunks, anchors, texts, vecs,
                                          queries[p], k=a["k"])
            log(f"  path B [{p}]: self_recall@{a['k']}="
                f"{path_b[p]['self_recall_at_k']:.4f} "
                f"containing={path_b[p]['containing_hit_at_k']:.4f} "
                f"({time.time()-t0:.0f}s)")

        flag = RP.fragmented_flag(
            path_a["length_distribution"],
            path_b["verbatim"]["self_recall_at_k"],
            floor=req["fragmented"]["length_p50_floor"],
            high_self_recall=req["fragmented"]["high_self_recall"])
        results.append(RP.StrategyResult(
            strategy=name, params=params, chunks=len(chunks), path_a=path_a,
            path_b=path_b, flag=flag, embed_seconds=round(t_embed, 1)))

        # a receipt per strategy, the moment it exists
        write_json_stable(str(out / f"strategy-{name}.json"),
                          results[-1].as_dict())

    rep = RP.chunking_report(
        results, extraction, corpus=req["corpus"]["fixture"],
        embed_note={
            "per_strategy": cost,
            "shared_tokenisation_seconds": round(t_tok, 1),
            "note": ("Every strategy needs its own embedding pass: different "
                     "chunks, different vectors, no reuse. Comparing N "
                     "strategies costs N embeds. Tokenisation is the one "
                     "cost that IS shared -- all three read the same offsets."),
        })
    rep["subsample"] = dict(sub, realised_documents=len(docs),
                            realised_chars=chars)
    rep["anchors"] = {"count": len(anchors), "seed": a["seed"],
                      "k": a["k"], "perturbations": a["perturbations"]}
    rep["weights_sha256"] = weights_sha
    write_json_stable(str(out / "chunking.json"), rep)
    log(f"wrote {out/'chunking.json'} in {(time.time()-t_start)/60:.1f} min")
    print("DONE")


class _Pre:
    """A tokenizer that hands back offsets computed once, for one document."""

    name = "precomputed"

    def __init__(self, offs):
        self._offs = offs

    def offsets(self, text):
        return self._offs


if __name__ == "__main__":
    main()
