"""Pricing engine. All assumptions are Hannah & Co working rules, shown in the report."""
import math

VAT = 0.15
UTILISATION = 0.75      # realistic share of your capacity that actually gets booked and paid
BUFFER = 0.20           # recommended price = floor + 20% for tax, leave, slow months and growth

# Hannah & Co working estimates when the owner picks "I'm not sure".
# Shown clearly as estimates in the report. Not market statistics.
ESTIMATE = {
    "costs": 2500,          # monthly: software, transport, products, small rent share
    "salary_target": 8000,  # monthly take-home the owner would like
    "salary_current": 0,    # if unsure what they take now, treat as unpaid
    "capacity": {
        "service": 8,       # bookings per week
        "hour": 20,         # billable hours per week
        "month": 4,         # clients at once
    },
}

REASON_LABELS = {
    "reinvest": "reinvesting in the business",
    "home_office": "home or office costs",
    "debt": "covering debt",
    "irregular": "irregular income",
    "not_enough": "not enough left after expenses",
    "other": "other reasons",
}

def experience_uplift(y):
    return 0.0 if y < 2 else 0.10 if y < 5 else 0.20 if y < 10 else 0.30

def r10(x):  # round up to a clean R10 price
    return int(math.ceil(x / 10.0) * 10)

def _f(v, default=0.0):
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)

def _truthy(v):
    return str(v).lower() in ("1", "true", "yes", "on")

def _reasons(d):
    raw = d.get("no_pay_reasons") or d.get("reasons") or []
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",") if x.strip()]
    out = []
    for r in raw:
        key = str(r).strip()
        if key in REASON_LABELS and key not in out:
            out.append(key)
    return out

def apply_estimates(d):
    """Resolve 'I'm not sure' flags into stated Hannah & Co working estimates.
    Returns (resolved_input_dict, estimates_used_dict).
    """
    basis = d.get("basis", "service")
    est = {}
    out = dict(d)

    if _truthy(d.get("costs_estimate")) or str(d.get("costs", "")).strip() == "":
        out["costs"] = ESTIMATE["costs"]
        est["costs"] = ESTIMATE["costs"]

    if _truthy(d.get("capacity_estimate")) or str(d.get("capacity", "")).strip() == "":
        out["capacity"] = ESTIMATE["capacity"].get(basis, ESTIMATE["capacity"]["service"])
        est["capacity"] = out["capacity"]

    # Current owner pay (what they actually take now)
    if _truthy(d.get("salary_estimate")) or str(d.get("salary", "")).strip() == "":
        out["salary"] = ESTIMATE["salary_current"]
        est["salary"] = ESTIMATE["salary_current"]

    # Target owner pay (what they want to take)
    if _truthy(d.get("salary_target_estimate")) or str(d.get("salary_target", "")).strip() == "":
        # If they typed a current salary > 0 and left target blank, default target to current.
        cur = _f(out.get("salary"), 0)
        out["salary_target"] = cur if cur > 0 else ESTIMATE["salary_target"]
        est["salary_target"] = out["salary_target"]
    else:
        out["salary_target"] = _f(d.get("salary_target"), 0)

    out["costs"] = _f(out.get("costs"), 0)
    out["salary"] = _f(out.get("salary"), 0)
    out["salary_target"] = _f(out.get("salary_target"), 0)
    out["capacity"] = _f(out.get("capacity"), 1)
    out["price"] = _f(out.get("price"), 0)
    out["years"] = _f(out.get("years"), 0)
    out["weeks"] = _f(out.get("weeks"), 46)
    out["duration"] = _f(out.get("duration"), 1)
    out["no_pay_reasons"] = _reasons(d)
    out["estimates"] = est
    return out, est

def compute(d):
    d, estimates = apply_estimates(d)
    basis = d.get("basis", "service")               # service | hour | month
    price = float(d["price"])
    years = float(d["years"])
    weeks = float(d["weeks"])
    costs_m = float(d["costs"])
    salary_now_m = float(d["salary"])               # what they take home now
    salary_target_m = float(d["salary_target"])     # what they want to take home
    # If target is blank/zero but they currently pay themselves, use current as target.
    if salary_target_m <= 0 and salary_now_m > 0:
        salary_target_m = salary_now_m
    # If both are zero and they didn't ask for an estimate, still use the working estimate
    # so the floor reflects a living wage target rather than "expenses only".
    if salary_target_m <= 0:
        salary_target_m = ESTIMATE["salary_target"]
        estimates = dict(estimates)
        estimates["salary_target"] = salary_target_m

    costs_y = costs_m * 12
    salary_now_y = salary_now_m * 12
    salary_target_y = salary_target_m * 12
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

    # Business expenses and owner pay are separate.
    # Break-even covers costs only. Floor covers costs + TARGET owner pay.
    # Recommended adds the buffer for tax, leave, slow months and reinvestment.
    need_costs = costs_y
    need_target = costs_y + salary_target_y
    need_now = costs_y + salary_now_y

    gross_full = net * cap_y
    gross_real = net * cap_y * UTILISATION
    hours_real = hrs_job * cap_y * UTILISATION
    true_hourly = (gross_real - costs_y) / hours_real if hours_real else 0
    breakeven = need_costs / (cap_y * UTILISATION) if cap_y else 0
    floor = need_target / (cap_y * UTILISATION) if cap_y else 0
    rec = floor * (1 + BUFFER)
    up = experience_uplift(years)
    prem = rec * (1 + up)
    g = lambda x: r10(x * (1 + VAT)) if vat else r10(x)    # price as charged to client
    per = (lambda v: v / weeks) if basis != "month" else (lambda v: v / 12 / (weeks / 52))
    jobs_now = need_target / net if net else float("inf")
    jobs_rec = need_target / rec if rec else float("inf")
    jobs_costs_only = need_costs / net if net else float("inf")
    cap_label = "per month" if basis == "month" else "per week"
    cap = float(d["capacity"])
    noun = {"month": "clients", "hour": "billable hours"}.get(basis, "bookings")
    noun1 = {"month": "client", "hour": "hour"}.get(basis, "booking")

    # Gap to target owner pay at current price
    surplus_after_costs = gross_real - costs_y
    owner_pay_afforded_y = max(0.0, surplus_after_costs)
    owner_pay_afforded_m = owner_pay_afforded_y / 12
    pay_gap_m = max(0.0, salary_target_m - owner_pay_afforded_m)
    pay_gap_y = pay_gap_m * 12
    # Extra clients/bookings needed at current price to hit target pay
    extra_jobs_y = (pay_gap_y / net) if net and pay_gap_y > 0 else 0.0
    extra_jobs = round(per(extra_jobs_y), 1) if extra_jobs_y else 0.0
    # Extra rand per job needed at current volume to hit target pay
    realistic_jobs = cap_y * UTILISATION
    extra_per_job = r10(pay_gap_y / realistic_jobs) if realistic_jobs and pay_gap_y > 0 else 0

    reasons = d.get("no_pay_reasons") or []
    reason_labels = [REASON_LABELS[r] for r in reasons if r in REASON_LABELS]
    unpaid = salary_now_m <= 0
    low_pay = (not unpaid) and salary_target_m > 0 and salary_now_m < salary_target_m * 0.5

    res = dict(
        noun=noun, noun1=noun1,
        basis=basis, unit=unit, cap_label=cap_label, vat=vat, price=price, net_price=round(net),
        capacity=cap, years=years, weeks=weeks,
        costs_m=round(costs_m), salary_now_m=round(salary_now_m), salary_target_m=round(salary_target_m),
        true_hourly=round(true_hourly), breakeven=g(breakeven), floor=g(floor),
        recommended=g(rec), premium=g(prem), uplift_pct=int(up * 100),
        needed_now=round(per(jobs_now), 1), needed_rec=round(per(jobs_rec), 1),
        needed_costs_only=round(per(jobs_costs_only), 1),
        capacity_pct_now=round(per(jobs_now) / cap * 100) if cap else 0,
        capacity_pct_rec=round(per(jobs_rec) / cap * 100) if cap else 0,
        revenue_real=round(gross_real),
        need=round(need_target), need_costs=round(need_costs), need_now=round(need_now),
        gap=round(need_target - gross_real),
        owner_pay_afforded_m=round(owner_pay_afforded_m),
        pay_gap_m=round(pay_gap_m),
        extra_jobs=extra_jobs,
        extra_per_job=extra_per_job,
        unpaid=unpaid, low_pay=low_pay,
        reasons=reasons, reason_labels=reason_labels,
        estimates=estimates,
        utilisation=int(UTILISATION * 100), buffer=int(BUFFER * 100),
    )
    if price < res["breakeven"]:
        v, tone = f"You are losing money on every {res['noun1']}", "red"
    elif price < res["floor"]:
        v, tone = "You cover costs, but you are not paying yourself enough", "amber"
    elif unpaid and pay_gap_m <= 0:
        v, tone = "You could pay yourself, but you are choosing not to", "amber"
    elif unpaid or pay_gap_m > 0:
        v, tone = "You cover costs, but you are not paying yourself enough", "amber"
    elif price < res["recommended"]:
        v, tone = "You cover the basics, with no room to breathe", "amber"
    elif price <= res["premium"]:
        v, tone = "Your price is healthy", "green"
    else:
        v, tone = "You are priced above your premium mark", "blue"
    res.update(verdict=v, tone=tone)

    # Write resolved values back so the report can show estimate labels from input.
    d["costs"] = costs_m
    d["salary"] = salary_now_m
    d["salary_target"] = salary_target_m
    d["capacity"] = cap
    d["estimates"] = estimates
    d["no_pay_reasons"] = reasons
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
    target = res["salary_target_m"]
    reasons = res.get("reason_labels") or []
    reason_txt = ""
    if reasons:
        if len(reasons) == 1:
            reason_txt = reasons[0]
        elif len(reasons) == 2:
            reason_txt = f"{reasons[0]} and {reasons[1]}"
        else:
            reason_txt = ", ".join(reasons[:-1]) + f", and {reasons[-1]}"

    if res["unpaid"] or res["pay_gap_m"] > 0:
        why = f" because of {reason_txt}" if reason_txt else ""
        title = "Pay yourself on purpose"
        if res["pay_gap_m"] <= 0:
            body = (
                f"You are not paying yourself{why}. After business costs, your current price already leaves about "
                f"R{res['owner_pay_afforded_m']:,} a month, which covers the R{target:,} you want. Decide a fixed owner pay, "
                f"take it first, and treat reinvestment or home costs as a separate planned amount. "
                f"Business costs and owner pay are separate."
            )
        else:
            bits = []
            if res["extra_jobs"]:
                bits.append(f"{res['extra_jobs']} more {res['noun']} {res['cap_label']}")
            if res["extra_per_job"]:
                bits.append(f"R{res['extra_per_job']:,} more per {res['noun1']}")
            how = " or ".join(bits) if bits else f"a move toward R{res['recommended']:,}"
            body = (
                f"You are not paying yourself{why}. After business costs, your current price leaves about "
                f"R{res['owner_pay_afforded_m']:,} a month for you. To take home R{target:,} a month you need "
                f"{how}. Business costs and owner pay are separate: covering rent and tools is not the same as paying yourself."
            )
        recs.append((title, body))
    elif p < res["floor"]:
        recs.append(("Move to your recommended price in two steps",
            f"Go to R{(p + res['recommended']) // 2:,.0f} for new clients now and R{res['recommended']:,} in 8 weeks. Tell existing clients 30 days ahead, with the reason in one line."))
    else:
        recs.append(("Hold your price and stop discounting",
            f"Your R{p:,.0f} covers your costs and the R{target:,} a month you want to pay yourself. Protect it: replace discounts with a paid add-on that raises the value of each {res['noun1']}."))

    if res["capacity_pct_now"] > 85:
        recs.append(("You are fully booked and still short",
            f"At today's price you need {res['needed_now']} {res['noun']} {res['cap_label']} to hit your target pay, which is {res['capacity_pct_now']}% of your capacity. Raising the price is the only fix that does not cost you more hours."))
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
    return recs[:3]


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
