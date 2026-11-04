"""Live local competitor price research. Free: DuckDuckGo via ddgs + page fetch + regex."""
import re, statistics, datetime, time, concurrent.futures as cf
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
PRICE_RE = re.compile(r"(?<![A-Za-z0-9])(?:R|ZAR)\s?(\d{1,3}(?:[ ,\u00a0]\d{3})+|\d{2,6})(?:[.,]\d{2})?(?!\s?(?:m|bn|million|billion)\b)(?![\d%])")
SKIP = ("/collections/", "/products/", "product-category", "/category/", "/shop/", "/product/", "youtube.", "tiktok.", "pinterest.", "instagram.", "wikipedia.", "amazon.", "reddit.")
STOP = {"and", "the", "of", "for", "in", "a", "services", "service"}

def _search(q, n=10):
    for attempt in range(3):
        try:
            return list(DDGS().text(q, region="za-en", max_results=n))
        except Exception:
            time.sleep(1.5)
    return []

def _keywords(service):
    words = [w for w in re.findall(r"[a-z]+", service.lower()) if w not in STOP and len(w) > 2]
    stems = {w[:-1] if w.endswith("s") else w for w in words}
    return stems or {service.lower()}

BAD = ("save", "off ", "deposit", "discount", "less ", "voucher", "from r0")

def extract_prices(text, kws, lo=50, hi=100000, phrase=None):
    """Prices near the service term. Uses the exact phrase when the page has it."""
    low = text.lower()
    if phrase and phrase in low:
        got = extract_prices(text, {phrase}, lo, hi)
        if got:
            return got
    out = []
    for m in PRICE_RE.finditer(text):
        v = int(re.sub(r"\D", "", m.group(1)))
        if not (lo <= v <= hi):
            continue
        ctx = low[max(0, m.start() - 110): m.end() + 40]
        if any(b in low[max(0, m.start() - 12): m.start()] for b in BAD):
            continue
        if any(k in ctx for k in kws):
            snippet = re.sub(r"\s+", " ", text[max(0, m.start() - 70): m.end() + 30]).strip()
            after = low[m.end(): m.end() + 22]
            unit = ("hour" if re.search(r"^\s*(/\s*h|per hour|p/?h\b|/hr|an hour|hourly)", after)
                    else "month" if re.search(r"^\s*(/\s*m|per month|p/?m\b|pm\b|a month|monthly)", after)
                    else "service")
            out.append((v, snippet, unit))
    return out

def _fetch(url):
    try:
        r = requests.get(url, headers=UA, timeout=8)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return ""
        s = BeautifulSoup(r.text, "html.parser")
        for t in s(["script", "style", "noscript", "svg"]):
            t.decompose()
        return s.get_text(" ")[:400000]
    except Exception:
        return ""

def research(service, area, unit="service", max_sources=10):
    kws = _keywords(service)
    phrase = service.lower().strip().rstrip('s')
    city = area.split(",")[-1].strip()
    queries = [f"{service} price {area}", f"{service} prices {city} South Africa", f"{service} price list {area} R"]
    hits, seen = [], set()
    for q in queries:
        for r in _search(q):
            u = r.get("href", "")
            if u and u not in seen and not any(s in u for s in SKIP):
                seen.add(u); hits.append(r)
        if len(hits) >= 18:
            break
    def work(r):
        try:
            return _work(r)
        except Exception:
            return None
    def _work(r):
        u = r["href"]
        text = _fetch(u) if "facebook.com" not in u else ""
        found = extract_prices(text, kws, phrase=phrase) if text else []
        how = "page"
        if not found:
            found = extract_prices(f"{r.get('title','')} {r.get('body','')}", kws, phrase=phrase)
            how = "search snippet"
        if not found:
            return None
        units = [u for *_, u in found]
        unit = max(set(units), key=units.count)
        found = [f for f in found if f[2] == unit]
        vals = sorted(v for v, *_ in found)
        dom = (u.lower().split("/") + ["", "", ""])[2]
        agg = (any(k in dom for k in ("prices", "compare", "guide", "marketing", "directory", "fresha", "accounter"))
               or any(k in u.lower() for k in ("/blog", "/guides", "/find/", "/lp/", "how-much", "cost-of", "-fees-")))
        return {"unit": unit, "kind": "guide or directory" if agg else "business","url": u, "title": (r.get("title") or u)[:90], "prices": vals[:30],
                "low": vals[0], "high": vals[-1], "typical": int(statistics.median(vals)),
                "example": found[0][1][:160], "from": how}
    with cf.ThreadPoolExecutor(8) as ex:
        sources = [s for s in ex.map(work, hits) if s]
    uniq, doms = [], set()
    for s in sources:
        d = re.sub(r"^www\.", "", s["url"].split("/")[2])
        if d not in doms:
            doms.add(d); s["domain"] = d; uniq.append(s)
    sources = uniq[:max_sources]
    other = [s for s in sources if s["unit"] != unit]
    sources = [s for s in sources if s["unit"] == unit]
    refs = [s for s in sources if s["kind"] != "business"]
    sources = [s for s in sources if s["kind"] == "business"]
    typ = [s["typical"] for s in sources]
    res = {"query": f"{service}, {area}", "checked": datetime.date.today().isoformat(),
           "searched": len(hits), "sources": sources, "n": len(sources), "thin": len(sources) < 3, "unit": unit, "other_unit": other[:6], "refs": refs[:6]}
    if typ:
        res.update(low=min(typ), high=max(typ), median=int(statistics.median(typ)))
    return res

if __name__ == "__main__":
    import json, sys
    print(json.dumps(research(sys.argv[1], sys.argv[2], *(sys.argv[3:4])), indent=1))
