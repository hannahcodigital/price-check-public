import json, uuid, subprocess, os, datetime, shutil, secrets, hmac
from flask import Flask, request, jsonify, render_template, send_file, abort, redirect
import engine, research, storage

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
HERE = os.path.dirname(os.path.abspath(__file__))
RDIR = os.path.join(HERE, "reports")
os.makedirs(RDIR, exist_ok=True)

# Settings come from environment variables (set them on the host, never in code).
PAYWALL = os.environ.get("PAYWALL", "1") == "1"          # PAYWALL=0 = demo mode, report shows straight away
PAY_LINK = os.environ.get("PAY_LINK", "")                 # Hannah's bank payment request link for R99
EFT = os.environ.get("EFT_DETAILS", "")                   # e.g. "Bank: ... | Acc: ... | Branch: ..."
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")               # long random secret for /admin
PRICE = os.environ.get("PRICE", "99")
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")

def save(rep): storage.save(rep)
def load(rid):
    r = storage.get(os.path.basename(rid))
    if r is None: abort(404)
    return r
def paid(rep): return rep.get("paid", True) or not PAYWALL   # old reports without the field count as paid

@app.get("/")
def index():
    return render_template("index.html", paywall=PAYWALL, price=PRICE)

@app.post("/api/analyze")
def analyze():
    raw = request.get_json(force=True)
    # Resolve "I'm not sure" estimates and normalise owner-pay fields before computing.
    d, _est = engine.apply_estimates(raw)
    d["vat"] = bool(raw.get("vat")) if not isinstance(raw.get("vat"), str) else raw.get("vat") in ("1", "true", "True")
    # Preserve optional text fields from the raw payload.
    for k in ("service", "area", "dream", "proof", "speed", "pain", "email", "basis"):
        if k in raw and raw[k] is not None:
            d[k] = raw[k]
    d["research"] = raw.get("research", True)
    res = engine.compute(d)
    # Keep the stored input aligned with what the engine actually used.
    d["costs"] = res["costs_m"]
    d["salary"] = res["salary_now_m"]
    d["salary_target"] = res["salary_target_m"]
    d["capacity"] = res["capacity"]
    d["estimates"] = res.get("estimates") or {}
    d["no_pay_reasons"] = res.get("reasons") or []
    mk = research.research(d["service"], d["area"], unit=res["basis"]) if d.get("research", True) else None
    pos = engine.market_position(res, mk)
    offer = engine.premium_offer(res, d)
    recs = engine.recommendations(res, mk, pos, d["service"], offer)
    rid = uuid.uuid4().hex[:10] + secrets.token_hex(3)      # hard-to-guess report link
    ref = "PC" + secrets.token_hex(2).upper()               # payment reference the customer uses, e.g. PC7F3A
    rep = dict(id=rid, ref=ref, paid=not PAYWALL, input=d, res=res, market=mk, pos=pos, recs=recs, offer=offer,
               created=datetime.datetime.now().strftime("%d %B %Y"), ts=datetime.datetime.now().isoformat(timespec="minutes"))
    save(rep)
    return jsonify(id=rid, ref=ref, paid=rep["paid"], verdict=res["verdict"], sources=(mk or {}).get("n", 0))

@app.get("/report/<rid>")
def report(rid):
    r = load(rid)
    if not paid(r):
        return render_template("pending.html", r=r, pay_link=PAY_LINK, eft=EFT, price=PRICE)
    return render_template("report.html", r=r, pdf=request.args.get("pdf"), autoprint=request.args.get("print"))

@app.get("/api/status/<rid>")
def status(rid):
    return jsonify(paid=paid(load(rid)))

@app.get("/report/<rid>.pdf")
def report_pdf(rid):
    r = load(rid)
    if not paid(r): return redirect(f"/report/{rid}")
    if not CHROME:   # shared hosting / no Chrome: the browser's own "Save as PDF" using the print layout
        return redirect(f"/report/{rid}?pdf=1&print=1")
    out = os.path.join(RDIR, f"{rid}.pdf")
    url = f"http://127.0.0.1:{os.environ.get('PORT', 8090)}/report/{rid}?pdf=1"
    subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--no-pdf-header-footer",
                    "--virtual-time-budget=3000", f"--print-to-pdf={out}", url], capture_output=True, timeout=60)
    if not os.path.exists(out): return redirect(f"/report/{rid}?pdf=1&print=1")
    return send_file(out, as_attachment=True, download_name=f"hannah-and-co-pricing-report-{rid}.pdf")

def _admin_ok():
    k = request.values.get("key", "")
    return bool(ADMIN_KEY) and hmac.compare_digest(k, ADMIN_KEY)

@app.get("/admin")
def admin():
    if not _admin_ok(): abort(404)
    reps = storage.all_reports()
    return render_template("admin.html", reps=reps, key=request.values["key"])

@app.post("/admin/unlock/<rid>")
def unlock(rid):
    if not _admin_ok(): abort(404)
    r = load(rid); r["paid"] = True; r["paid_at"] = datetime.datetime.now().isoformat(timespec="minutes"); save(r)
    return redirect(f"/admin?key={request.values['key']}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8090)), threaded=True)
