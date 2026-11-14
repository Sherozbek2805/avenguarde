"""
Exercise the running API end to end (start it first: see api.py).

    python engine/test_api.py [http://127.0.0.1:8000]
"""
import json
import sys
import time
import urllib.error
import urllib.request

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
RES = []


def call(method, path, body=None, timeout=300):
    req = urllib.request.Request(B + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def check(tag, ok, detail=""):
    RES.append((tag, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {tag}" + (f"  -- {detail}" if detail else ""), flush=True)


def wait(job_id, limit=900):
    t0 = time.time()
    while time.time() - t0 < limit:
        _, j = call("GET", f"/jobs/{job_id}")
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(3)
    return dict(status="timeout")


def main():
    import io
    import os
    import jsonschema
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_schema = json.load(io.open(os.path.join(root, "contract", "output_schema.json"), encoding="utf-8"))
    pt_schema = json.load(io.open(os.path.join(root, "contract", "point_schema.json"), encoding="utf-8"))
    code, h = call("GET", "/health")
    check("GET /health", code == 200 and h["status"] == "ok", h.get("code_version", ""))
    code, p = call("GET", "/presets?body=moon")
    check("GET /presets lists the nine Artemis regions", code == 200 and len(p) == 9)
    code, e = call("POST", "/search", dict(body="moon", system="all_variables"))
    check("POST /search with neither preset nor selection is refused", code == 422, str(e.get("detail"))[:60])
    code, e = call("POST", "/search", dict(body="moon", system="fastest", selection=dict(method="circle", params=dict(lat=0, lon=0, radius_km=20))))
    check("an unknown ranking system is refused", code == 422)

    code, j = call("POST", "/search", dict(body="moon", system="all_variables", name="API test: small circle near Copernicus",
                                          selection=dict(method="circle", params=dict(lat=9.6, lon=-20.1, radius_km=14))))
    check("POST /search (custom circle) is accepted at once", code == 202 and "job_id" in j, j.get("status", ""))
    code2, big = call("POST", "/search", dict(body="moon", system="all_variables", selection=dict(method="circle", params=dict(lat=0, lon=0, radius_km=400))))
    code3, bad = call("POST", "/search", dict(body="moon", system="all_variables", preset=dict(name="Shackleton")))
    done = wait(j["job_id"])
    check("the job finishes", done["status"] == "done", f"{done.get('seconds')} s, run_id {done.get('run_id')}, p = {done.get('p')}, {done.get('sites')} sites")
    jb = wait(big["job_id"])
    check("a shape that is too large fails with a clear message, and the server stays up", jb["status"] == "failed", jb.get("error", "")[:80])
    jx = wait(bad["job_id"])
    check("an unknown preset fails with a clear message", jx["status"] == "failed", jx.get("error", "")[:80])
    if done["status"] == "done":
        code, doc = call("GET", f"/runs/{done['run_id']}")
        try:
            jsonschema.Draft202012Validator(out_schema, format_checker=jsonschema.FormatChecker()).validate(doc)
            ok = True
        except Exception as ex:
            ok = False
            print(str(ex)[:300])
        check("GET /runs/{run_id} returns a contract-valid output", code == 200 and ok,
              f"{doc['run']['target']['cells']} cells, {doc['run']['dims_used']} variables, control passed {doc['null_test']['positive_control']['passed']}")
        f = doc["rasters"][-1]["views"]["global"].split("/")[-1]
        with urllib.request.urlopen(f"{B}/runs/{done['run_id']}/files/{f}", timeout=60) as r:
            check("the run's rank image is served", r.status == 200 and r.headers.get("content-type") == "image/png", f"{f}, {len(r.read()):,} bytes")
        s1 = doc["sites"][0]
        code, pp = call("GET", f"/point?run_id={done['run_id']}&lat={s1['lat']}&lon={s1['lon']}")
        jsonschema.Draft202012Validator(pt_schema).validate(pp)
        check("GET /point on the run's best site returns that site's score", code == 200 and abs(pp["di_combined"] - s1["di_combined"]) < 1e-3,
              f"DI {pp['di_combined']} at {pp['lat']}, {pp['lon']}")
        code, po = call("GET", f"/point?run_id={done['run_id']}&lat=0&lon=-30")
        jsonschema.Draft202012Validator(pt_schema).validate(po)
        check("GET /point in the ocean answers with a reason", code == 200 and po["reason_excluded"] == "ocean")
    code, e = call("GET", "/point?run_id=no_such_run&lat=0&lon=0")
    check("GET /point for an unknown run is a 404", code == 404)
    code, e = call("GET", "/point?run_id=moon_haworth__all_variables&lat=123&lon=0")
    check("a latitude outside -90..90 is refused", code == 422)
    code, rs = call("GET", "/runs")
    check("GET /runs lists the new run", code == 200 and any(r["run_id"] == done.get("run_id") for r in rs), f"{len(rs)} runs")
    nf = [t for t, ok in RES if not ok]
    print(f"\n{len(RES) - len(nf)} of {len(RES)} passed" + (f"; FAILED: {nf}" if nf else ""))
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
