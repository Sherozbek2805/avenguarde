"""
DECISION 2 -- download the Diviner Global Cumulative Product from PDS.

    python build/fetch_diviner_gcp.py

WHY THE GCP AND NOT A DERIVED tbol_min RASTER
    There is no tbol_min raster at PDS. The level-4 rasters already on disk
    (diviner_tbol_max.xyz and friends) are a derived UCLA product set, and the
    minimum is simply absent from it -- only a description file exists. The
    GCP is the SOURCE those rasters were derived from: tbol binned by local
    time, so the maximum AND the minimum are both computable directly from it.
    That is strictly better than reconstructing the minimum by least squares
    from the zonal-mean-removed anomaly, which would be inference layered on
    inference.

STRUCTURE, from the PDS4 label (verified, not assumed)
    18 files, one per 10 degrees of latitude, 90S to 90N.
    Each: FIXED_LENGTH ASCII, record_length 113 bytes (111 data + CRLF),
    1,382,400 records = 720 lon x 20 lat x 96 local-time bins.
    0.5 degree spatial binning, 0.25 hour local-time binning.
    Columns, 1-indexed byte starts:
        1  Center_Longitude  start   1 len 7  degree
        2  Center_Latitude   start  10 len 6  degree
        3  Local_Time        start  18 len 6  hr
        4-10 t3..t9          channel brightness temperatures, K
        11 tbol              start 103 len 9  K   <- the one we want
    TWO fill constants, not one:
        -9999  unknown      bins that contained no observations
        -9998  invalid
    NEGATIVE brightness temperatures are VALID DATA, not fill: they come from
    negative radiance when the true temperature is below a channel's
    sensitivity. Only the two constants above may be discarded.

    Williams, J.-P., Paige, D.A., Greenhagen, B.T. & Sefton-Nash, E. (2017)
    The global surface temperatures of the Moon as measured by the Diviner
    Lunar Radiometer Experiment. Icarus 283, 300-325.
    Data set LRO-L-DLRE-5-GCP-V1.0, DOI 10.17189/1520655.
    Observations 2009-07-05 to 2015-04-01.
"""

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

BASE = ("https://pds-geosciences.wustl.edu/lro/"
        "urn-nasa-pds-lro_diviner_derived1/data_derived_gcp/")
OUT = os.path.join(C.ROOT, "sources", "diviner_gcp")
UA = ("Mozilla/5.0 (compatible; student project, NASA Space Apps Challenge "
      "2026; 18 files, sequential, 3s apart; lunar thermal analog study)")

EXPECT_BYTES = 156_211_313
RECORD_BYTES = 113
EXPECT_RECORDS = 1_382_400
DELAY_S = 3.0

BANDS = ([f"{a:02d}n{a+10:02d}n" for a in range(0, 90, 10)] +
         [f"{a+10:02d}s{a:02d}s" for a in range(0, 90, 10)])


def fetch(url, dest, timeout=1800):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest + ".part"
    t0 = time.perf_counter()
    n = 0
    with urllib.request.urlopen(req, timeout=timeout) as r, \
            io.open(tmp, "wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            n += len(chunk)
    os.replace(tmp, dest)
    return n, time.perf_counter() - t0


def main():
    os.makedirs(OUT, exist_ok=True)
    print("=" * 78)
    print("DIVINER GCP -- 18 latitude bands, ~149 MB each, ~2.6 GB total")
    print(f"free disk {C.free_gib(C.ROOT):.1f} GiB")
    print("=" * 78)
    C.require_disk(10.0, C.ROOT)
    rec = {}
    t0 = time.perf_counter()
    got = skipped = failed = 0
    for i, b in enumerate(BANDS, 1):
        name = f"global_cumul_avg_cyl_{b}_002.tab"
        dest = os.path.join(OUT, name)
        if os.path.exists(dest) and os.path.getsize(dest) == EXPECT_BYTES:
            print(f"  [{i:2d}/18] {name}  already complete, skipping")
            rec[name] = dict(bytes=EXPECT_BYTES, status="already_present")
            skipped += 1
            continue
        try:
            n, dt = fetch(BASE + name, dest)
            ok = n == EXPECT_BYTES
            print(f"  [{i:2d}/18] {name}  {n:,} B in {dt:5.1f} s "
                  f"({n/2**20/max(dt,1e-9):5.1f} MB/s)  "
                  f"size {'OK' if ok else 'MISMATCH'}")
            rec[name] = dict(bytes=n, seconds=round(dt, 1),
                             size_ok=ok, status="downloaded")
            got += 1
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            print(f"  [{i:2d}/18] {name}  FAILED: {type(e).__name__}: {e}")
            rec[name] = dict(status="failed", error=f"{type(e).__name__}: {e}")
            failed += 1
        time.sleep(DELAY_S)
    el = time.perf_counter() - t0
    total = sum(v.get("bytes", 0) for v in rec.values())
    man = dict(
        source="PDS Geosciences Node, LRO Diviner Global Cumulative Product",
        dataset_id="LRO-L-DLRE-5-GCP-V1.0", doi="10.17189/1520655",
        base_url=BASE,
        citation=("Williams, J.-P., Paige, D.A., Greenhagen, B.T. & "
                  "Sefton-Nash, E. (2017) The global surface temperatures of "
                  "the Moon as measured by the Diviner Lunar Radiometer "
                  "Experiment. Icarus 283, 300-325"),
        observations="2009-07-05T16:50:26.195 to 2015-04-01T00:00:00.000",
        binning="0.5 degree latitude and longitude, 0.25 hours of local time",
        record_bytes=RECORD_BYTES, records_per_file=EXPECT_RECORDS,
        bytes_per_file=EXPECT_BYTES,
        columns={
            "1": dict(name="Center_Longitude", start=1, length=7, unit="degree"),
            "2": dict(name="Center_Latitude", start=10, length=6, unit="degree"),
            "3": dict(name="Local_Time", start=18, length=6, unit="hr"),
            "4": dict(name="t3", start=26, length=9, unit="K"),
            "5": dict(name="t4", start=37, length=9, unit="K"),
            "6": dict(name="t5", start=48, length=9, unit="K"),
            "7": dict(name="t6", start=59, length=9, unit="K"),
            "8": dict(name="t7", start=70, length=9, unit="K"),
            "9": dict(name="t8", start=81, length=9, unit="K"),
            "10": dict(name="t9", start=92, length=9, unit="K"),
            "11": dict(name="tbol", start=103, length=9, unit="K"),
        },
        fill_constants={"-9999": "unknown; bin contained no observations",
                        "-9998": "invalid"},
        negative_values_note=(
            "NEGATIVE brightness temperatures are VALID DATA, not fill. They "
            "arise from negative radiance when the true temperature is below "
            "a channel's sensitivity. Only -9998 and -9999 may be discarded."),
        header_note=("The PDS4 label places a 113-byte Header object at "
                     "offset 0 and the Table_Character at offset 113, so the "
                     "first 113 bytes are a header record, not data. Verified "
                     "on read, not assumed."),
        files=rec, downloaded=got, skipped=skipped, failed=failed,
        total_bytes=total, elapsed_s=round(el, 1),
        fetched_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    mp = os.path.join(OUT, "manifest.json")
    io.open(mp, "w", encoding="utf-8").write(
        json.dumps(man, indent=1, ensure_ascii=False))
    print("=" * 78)
    print(f"downloaded {got}, already present {skipped}, failed {failed}")
    print(f"{total/2**30:.2f} GiB in {el/60:.1f} min")
    print(f"manifest -> {mp}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
