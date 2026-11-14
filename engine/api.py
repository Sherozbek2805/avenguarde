"""
A small web API on top of the engine, for the website and the backend.

    python -m uvicorn api:app --app-dir engine --host 127.0.0.1 --port 8000
    open http://127.0.0.1:8000/docs          (every endpoint, with a "Try it out" button)

    GET  /health                             is it up, which code version
    GET  /presets?body=moon                  the preset targets (name, centre, shape, cells)
    GET  /runs                               finished runs on disk, newest first
    GET  /runs/{run_id}                      one run: the contract's output JSON
    GET  /runs/{run_id}/files/{name}         a map of that run (PNG or .npy)
    POST /search                             start a search; returns a job id at once
    GET  /jobs/{job_id}                      queued | running | done | failed (+ run_id when done)
    GET  /point?run_id=..&lat=..&lon=..      any Earth cell against that run's target

A search takes 40 s for a 15-cell region and several minutes for a few hundred cells, so /search
does not wait: poll /jobs/{id} every few seconds, then fetch /runs/{run_id}. One search runs at a time.

Nothing here computes anything the engine does not: it only calls analog_engine.
"""
import io
import json
import os
import re
import sys
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analog_engine as AE
from run import control_for, slug

RUNS = os.path.join(AE.ROOT, "runs")
MAX_TARGET_CELLS = 1500          # a larger target would hold the one worker for more than a quarter of an hour
MAX_STATES = 4                   # finished runs kept in memory for /point (each is about 80 MB)
RUN_ID = re.compile(r"^[a-z0-9_]{1,120}$")
FILE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}\.(png|npy|json)$")

app = FastAPI(title="Terrestrial Analog Finder", version="2.4",
              description="Earth analogs of a place on the Moon or Mars. Output follows contract 2.4 (contract/output_schema.json).")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

_pairings, _states, _jobs = {}, OrderedDict(), {}
_lock = threading.Lock()                       # the engine keeps caches; one request at a time touches it
_worker = ThreadPoolExecutor(max_workers=1)


def pairing(body):
    if body not in ("moon", "mars"):
        raise HTTPException(422, "body must be moon or mars")
    if body not in _pairings:
        _pairings[body] = AE.Pairing(body)
    return _pairings[body]


def run_dir(run_id):
    if not RUN_ID.match(run_id) or not os.path.exists(os.path.join(RUNS, run_id, "output.json")):
        raise HTTPException(404, f"no finished run called {run_id}")
    return os.path.join("runs", run_id)


class Preset(BaseModel):
    name: str = Field(..., description="exactly as /presets lists it, e.g. Haworth")
    construction: Optional[str] = Field(None, description="Mars only: all_dimensions or without_composition; default is the target's primary one")


class Selection(BaseModel):
    method: Literal["circle", "rectangle", "pixel_list"]
    params: dict = Field(..., description="circle: {lat, lon, radius_km}. rectangle: {lat_min, lat_max, lon_min, lon_max}. pixel_list: {nside, pixels[]}")


class SearchRequest(BaseModel):
    body: Literal["moon", "mars"]
    system: Literal["all_variables", "earth_reachable_only"] = Field(..., description="the ranking system; run both and show both")
    preset: Optional[Preset] = None
    selection: Optional[Selection] = None
    name: Optional[str] = Field(None, max_length=80, description="a label for a custom target")


@app.get("/health")
def health():
    return dict(status="ok", contract_version="2.4", code_version=AE.code_version(), bodies_loaded=sorted(_pairings),
                jobs={k: v["status"] for k, v in list(_jobs.items())[-10:]})


@app.get("/presets")
def presets(body: Literal["moon", "mars"]):
    T = AE.jl(AE.CONTRACT, f"targets_{body}.json")["targets"]
    return [dict(name=t["name"], body=body, center_lat=t["center_lat"], center_lon=t["center_lon"], geometry=t["geometry"],
                 cells=t["cells"], primary_construction=t["primary_construction"], second_construction=t.get("second_construction"),
                 abs_lat_band=t["abs_lat_band"], source=t["geometry_source"]) for t in T]


@app.get("/runs")
def runs():
    out = []
    if os.path.isdir(RUNS):
        for d in os.listdir(RUNS):
            f = os.path.join(RUNS, d, "output.json")
            if RUN_ID.match(d) and os.path.exists(f):
                doc = json.load(io.open(f, encoding="utf-8"))
                r, nt = doc["run"], doc["null_test"]
                out.append(dict(run_id=d, body=r["target"]["body"], target=r["target"]["name"], method=r["target"]["selection"]["method"],
                                system=r["ranking"]["system"], variables=r["dims_used"], cells=r["target"]["cells"], p=nt["p"],
                                significant=bool(nt["p"] < AE.P_SIGNIFICANT), control_passed=nt["positive_control"]["passed"],
                                sites=len(doc["sites"]), run_utc=r["run_utc"]))
    return sorted(out, key=lambda q: q["run_utc"], reverse=True)


@app.get("/runs/{run_id}")
def run_output(run_id: str):
    return json.load(io.open(os.path.join(AE.ROOT, run_dir(run_id), "output.json"), encoding="utf-8"))


@app.get("/runs/{run_id}/files/{name}")
def run_file(run_id: str, name: str):
    d = run_dir(run_id)
    path = os.path.join(AE.ROOT, d, name)
    if not FILE_NAME.match(name) or not os.path.isfile(path):
        raise HTTPException(404, "no such file in this run")
    return FileResponse(path)


def _search(job_id, req: SearchRequest):
    job = _jobs[job_id]
    job.update(status="running", started=time.time())
    try:
        with _lock:
            P = pairing(req.body)
            if req.preset:
                if req.preset.name not in P.targets:
                    raise ValueError(f"no preset called {req.preset.name!r}; see /presets")
                tgt = P.targets[req.preset.name]
                cons = req.preset.construction or tgt["primary_construction"]
                rk, parent = P.ranking(req.preset.name, cons, req.system)
                run_id = f"{req.body}_{slug(req.preset.name)}" + ("" if cons == tgt["primary_construction"] else "_" + slug(cons)) + f"__{req.system}"
                cset = rk["ranking_set"] if req.system == "all_variables" else P._preset_control_set(parent)
                doc, det, state = P.run_preset(req.preset.name, req.system, construction=cons, out_dir=os.path.join("runs", run_id),
                                               control=control_for(P, cset, parent))
            else:
                sel = req.selection
                n = P.select_pixels(sel.method, sel.params).size
                if n == 0:
                    raise ValueError("the shape contains no cell centre; make it larger (one cell is 6 to 7 km across)")
                if n > MAX_TARGET_CELLS:
                    raise ValueError(f"the shape holds {n} cells; the limit is {MAX_TARGET_CELLS}. Make it smaller.")
                run_id = f"custom_{req.body}_{job_id[:8]}__{req.system}"
                parent = "earth_moon" if req.body == "moon" else None
                if parent is None:   # the same rule run_custom applies
                    import numpy as np
                    px = P.select_pixels(sel.method, sel.params)
                    comp = np.isfinite(P.Bd[[P.names.index(d) for d in P.parents["earth_mars"]["dimensions"]]][:, px]).all(0)
                    parent = "earth_mars" if comp.mean() >= 0.9 else "earth_mars_no_composition"
                cset = parent if req.system == "all_variables" else P._preset_control_set(parent)
                doc, det, state = P.run_custom(sel.method, sel.params, req.system, name=req.name or f"custom {sel.method}",
                                               out_dir=os.path.join("runs", run_id), control=control_for(P, cset, parent))
            _states[run_id] = (req.body, state)
            while len(_states) > MAX_STATES:
                _states.popitem(last=False)
        job.update(status="done", run_id=run_id, seconds=round(time.time() - job["started"], 1), p=doc["null_test"]["p"],
                   control_passed=doc["null_test"]["positive_control"]["passed"], sites=len(doc["sites"]))
    except Exception as e:                       # the message goes back to the caller; the server stays up
        job.update(status="failed", error=f"{type(e).__name__}: {e}", seconds=round(time.time() - job.get("started", time.time()), 1))


@app.post("/search", status_code=202)
def search(req: SearchRequest):
    if (req.preset is None) == (req.selection is None):
        raise HTTPException(422, "give exactly one of preset or selection")
    job_id = uuid.uuid4().hex
    _jobs[job_id] = dict(status="queued", queued=time.time(), body=req.body, system=req.system)
    _worker.submit(_search, job_id, req)
    return dict(job_id=job_id, status="queued", poll=f"/jobs/{job_id}")


@app.get("/jobs/{job_id}")
def job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "no such job (jobs are forgotten when the server restarts; finished runs stay under /runs)")
    j = dict(_jobs[job_id])
    if j["status"] == "running":
        j["running_seconds"] = round(time.time() - j["started"], 1)
    return j


@app.get("/point")
def point(run_id: str, lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=360)):
    d = run_dir(run_id)
    with _lock:
        if run_id not in _states:
            body = json.load(io.open(os.path.join(AE.ROOT, d, "output.json"), encoding="utf-8"))["run"]["target"]["body"]
            _states[run_id] = (body, pairing(body).state_from_disk(d))
            while len(_states) > MAX_STATES:
                _states.popitem(last=False)
        _states.move_to_end(run_id)
        body, state = _states[run_id]
        return pairing(body).point(state, lat, lon)
