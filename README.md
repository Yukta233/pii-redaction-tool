# PII Redaction Tool

A web tool that takes a `.docx` file and returns a redacted copy with
personally identifiable information (PII) replaced by realistic **fake**
values (not just `[REDACTED]`), while preserving the original document's
formatting, tables, and layout.

**Live demo:** https://pii-redaction-tool-8ud9.onrender.com/
**PII types covered:** full names, emails, phone numbers, company names,
physical/mailing addresses, SSNs, credit card numbers, dates of birth, IP
addresses.

## Approach

Hybrid regex + NER, not pure regex and not pure ML.

Regex handles anything with a predictable, structured format: emails,
phone numbers, SSNs, credit card numbers (validated with a Luhn checksum
to cut down false positives), IP addresses, and dates of birth (matched
by looking for a DOB-indicating label like "DOB" / "Date of Birth" /
"Born" within ~40 characters of a date, rather than matching any bare
date pattern).

spaCy NER (`en_core_web_sm`) handles the PII that doesn't have a fixed
shape: person names (`PERSON` → NAME) and company names (`ORG` →
COMPANY). Physical addresses turned out to be a special case — spaCy's
`GPE`/`LOC` labels are too coarse for them (it'll tag "Pune" fine but
won't grab "45 Sarthak Nagar, Baner, Pune" as one span), so addresses
use a regex heuristic instead: a leading house/building number followed
by a street-type or locality keyword ("Street", "Road", "Nagar",
"Village", etc.).

Every real value maps to one fake value across the whole document — the
fake is seeded from a hash of the real value, so "Rashi Patil" becomes
the same fake name everywhere it shows up rather than a different one
each time (`app/redactor.py::Redactor._fake_for`).

When a regex match and an NER match overlap (e.g. an ORG entity that
accidentally swallows part of an IP address), the regex match wins —
those types are unambiguous by construction, so there's no reason to
defer to the NER guess.

DOCX handling redacts at the paragraph/cell level using `python-docx`,
not the raw XML, and writes the result back into the first run of each
paragraph. This is what reliably catches PII that Word has split across
multiple runs — a name typed with spell-check on can end up split into
3+ runs in the underlying XML — but it costs run-level formatting
precision: if half a name was bold and half wasn't, the replacement
takes on the first run's formatting for the whole span.

## What counts as PII (scope decisions)

- Order/ticket/reference numbers ("Ticket #4521") aren't treated as
  PII — they identify a case, not a person.
- Company registration/identity numbers (CIN numbers in the prospectus,
  for instance) aren't redacted — they're public regulatory
  identifiers, even sitting right next to a company name.
- Job titles alone ("Company Secretary") aren't redacted; a title is
  only PII when it's tied to a specific name, and it's the name that
  gets redacted, not the title.

## Known limitations

Numbers behind these are in `eval/evaluation_report.json`.

ALL-CAPS text trips up the NER model. Legal documents like the
prospectus often write names and companies in all caps ("WATERLOO
INDUSTRIAL PARK VI PRIVATE LIMITED"), and `en_core_web_sm` — trained
mostly on mixed-case news/web text — misses entities written entirely
in caps more often than it should. That's a false negative, and it's
the biggest gap the small synthetic test set didn't catch.

spaCy also occasionally tags a bare acronym near other PII as an ORG —
the literal word "SSN" or "IP" got flagged in testing. Low-impact since
the value itself isn't sensitive, but it does drag down COMPANY
precision.

Names can get mistagged as locations. "Ananya Sharma" came back as two
separate `GPE` (place) entities instead of one `PERSON` in testing —
a weak spot of the small spaCy model on names it hasn't seen much of in
training, particularly names outside a Western news corpus. A
transformer model (`en_core_web_trf`) or one fine-tuned on Indian names
would help here; I didn't use one because of the latency/memory cost,
but it's the obvious next step if this went to production.

Free-text addresses without a recognizable street-type keyword get
missed by the regex heuristic — e.g. a building name plus city, with no
"Road"/"Nagar"/etc. anywhere in it.

Phone matching is intentionally loose on digit count (8–13 digits) to
catch varied international formats, which means documents with a lot of
other 8+ digit numbers (invoice totals, IDs) can occasionally
over-trigger it. Credit card matching uses a Luhn checksum specifically
to avoid that problem for that category.

## How to extend this to a new PII type

1. Fixed format (passport number, bank account number): add a regex to
   `PATTERNS` in `app/redactor.py`, add it to `PATTERN_ORDER`, and add a
   case to `Redactor._fake_for` for how to generate a fake replacement
   (Faker has providers for most common types).
2. No fixed format (job title, nationality): either extend the spaCy
   entity types checked in `find_ner_matches` (spaCy's default model
   also has `GPE`, `LOC`, `NORP`, `DATE`, etc.), or fine-tune a custom
   NER model on labeled examples.
3. Add the new type's priority to `_resolve_overlaps` so overlap
   resolution knows how much to trust it relative to existing types.
4. Add labeled examples to `eval/test_data.py`'s `GROUND_TRUTH` and
   re-run `eval/run_eval.py` to check precision/recall on the new type.

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

Or from the command line, without the web UI:

```python
from app.docx_redactor import redact_docx
redact_docx("input.docx", "output_redacted.docx")
```

## Deploying

Set up for Render (free tier) out of the box via `render.yaml`:

1. Push this repo to GitHub.
2. On [render.com](https://render.com), New → Web Service → connect the
   repo → Render auto-detects `render.yaml`.
3. Deploy. First request after idling may take ~30s (free tier cold
   start) — expected, not a bug.

For Railway/Vercel/Netlify: same `requirements.txt`, and the start
command from `Procfile`:
```
gunicorn -w 2 -b 0.0.0.0:$PORT --timeout 120 app.main:app
```
Vercel/Netlify are built for static/serverless sites, not long-running
Flask apps with file uploads — Render or Railway fits better here.

## Running the evaluation

```bash
python eval/run_eval.py
```

Prints and saves `eval/evaluation_report.json` with precision, recall,
and accuracy per PII type and overall. Full writeup in `EVALUATION.md`.
