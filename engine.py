"""Pricing engine. All assumptions are Hannah & Co working rules, shown in the report."""
import math

VAT = 0.15
UTILISATION = 0.75      # realistic share of your capacity that actually gets booked and paid
BUFFER = 0.20           # recommended price = floor + 20% for tax, leave, slow months and growth
def experience_uplift(y):
    return 0.0 if y < 2 else 0.10 if y < 5 else 0.20 if y < 10 else 0.30

def r10(x):  # round up to a clean R10 price
    return int(math.ceil(x / 10.0) * 10)

def compute(d):
    basis = d.get("basis", "service")               # service | hour | month
    price = float(d["price"])
    years = float(d["years"])
    weeks = float(d["weeks"])
    costs_y = float(d["costs"]) * 12
    salary_y = float(d["salary"]) * 12
    vat = bool(d.get("vat"))
    if basis == "month":
        cap_y = float(d["capacity"]) * 12 * weeks / 52        # client-months a year
        hrs_job = float(d["duration"])                        # hours per client per month
        unit, per_wk = "client-month", None
    elif basis == "hour":
        cap_y = float(d["capacity"]) * weeks
        hrs_job, unit = 1.0, "hour"
    else:
        cap_y = float(d["capacity"]) * weeks
        hrs_job, unit = float(d["duration"]), "service"
    net = price / (1 + VAT) if vat else price                   # what you keep, before VAT
    need = costs_y + salary_y
    gross_full = net * cap_y
    gross_real = net * cap_y * UTILISATION
    hours_real = hrs_job * cap_y * UTILISATION
    true_hourly = (gross_real - costs_y) / hours_real if hours_real else 0
    breakeven = costs_y / (cap_y * UTILISATION)
    floor = need / (cap_y * UTILISATION)
    rec = floor * (1 + BUFFER)
    up = experience_uplift(years)
    prem = rec * (1 + up)
    g = lambda x: r10(x * (1 + VAT)) if vat else r10(x)    # price as charged to client
    per = (lambda v: v / weeks) if basis != "month" else (lambda v: v / 12 / (weeks / 52))
    jobs_now = need / net if net else float("inf")
    jobs_rec = need / rec
    cap_label = "per month" if basis == "month" else "per week"
    cap = float(d["capacity"])
    noun = {"month": "clients", "hour": "billable hours"}.get(basis, "bookings")
    res = dict(noun=noun, noun1={"month": "client", "hour": "hour"}.get(basis, "booking"),
        basis=basis, unit=unit, cap_label=cap_label, vat=vat, price=price, net_price=round(net),
        capacity=cap, years=years, weeks=weeks,
        true_hourly=round(true_hourly), breakeven=g(breakeven), floor=g(floor),
        recommended=g(rec), premium=g(prem), uplift_pct=int(up * 100),
        needed_now=round(per(jobs_now), 1), needed_rec=round(per(jobs_rec), 1),
        capacity_pct_now=round(per(jobs_now) / cap * 100) if cap else 0,
        capacity_pct_rec=round(per(jobs_rec) / cap * 100) if cap else 0,
        revenue_real=round(gross_real), need=round(need), gap=round(need - gross_real + 0),
        utilisation=int(UTILISATION * 100), buffer=int(BUFFER * 100),
    )
    if price < res["breakeven"]:
        v, tone = f"You are losing money on every {res['noun1']}", "red"
    elif price < res["floor"]:
        v, tone = "You are underpriced", "amber"
    elif price < res["recommended"]:
        v, tone = "You cover the basics, with no room to breathe", "amber"
    elif price <= res["premium"]:
        v, tone = "Your price is healthy", "green"
    else:
        v, tone = "You are priced above your premium mark", "blue"
    res.update(verdict=v, tone=tone)
    return res

def market_position(res, mk):
    if not mk or mk.get("thin") or "median" not in mk:
        return None
    p, m = res["price"], mk["median"]
    vals = sorted(s["typical"] for s in mk["sources"])
    below = sum(1 for x in vals if x < p)
    diff = round((p - m) / m * 100)
    return dict(diff_pct=diff, below=below, total=len(vals),
                text=(f"{abs(diff)}% {'below' if diff < 0 else 'above'} the local median" if diff else "right on the local median"))

def recommendations(res, mk, pos, service, offer=None):
    recs = []
    p = res["price"]
    if p < res["floor"]:
        recs.append(("Move to your recommended price in two steps",
            f"Go to R{(p + res['recommended']) // 2:,.0f} for new clients now and R{res['recommended']:,} in 8 weeks. Tell existing clients 30 days ahead, with the reason in one line."))
    else:
        recs.append(("Hold your price and stop discounting",
            f"Your R{p:,.0f} covers your costs and salary. Protect it: replace discounts with a paid add-on that raises the value of each {res['noun1']}."))
    if res["capacity_pct_now"] > 85:
        recs.append(("You are fully booked and still short",
            f"At today's price you need {res['needed_now']} {res['noun']} {res['cap_label']}, which is {res['capacity_pct_now']}% of your capacity. Raising the price is the only fix that does not cost you more hours."))
    else:
        recs.append(("Fill the gap before you add more services" if res["basis"]!="month" else "Fill your client list before you add more services",
            f"At the recommended price you need {res['needed_rec']} {res['noun']} {res['cap_label']} ({res['capacity_pct_rec']}% of capacity). " + "Put your effort into a steady flow of new work: " + ("rebook every client before they leave." if res['basis'] != 'month' else "ask every new client for a referral in their second month.")))
    if pos and pos["diff_pct"] < -10:
        recs.append(("The local market supports a higher price",
            f"You sit {pos['text']} for {service}. Use your {int(res['years'])} years of experience as the reason: show results, reviews and before-and-after proof next to your price." if res['basis'] == 'service' else f"You sit {pos['text']} for {service}. Use your {int(res['years'])} years of experience as the reason: put client results and testimonials next to your price."))
    elif pos and pos["diff_pct"] > 15:
        recs.append(("Make your premium obvious",
            f"You sit {pos['text']}. Buyers will compare, so spell out what they get that cheaper options do not: time, results, guarantees or aftercare."))
    elif res["uplift_pct"] and p < res["premium"]:
        recs.append(("Create a premium tier",
            f"With {int(res['years'])} years behind you, offer a top tier at R{(offer['price'] if offer else res['premium']):,}{(' (' + offer['name'] + ', below)') if offer else ''} for clients who want your most experienced service, and keep your standard price for everyone else."))
    else:
        recs.append(("Collect proof as you go",
            "Ask every happy client for a review and a photo or result you can share. Proof is what lets you raise your price next year without losing clients."))
    return recs


# ---------- Premium offer (Hormozi value equation) ----------
CATS = {
 "hair": (("braid","hair","wig","weave","loc","nail","lash","brow","makeup","beauty","barber","salon","facial","wax","spa","massage"),
   dict(name="The Signature {S} Experience", dream="hair and a look that lasts and gets compliments",
        proof="before-and-after photos and named client reviews", speed="one sitting, with a guaranteed start time",
        effort="long waits, sore scalp, sourcing products and unclear aftercare",
        likely=["A written longevity promise: a free touch-up within 7 days if anything comes loose","Before-and-after gallery of your own work at the booking link","A short consult before the day so there are no surprises"],
        fast=["Guaranteed start time, no waiting room","A second pair of hands on long styles to cut chair time","Priority booking for the next appointment"],
        easy=["Hair and products included, nothing to buy beforehand","Wash, prep and finish done in the same visit","WhatsApp aftercare check-in on day 3"],
        bonuses=["Take-home aftercare kit (satin bonnet or scarf and a care card)","A free touch-up visit within 2 weeks","First pick of booking slots for the next 3 months"])),
 "finance": (("bookkeep","account","tax","payroll","vat","financ","audit","admin"),
   dict(name="The {S} Peace of Mind Plan", dream="books that are always up to date and no SARS surprises",
        proof="client testimonials and the number of years with no late submissions", speed="month-end done by a fixed date",
        effort="chasing slips, late-night spreadsheets and not knowing where the money went",
        likely=["A deadline promise: if a submission is late because of you, that month's fee is waived","A named bookkeeper and a monthly 15-minute check-in","A clear onboarding checklist in week one"],
        fast=["Month-end report by a fixed day every month","Same-day replies on WhatsApp during business hours","Catch-up of past months done in the first 30 days"],
        effort_l=None,
        easy=["Slip capture by photo, no paper","You set up and run the software for them","Reminders sent for every SARS deadline"],
        bonuses=["A one-page monthly money summary in plain language","A free cash-flow forecast every quarter","A year-end tax prep session"])),
 "fitness": (("fitness","personal train","coach","yoga","pilates","gym","nutrition","diet","physio","wellness"),
   dict(name="The {S} Transformation Programme", dream="visible results and feeling strong and confident",
        proof="client progress photos and testimonials", speed="a clear 8 or 12 week plan with check-ins",
        effort="guessing what to eat, losing motivation and fitting sessions into a busy week",
        likely=["A results promise: keep going free until they hit an agreed, measurable goal","Weekly progress check with photos or measurements","A plan built on their own starting point"],
        fast=["A clear 12-week roadmap from day one","Two short sessions a week instead of long ones","Quick wins planned for the first 14 days"],
        easy=["Meal plan and shopping list done for them","Sessions at their home or online","WhatsApp accountability every week"],
        bonuses=["A starter meal plan and shopping list","A progress tracker with monthly reviews","One free session for a friend"])),
 "creative": (("photo","video","design","content","social","market","brand","web","copy"),
   dict(name="The {S} Done-For-You Package", dream="content and assets that bring in enquiries and make them look established",
        proof="portfolio pieces and client results", speed="delivery in a fixed number of days",
        effort="briefing, back-and-forth revisions and not knowing what to post",
        likely=["A revision promise: changes until they are happy, within the agreed brief","Portfolio of similar work shown upfront","A strategy call before any work starts"],
        fast=["Fixed delivery date, written into the agreement","First drafts within days, not weeks","A shoot or work day planned and booked in the first week"],
        easy=["You write the brief from one call","Captions, sizing and scheduling done for them","One point of contact on WhatsApp"],
        bonuses=["A content calendar for the next month","Extra short-form cuts from the same shoot","A 30-day check-in on what is working"])),
 "trades": (("plumb","electric","clean","garden","paint","build","repair","handyman","pest","pool","solar","renovat"),
   dict(name="The {S} No-Stress Service", dream="the job done properly the first time, with a clean site",
        proof="photos of finished jobs, reviews and certificates", speed="arrival within a set window",
        effort="waiting at home, unreliable quotes and cleaning up after",
        likely=["A workmanship guarantee: come back free if the same issue returns within 30 days","Certificates and insurance shown on the quote","A fixed written quote before work starts"],
        fast=["Arrival within a 2-hour window","Same-week booking for premium clients","All parts brought on the first visit"],
        easy=["Full clean-up included","Photos of the finished work sent to them","Reminders for the next service"],
        bonuses=["A free follow-up check after 30 days","A maintenance reminder schedule","Priority call-outs for 12 months"])),
}
DEFAULT = dict(name="The {S} Premium Package", dream="the result they came for, without the hassle",
        proof="reviews and examples of past results", speed="a clear timeline agreed upfront",
        effort="waiting, back-and-forth and doing parts of the work themselves",
        likely=["A clear promise: what happens if you miss the agreed result","Proof of past results shown upfront","A short planning step before you start"],
        fast=["A fixed delivery date","Quick first result in the first week","Priority scheduling"],
        easy=["Done-for-you setup","One point of contact","A follow-up check after delivery"],
        bonuses=["A written plan they keep","A follow-up session","Priority booking for repeat work"])

def premium_offer(res, d):
    svc = d.get("service", "").strip()
    low = svc.lower()
    cat, t = "general", DEFAULT
    for k, (kws, tpl) in CATS.items():
        if any(w in low for w in kws):
            cat, t = k, tpl; break
    dream = (d.get("dream") or "").strip() or t["dream"]
    proof = (d.get("proof") or "").strip()
    speed = (d.get("speed") or "").strip()
    pain = (d.get("pain") or "").strip() or t["effort"]
    has_proof = bool(proof)
    uplift = 0.15 + (0.10 if has_proof else 0)
    price = int(math.ceil(res["premium"] * (1 + uplift) / 50.0) * 50)
    return dict(
        category=cat, name=t["name"].format(S=svc.title()),
        dream=dream, pain=pain, proof=proof or t["proof"], has_proof=has_proof, speed=speed or t["speed"],
        levers=[("Dream outcome", f"Sell the result, not the hours: {dream}.",
                 ["Name the result in the package title and on your price list", "Show the finished result first, the process second"]),
                ("Likelihood of achievement", "Make it feel certain it will work." + ("" if has_proof else " Start collecting proof now, because you did not list any yet."),
                 ([f"Lead with your proof: {proof}"] if has_proof else []) + t["likely"][:2]),
                ("Time delay", f"Make the result arrive sooner: {speed or t['speed']}.", t["fast"][:2]),
                ("Effort and sacrifice", f"Take away what clients find annoying: {pain}.", t["easy"][:3])],
        bonuses=t["bonuses"], price=price, uplift_pct=int(uplift * 100),
        vs_rec=price - res["recommended"])
