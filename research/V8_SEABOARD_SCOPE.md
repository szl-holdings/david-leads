# V8 — Genius Seaboard (locked scope)

**Prepared:** Sunday, June 28, 2026. **For:** David Abraham (New York Life) lead-intelligence app.
**Builds on:** V7 (East Coast multi-state + tax/wealth + Open the Black Box), merged to `main` via PR #6.
**Doctrine:** SZL governed-AI · public-data-only · honest by design. Conjectural items stay labelled. Never fake a signature; UNSIGNED receipts are honest receipts.

---

## 0. The three genius features (locked)

1. **Territory Pulse** — a live, ranked "pulse" of the 13-state Atlantic seaboard showing where the freshest lead-generating public activity is happening right now. Each state's pulse is computed from its **free, keyless, machine-readable** open-data richness (carried directly from the V7 `V7_MULTISTATE.md` research) × current freshness. The advisor sees, at a glance, which territories are "hot" today and why. New endpoint: `GET /api/pulse`.
2. **Signed 4-Part Brief** — every lead now carries a structured, citation-grounded **four-part brief** wrapped in a single signed receipt:
   - **WHO** — the prospect segment + the public signal that surfaced them.
   - **WHY NOW** — the time-sensitive trigger (with the dated public source).
   - **PRODUCT** — the matched NYL product + the suitability rationale.
   - **NEXT ACTION** — the concrete advisor move + talk track + a freshness deadline.
   Each part lists its public-data citations; the whole brief hashes into one tamper-evident, optionally ECDSA-P256-signed receipt.
3. **Λ with time-decay** — the transparent Λ-score gains an explicit, disclosed **time-decay** term on the `recency` axis: `recency_effective = recency_base × exp(−decay_rate × age_minutes)`. A lead's freshness erodes honestly over time, operationalizing the **speed-to-lead < 60s** promise: a HOT lead acted on within the first minute keeps full recency; one left for hours visibly cools. Fully inspectable in the model card.

## 1. The 13-state seaboard (locked roster)

Ordered by V7-verified free open-data richness (the Territory Pulse base weight). Atlantic seaboard, north→south, scored 0–4 from `V7_MULTISTATE.md` §1:

| # | State | Code | V7 data-richness (0–4) | Portal type | Notes |
|---|-------|------|------------------------|-------------|-------|
| 1 | Connecticut | CT | 4.0 | Socrata `data.ct.gov` | Best in class — daily formations + licenses + sales/CAMA |
| 2 | Delaware | DE | 3.5 | Socrata `data.delaware.gov` | Daily biz + individual pro licenses |
| 3 | District of Columbia | DC | 3.5 | ArcGIS `opendata.dc.gov` | Daily biz license + permits |
| 4 | Pennsylvania | PA | 2.0 | Socrata `data.pa.gov` | Named statewide biz registrations |
| 5 | Maryland | MD | 2.0 | Socrata `opendata.maryland.gov` | 2.4M-parcel statewide assessments |
| 6 | Virginia | VA | 2.0 | CKAN → city portals | Norfolk + Virginia Beach feeds |
| 7 | New York | NY | 2.0* | Socrata `data.ny.gov` | App's original home state (DOS, ACRIS, licenses) |
| 8 | Florida | FL | 1.5 | SFTP bulk + county ArcGIS | Sunbiz daily files (parse step) |
| 9 | New Jersey | NJ | 1.0 | Socrata `data.nj.gov` (thin) | Construction permits + bulk roster |
| 10 | Rhode Island | RI | 0.5 | Providence Socrata (stale) | Property tax rolls only |
| 11 | Massachusetts | MA | 0.0 (API) | Download portal / gated API | Flagged gap — no keyless bulk API |
| 12 | New Hampshire | NH | 0.0 | None | Flagged gap — HTML-only |
| 13 | Maine | ME | 0.0 | None verified | Flagged gap — included for seaboard completeness; pulse = baseline only |

\* NY richness held at 2.0 as a conservative floor; the app already ingests NY DOS/ACRIS/licenses live (V2–V6).

**Honest-by-design note:** MA/NH/ME have no verified keyless statewide API for our categories as of 2026-06-28. They appear in the seaboard roster and Territory Pulse at a **baseline** weight and are explicitly flagged as data gaps — never shown as live-rich when they are not.

## 2. Why this wins the meeting

- Territory Pulse turns David's "where do I prospect?" into a data-backed, one-glance answer across his whole Northeast/Atlantic footprint.
- The Signed 4-Part Brief is the boardroom artifact: a single screen David can read aloud to a prospect, every claim cited and cryptographically receipted.
- Λ time-decay makes "speed-to-lead" visible and honest — it is the live proof that fresh leads are worth more, which is exactly the behavior NYL wants to drive.

## 3. Non-goals (locked out of V8)

- No paid data sources. No private PII. No fabricated signals or signatures.
- No promotion of Λ beyond Conjecture status in any copy (SZL Doctrine).
- No change to the existing visual identity / CSS tokens.
