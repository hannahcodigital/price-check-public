"""Where Price Check reports are kept.

DATABASE_URL set  -> a Postgres table (needed on Render's free tier, whose disk is wiped
                     every time the app sleeps after 15 idle minutes, restarts or redeploys).
DATABASE_URL unset -> JSON files in reports/ (fine on this computer for demos).
"""
import json, os

URL = os.environ.get("DATABASE_URL", "")
RDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
os.makedirs(RDIR, exist_ok=True)

if URL:
    import psycopg
    from psycopg.types.json import Jsonb

    def _conn():
        return psycopg.connect(URL, autocommit=True, connect_timeout=15)

    # gunicorn starts two workers at once; the lock stops them racing to create the table.
    with psycopg.connect(URL, connect_timeout=15) as c, c.transaction():
        c.execute("select pg_advisory_xact_lock(4207)")
        c.execute("create table if not exists price_check_reports ("
                  "id text primary key, ts text, data jsonb not null)")

    def save(rep):
        with _conn() as c:
            c.execute("insert into price_check_reports (id, ts, data) values (%s, %s, %s) "
                      "on conflict (id) do update set ts = excluded.ts, data = excluded.data",
                      (rep["id"], rep.get("ts", ""), Jsonb(rep)))

    def get(rid):
        with _conn() as c:
            row = c.execute("select data from price_check_reports where id = %s", (rid,)).fetchone()
        return row[0] if row else None

    def all_reports():
        with _conn() as c:
            return [r[0] for r in c.execute("select data from price_check_reports order by ts desc")]
else:
    def _path(rid): return os.path.join(RDIR, f"{os.path.basename(rid)}.json")

    def save(rep):
        with open(_path(rep["id"]), "w") as f: json.dump(rep, f, indent=1)

    def get(rid):
        p = _path(rid)
        if not os.path.exists(p): return None
        with open(p) as f: return json.load(f)

    def all_reports():
        reps = []
        for name in os.listdir(RDIR):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(RDIR, name)) as f: reps.append(json.load(f))
                except Exception: pass
        return sorted(reps, key=lambda r: r.get("ts", ""), reverse=True)
