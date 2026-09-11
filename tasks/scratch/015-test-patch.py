import io

P = "oneground/verify/test_matched.py"
s = io.open(P, encoding="utf-8").read()

OLD = '''    sim = json.load(open(os.path.join(wd, "simulate.json"), encoding="utf-8"))
    data = json.load(open(os.path.join(wd, "verify.json"), encoding="utf-8"))
    info = json.load(open(os.path.join(wd, "verify_info.json"),
                          encoding="utf-8"))
    c = {"latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32},
         "recall_at_k": {"k": 10, "min": 0.95}}
    settled = [r["config"] for r in sim["rows"]
               if vd.latency_p95(r, data, c, "runpod", info).outcome == MEETS]
    assert settled == [
        "single_node_hnsw[M=32,efConstruction=200,efSearch=128]"], settled
    # And it is the configuration the engine reported building.
    ip = info["engine_facts"]["index_params"]
    assert ip["m"] == 32 and ip["ef_construct"] == 200, ip
    assert info["engine_params"]["hnsw_ef"] == 128, info["engine_params"]'''

NEW = '''    sim = json.load(open(os.path.join(wd, "simulate.json"), encoding="utf-8"))
    data = json.load(open(os.path.join(wd, "verify.json"), encoding="utf-8"))
    info = json.load(open(os.path.join(wd, "verify_info.json"),
                          encoding="utf-8"))
    c = {"latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32},
         "recall_at_k": {"k": 10, "min": 0.95}}

    # The rule is about which option may CARRY a measurement, not about which
    # way the measurement then goes. Asserting MEETS conflated the two, and
    # task 015's pod run made that visible: the same configuration measured
    # 38.22 ms on one pod and 42.82 ms on another, so an assertion on MEETS
    # against a 40 ms threshold was testing the machine, not the rule.
    built = "single_node_hnsw[M=32,efConstruction=200,efSearch=128]"
    for engine, block in vd.engine_blocks(data):
        einfo = dict(vd.engine_info_blocks(info)).get(engine)
        settled = [r["config"] for r in sim["rows"]
                   if vd.latency_p95(r, block, c, "runpod", einfo,
                                     engine=engine).outcome != COULDNT_CHECK]
        assert settled == [built], (engine, settled)

    # And it is the configuration each engine reported building.
    for engine, einfo in vd.engine_info_blocks(info):
        ip = (einfo.get("engine_facts") or {}).get("index_params") or {}
        m = ip.get("m")
        efc = ip.get("ef_construct", ip.get("ef_construction"))
        assert m == 32 and efc == 200, (engine, ip)
        assert einfo["engine_params"]["hnsw_ef"] == 128, einfo["engine_params"]

    # Task 015: both engines ran, in one environment, sequentially.
    assert data.get("engines_measured") == ["qdrant", "pgvector"], data.get(
        "engines_measured")
    assert data.get("sequential") is True
    assert data.get("environment_id")'''

assert OLD in s, "anchor not found"
s = s.replace(OLD, NEW, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("test restated around the rule rather than the threshold")
