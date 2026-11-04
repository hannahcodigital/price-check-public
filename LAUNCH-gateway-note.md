# Price Check launch: payment options (checked 29 Oct 2026)

Price Check already works without a gateway: customer gets a PC reference + Hannah's bank payment request link / EFT,
Hannah unlocks the report in /admin. Zero fees. Downside: manual unlock (customer waits until she presses Unlock).

Gateway cost on one R99 sale (local card, published rates, incl. 15% VAT):
- Paystack 2.9% + R1 ex VAT  -> about R4.45 (source: centrapoint.co.za Sept 2026 table; confirm on paystack.com)
- Yoco online 2.95% + R2 ex VAT -> about R5.66; once-off signup fee if no Yoco card machine (support.yoco.help Core Plan)
- PayFast card 3.2% + R2 ex VAT -> about R5.94, plus R8.70 ex VAT per payout to bank (payfast.io/fees)
A gateway only adds automatic unlock; it would need a small code change (webhook) once one is chosen.

Remaining launch steps (bank-link version): free Neon database -> DATABASE_URL; free Render deploy from render.yaml;
set PAY_LINK, EFT_DETAILS, ADMIN_KEY; point pricecheck.hannahcodigital.com at Render; one selling video.
