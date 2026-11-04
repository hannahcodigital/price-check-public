# The Price Check (Hannah & Co Growth) - demo

Run:
    pip install --break-system-packages flask ddgs requests beautifulsoup4
    python3 app.py            # http://localhost:8090  (PORT env to change)

Files: app.py (Flask routes, PDF via headless Chrome), engine.py (pricing maths + recommendations),
research.py (DuckDuckGo search via ddgs, page fetch, rand price regex), templates/, static/, reports/ (saved JSON + PDFs).
CLI test of research: python3 research.py "box braids" "Randburg, Johannesburg" [service|hour|month]
Payment step is a placeholder (no gateway). Needs google-chrome on PATH for PDFs.

## Go-live settings (2026-10-18)
Env vars: PAYWALL=1 (0 = demo, no payment), PAY_LINK (bank payment request link), EFT_DETAILS, ADMIN_KEY (long random secret), PRICE=99.
Flow: customer builds report -> gets reference PCxxxx + pay link/EFT -> Hannah opens /admin?key=ADMIN_KEY, matches reference, presses Unlock -> customer's page unlocks itself.
PDF: uses Chrome if present, otherwise falls back to the browser's Save as PDF (print layout).
Production: gunicorn -w 2 -t 120 -b 0.0.0.0:$PORT app:app   (research takes ~25 s, keep timeout >= 120)
Backup of the pre-change version: ../pricing-calculator.bak-20261018

## Storage for Render (2026-10-18, evening)
Render's free tier wipes the app's disk whenever it sleeps (after 15 idle minutes), restarts or redeploys, so reports saved as files
would vanish before Hannah could unlock a paid order. storage.py now keeps reports in Postgres when DATABASE_URL is set
(use a Neon free project: permanent free plan, no card, 1 GB). Without DATABASE_URL it still uses reports/ (local demos).
Deploy: render.yaml is a ready Render Blueprint (free plan); enter DATABASE_URL, PAY_LINK, EFT_DETAILS, ADMIN_KEY in the dashboard.
Tested: unpaid order created, disk wiped and app restarted, order still listed in /admin, unlocked, report opens.
Free-tier note: first visit after sleeping takes about a minute to wake up.
Backup of the pre-storage version: ../pricing-calculator.bak-20261018-storage
