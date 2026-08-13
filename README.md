# PII Redaction Tool

A web tool that takes a `.docx` file and returns a redacted copy with
personally identifiable information (PII) replaced by realistic **fake**
values (not just `[REDACTED]`), while preserving the original document's
formatting, tables, and layout.

**Live demo:** `<YOUR_DEPLOYED_URL_HERE>`
**PII types covered:** full names, emails, phone numbers, company names,
physical/mailing addresses, SSNs, credit card numbers, dates of birth, IP
addresses.

## Approach

**Hybrid regex + NER**, not pure regex and not pure ML:

- **Regex** handles PII with a predictable, structured format: emails,
  phone numbers, SSNs, credit card numbers (validated with a Luhn
  checksum to cut down false positives), IP addresses, and dates of birth
  (matched by looking for a DOB-indicating label like "DOB" / "Date of
  Birth" / "Born" within ~40 characters of a date).
- **spaCy NER** (`en_core_web_sm`) handles PII that has no fixed format:
  person names (`PERSON` → NAME) and company names (`ORG` → COMPANY).
  Physical addresses are handled with a regex heuristic (leading house/
  building number + street-type or locality keyword, e.g. "Street",
  "Road", "Nagar", "Village") rather than NER, since spaCy's `GPE`/`LOC`
  labels are too coarse (they tag "Pune" but not "45 Sarthak Nagar,
  Baner, Pune").

**Consistency:** every real value is mapped to one fake value for the
whole document, seeded by a hash of the real value, so "Rashi Patil"
becomes the same fake name everywhere it appears rather than a different
fake name each time (`app/redactor.py::Redactor._fake_for`).

**Overlap resolution:** when a regex match and an NER match overlap (e.g.
an ORG entity that accidentally swallows an IP address token), structured
regex types always win, since they're unambiguous by construction.

**DOCX handling:** we redact at the paragraph/cell level using
`python-docx`, not the raw XML, and write the result back into the first
run of each paragraph. This reliably catches PII that Word has split
across multiple runs (a common issue — a name typed with spell-check on
can end up split into 3+ runs in the underlying XML), at the cost of
collapsing any run-level formatting differences within a redacted
paragraph (e.g. if half a name was bold and half wasn't, the whole
replacement takes the first run's formatting).

## What counts as PII (scope decisions)

- Order/ticket/reference numbers (e.g. "Ticket #4521") are **not**
  treated as PII — they identify a case, not a person.
- Company registration/identity numbers (e.g. CIN numbers in the
  prospectus) are **not** redacted — they're public regulatory
  identifiers, not personal information, even though they sit next to a
  company name.
- Job titles alone (e.g. "Company Secretary") are **not** redacted; a
  title is only PII when tied to a specific name, and the name itself is
  what gets redacted.

## Known limitations / false positives & negatives

Observed during evaluation (see `eval/evaluation_report.json` for exact
numbers):

- **ALL-CAPS text confuses the NER model.** Legal documents like the
  prospectus often write names and company names in all caps (e.g.
  "WATERLOO INDUSTRIAL PARK VI PRIVATE LIMITED"). `en_core_web_sm` is
  trained mostly on mixed-case news/web text and sometimes misses
  entities written entirely in caps — a **false negative**.
- **Short, ambiguous ORG entities.** spaCy occasionally tags a bare
  acronym near other structured PII (e.g. the literal word "SSN" or
  "IP") as an ORG — a **false positive**. Low-impact since the noise
  value itself isn't sensitive, but it does slightly hurt COMPANY
  precision.
- **Ambiguous names can be mistagged as locations.** e.g. "Ananya
  Sharma" was tagged as two `GPE` (place) entities instead of one
  `PERSON` entity in testing — a **false negative**. This is a known
  weak spot of the small spaCy model on names that aren't common in its
  training data (particularly non-Western names outside a Western news
  corpus). Swapping in `en_core_web_trf` (transformer-based) or a model
  fine-tuned on Indian names would reduce this, at the cost of much
  higher latency/memory — not worth it for this assignment's scope, but
  is the natural next step for production use.
- **Free-text addresses without a recognizable street-type keyword** are
  missed by the regex heuristic (e.g. an address that's just a building
  name + city, with no "Road"/"Nagar"/etc. keyword).
- **Regex phone matching is intentionally loose** on digit count (8–13
  digits) to catch varied international formats; on documents with lots
  of other 8+ digit numbers (invoice totals, IDs) this can occasionally
  over-trigger. Credit card matching uses a Luhn checksum specifically to
  avoid this problem for that category.

## How to extend this to a new PII type

1. If it has a fixed format (like a passport number or a bank account
   number): add a regex to `PATTERNS` in `app/redactor.py`, add it to
   `PATTERN_ORDER`, and add a case to `Redactor._fake_for` for how to
   generate a fake replacement (Faker has providers for most common
   types).
2. If it doesn't have a fixed format (like a job title or a nationality):
   either extend the spaCy entity types you check for in
   `find_ner_matches` (spaCy's default model supports `PERSON`, `ORG`,
   `GPE`, `LOC`, `NORP`, `DATE`, etc.), or fine-tune a custom spaCy/
   transformer NER model on labeled examples of the new type.
3. Add the new type's priority to `_resolve_overlaps` so overlap
   resolution knows how confident to be in it relative to existing types.
4. Add labeled examples to `eval/test_data.py`'s `GROUND_TRUTH` and
   re-run `eval/run_eval.py` to confirm precision/recall on the new type.

## Project structure

```
pii-redactor/
├── app/
│   ├── main.py           # Flask web app (upload -> redact -> download)
│   ├── redactor.py        # Core detection + fake-value generation engine
│   └── docx_redactor.py   # DOCX-specific wrapper (paragraph/table/header handling)
├── templates/index.html   # Upload UI
├── eval/
│   ├── test_data.py       # Synthetic labeled ticket-log test set (all 9 PII types)
│   ├── run_eval.py        # Computes precision/recall/accuracy per type
│   └── evaluation_report.json
├── EVALUATION.md          # Evaluation methodology + results (readable version)
├── requirements.txt
├── Procfile                # for Render/Railway/Heroku-style deploys
└── render.yaml
```

## Running locally

```bash
pip install -r requirements.txt
python -m app.main
# open http://localhost:5000, upload a .docx, download the redacted result
```

Or via the command line, without the web UI:

```python
from app.docx_redactor import redact_docx
redact_docx("input.docx", "output_redacted.docx")
```

## Deploying

This repo is set up for **Render** (free tier) out of the box via
`render.yaml`:

1. Push this repo to GitHub.
2. On [render.com](https://render.com), New → Web Service → connect the
   repo → Render auto-detects `render.yaml`.
3. Deploy. First request after idling may take ~30s (free tier cold
   start) — expected, not a bug.

For Railway/Vercel/Netlify: use the same `requirements.txt` and start
command in `Procfile` (`gunicorn -w 2 -b 0.0.0.0:$PORT app.main:app`).
Vercel/Netlify are built for static/serverless sites, not long-running
Flask apps with file uploads — Render or Railway is a better fit here.

## Running the evaluation

```bash
python eval/run_eval.py
```

Prints and saves `eval/evaluation_report.json` with precision, recall,
and accuracy per PII type and overall. See `EVALUATION.md` for the full
writeup.
