#!/bin/bash
# Terrestrial Analog Finder: one server for the website and the engine API (Ubuntu 24.04, runs once as root at first boot).
# Progress: /setup/setup.txt, /setup/warmup.txt, /setup/log.txt
exec > /var/log/analog-setup.log 2>&1
set -x
export DEBIAN_FRONTEND=noninteractive
DOMAIN="avenguarde.eengineer.net"
mkdir -p /srv/status /srv/www/site /srv/data /etc/analog /var/lib/analog/null_cache /opt/analog_app
S=/srv/status/setup.txt
step() { echo "$(date -u +%H:%M:%S) $*" >> $S; }
step "start"
(while true; do cp /var/log/analog-setup.log /srv/status/log.txt; sleep 15; done) &
echo "PUT_YOUR_OWN_LONG_RANDOM_TOKEN_HERE" > /etc/analog/deploy_token
echo "<!doctype html><meta charset=utf-8><title>Terrestrial Analog Finder</title><p>The site is being set up.</p>" > /srv/www/site/index.html
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
for i in 1 2 3 4 5; do apt-get update -y && apt-get install -y python3-venv python3-pip git curl caddy && break; sleep 8; done
step "packages installed"

# Web server. The site at /, the engine under /api/, stored results under /data/. HTTPS for the project's domain
# (the certificate is fetched at the first visit after DNS points here) and for a name made from the public address.
cat > /usr/local/bin/analog-web.sh <<'WEB'
#!/bin/bash
IP=$(curl -s --max-time 10 https://checkip.amazonaws.com | tr -d '[:space:]')
[ -z "$IP" ] && exit 1
HOST="$(echo "$IP" | tr . -).sslip.io"
[ "$(cat /srv/status/host.txt 2>/dev/null)" = "$HOST" ] && systemctl is-active --quiet caddy && exit 0
cat > /etc/caddy/Caddyfile <<CADDY
{
    auto_https disable_redirects
    on_demand_tls {
        ask http://127.0.0.1:8000/_tls_ask
    }
}
(site) {
    encode gzip
    handle_path /setup/* {
        root * /srv/status
        file_server
    }
    handle_path /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle_path /data/runs/* {
        root * /srv/data/runs
        file_server
    }
    handle_path /data/contract/* {
        root * /srv/data/contract
        file_server
    }
    handle_path /data/export/* {
        root * /srv/data/export
        file_server
    }
    handle {
        root * /srv/www/site
        file_server
    }
}
:80 {
    import site
}
https://$HOST {
    import site
}
https://DOMAIN_NAME {
    tls {
        on_demand
    }
    import site
}
CADDY
sed -i "s/DOMAIN_NAME/$(cat /etc/analog/domain)/" /etc/caddy/Caddyfile
echo "$HOST" > /srv/status/host.txt
systemctl restart caddy
WEB
echo "$DOMAIN" > /etc/analog/domain
chmod +x /usr/local/bin/analog-web.sh
cat > /etc/systemd/system/analog-web.service <<'UNIT'
[Unit]
Description=Analog Finder: web server names
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/analog-web.sh
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable analog-web
/usr/local/bin/analog-web.sh
step "web server started as $(cat /srv/status/host.txt)"

useradd --system --home /opt/avenguarde --shell /usr/sbin/nologin analog
for i in 1 2 3; do git clone --depth 1 https://github.com/Sherozbek2805/avenguarde /opt/avenguarde && break; rm -rf /opt/avenguarde; sleep 8; done
step "repository cloned: $(du -sh /opt/avenguarde | cut -f1), commit $(git -C /opt/avenguarde rev-parse --short HEAD)"
/usr/local/bin/analog-web.sh
python3 -m venv /opt/venv
/opt/venv/bin/pip install --no-cache-dir numpy scipy astropy astropy-healpix jsonschema matplotlib pillow fastapi uvicorn pydantic
step "python packages installed, exit $?"
cd /opt/avenguarde
/opt/venv/bin/python build/phase4b_minmax_scale.py > /srv/status/calibration.txt 2>&1
step "calibration built, exit $?"
# the stored results the website shows: a copy taken now, so live searches never touch them
cp -r runs contract /srv/data/ && mkdir -p /srv/data/export && cp -r export/site_assets /srv/data/export/
step "stored results copied: $(du -sh /srv/data | cut -f1)"

# The app: the engine's own API, plus (1) a cache for the chance-test draws, (2) a site upload, (3) the certificate check.
# (1) The draws depend only on the variable set, the patch size, the latitude band, the Earth sample and the seed, never on
#     the target's values, and the seed is fixed. The same request always gives the same draws, so they are kept on disk.
cat > /opt/analog_app/app.py <<'PY'
import hashlib, io, json, os, shutil, sys, tarfile
import numpy as np
sys.path.insert(0, "/opt/avenguarde/engine")
import analog_engine as AE
CACHE = "/var/lib/analog/null_cache"
_orig_null = AE.Pairing.null
def cached_null(self, set_id, parent_id, n_cells, band, sample, B=AE.B_NULL, seed=AE.SEED, keep_pixels=False):
    if keep_pixels:
        return _orig_null(self, set_id, parent_id, n_cells, band, sample, B=B, seed=seed, keep_pixels=True)
    sample = np.ascontiguousarray(sample)
    key = hashlib.sha256(json.dumps([self.body, set_id, parent_id, int(n_cells), [float(b) for b in band], int(B), int(seed), int(sample.size),
                                     hashlib.sha256(sample.tobytes()).hexdigest(), AE.code_version()]).encode()).hexdigest()[:40]
    f = os.path.join(CACHE, key + ".npz")
    if os.path.exists(f):
        z = np.load(f)
        return dict(minima=z["minima"], spreads=z["spreads"], hemispheres=z["hemispheres"], discards=int(z["discards"]),
                    patch_radius_km=float(z["patch_radius_km"]), pixels=[])
    out = _orig_null(self, set_id, parent_id, n_cells, band, sample, B=B, seed=seed, keep_pixels=False)
    tmp = os.path.join(CACHE, key + ".tmp.npz")
    np.savez(tmp, minima=out["minima"], spreads=out["spreads"], hemispheres=out["hemispheres"], discards=out["discards"], patch_radius_km=out["patch_radius_km"])
    os.replace(tmp, f)
    return out
AE.Pairing.null = cached_null

from api import app
from fastapi import HTTPException, Request
TOKEN = open("/etc/analog/deploy_token").read().strip()
DOMAINS = {open("/etc/analog/domain").read().strip()}

@app.get("/_tls_ask", include_in_schema=False)
def tls_ask(domain: str = ""):
    if domain in DOMAINS:
        return {"ok": True}
    raise HTTPException(404, "not served here")

@app.get("/_cache", include_in_schema=False)
def cache_state():
    return {"cached_chance_tests": len([f for f in os.listdir(CACHE) if f.endswith(".npz") and ".tmp." not in f])}

@app.post("/_deploy", include_in_schema=False)
async def deploy(request: Request):
    if request.headers.get("x-deploy-token") != TOKEN:
        raise HTTPException(403, "wrong token")
    data = await request.body()
    new, cur, old = "/srv/www/site.new", "/srv/www/site", "/srv/www/site.old"
    shutil.rmtree(new, ignore_errors=True); os.makedirs(new)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as t:
        t.extractall(new, filter="data")
    if not os.path.exists(os.path.join(new, "index.html")):
        raise HTTPException(422, "no index.html in the upload")
    shutil.rmtree(old, ignore_errors=True)
    os.rename(cur, old); os.rename(new, cur)
    n = sum(len(fs) for _, _, fs in os.walk(cur))
    return {"deployed_files": n, "bytes": len(data)}
PY
chown -R analog:analog /opt/avenguarde /var/lib/analog /srv/www /opt/analog_app
chmod 640 /etc/analog/deploy_token && chown root:analog /etc/analog/deploy_token

cat > /etc/systemd/system/analog.service <<'UNIT'
[Unit]
Description=Terrestrial Analog Finder API
After=network-online.target
[Service]
User=analog
WorkingDirectory=/opt/avenguarde
Environment=MPLCONFIGDIR=/tmp/mpl
ExecStart=/opt/venv/bin/python -m uvicorn app:app --app-dir /opt/analog_app --host 127.0.0.1 --port 8000 --root-path /api
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now analog
sleep 10
step "api started: $(curl -s --max-time 20 http://127.0.0.1:8000/health | head -c 200)"

# Warm-up: every preset of the main result once (this fills the cache), then once more (this measures the cached time).
cat > /opt/analog_app/warmup.py <<'PY'
import json, time, urllib.request
API = "http://127.0.0.1:8000"
def get(p): return json.load(urllib.request.urlopen(API + p, timeout=120))
def post(p, b): return json.load(urllib.request.urlopen(urllib.request.Request(API + p, data=json.dumps(b).encode(), headers={"Content-Type": "application/json"}), timeout=120))
out = open("/srv/status/warmup.txt", "a")
def log(*a):
    out.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n"); out.flush()
log("warmup start")
for body in ("moon", "mars"):
    rows = [r for r in json.load(open("/srv/data/runs/%s_summary.json" % body)) if r["system"] == "all_variables"]
    for r in rows:
        req = {"body": body, "system": "all_variables", "preset": {"name": r["target"], "construction": r["construction"]}}
        for attempt in ("first", "cached"):
            try:
                j = post("/search", req)
                while True:
                    time.sleep(3)
                    s = get("/jobs/" + j["job_id"])
                    if s["status"] in ("done", "failed"):
                        break
                same = s.get("p") is not None and abs(s["p"] - r["p"]) < 1e-6
                log(body, "|", r["target"], "|", r["construction"], "|", attempt, "|", s["status"], "|", s.get("seconds"), "s | p", s.get("p"), "| stored p", r["p"], "|", "SAME" if same else "DIFFERENT", "|", s.get("error", ""))
            except Exception as e:
                log(body, "|", r["target"], "|", attempt, "| ERROR", repr(e)[:200])
log("warmup finished")
PY
systemd-run --unit=analog-warmup --uid=root /opt/venv/bin/python /opt/analog_app/warmup.py
free -m >> $S; nproc >> $S
/usr/local/bin/analog-web.sh
step "setup finished, name $(cat /srv/status/host.txt); warm-up running, see /setup/warmup.txt"
cp /var/log/analog-setup.log /srv/status/log.txt
