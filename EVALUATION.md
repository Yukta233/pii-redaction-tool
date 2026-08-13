# Evaluation Strategy & Results

## Why a synthetic test set instead of just the prospectus

`Red_Herring_Prospectus.docx` is a real filing, so it only contains four
of the nine PII types we're asked to handle — names, companies,
addresses, emails, phone numbers. There's no SSN, credit card, DOB, or
IP address anywhere in it (a securities filing wouldn't have those), and
there's no ground truth for it either — nobody has hand-labeled which of
the ~2,300 name-like occurrences in a 400-page document are actually
correct.

So I split this into two checks:

1. A small hand-labeled synthetic document (a support-ticket log, same
   format as the assignment brief) covering all 9 PII types with known
   ground truth. The precision/recall numbers below come from this.
2. Running the real tool against the actual prospectus and spot-checking
   the output — this doesn't produce a score, but it's the only way to
   see how the tool behaves at real document scale and formatting.

## Ground truth

`eval/test_data.py` has a 4-ticket synthetic log plus a hand-built list
of every PII instance in it as `(type, exact_text)` pairs — including
deliberate repeats, e.g. an email quoted twice in one ticket should be
detected twice. 30 labeled instances total, across all 9 types, with
some non-PII noise mixed in (ticket numbers, order refs) to check the
tool doesn't over-redact.

## How matching works

I compare detections and ground truth as multisets of
`(type, normalized_value)`, not by character offset — what matters here
is whether the right value got flagged as the right type the right
number of times, not exact spans. Values are whitespace-normalized
before comparing.

- **TP** — a detection matches a ground-truth pair.
- **FP** — a detection with no matching ground-truth pair (redacted
  something that isn't PII, or tagged it as the wrong type).
- **FN** — a ground-truth pair with nothing matching it (missed real
  PII).

## Metrics

```
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
Accuracy  = TP / (TP + FP + FN)
```

I'm using this accuracy formula instead of the classic
`(TP+TN)/(TP+TN+FP+FN)` because true negatives — every substring that
correctly wasn't flagged — aren't a well-defined, bounded quantity in
free text. This is the usual way accuracy gets defined for span
extraction / NER tasks.

## Results

### Overall

| Metric | Value |
|---|---|
| Precision | 0.875 (28 / 32) |
| Recall | 0.933 (28 / 30) |
| Accuracy | 0.824 (28 / 34) |
| TP | 28 |
| FP | 4 |
| FN | 2 |

### By type

| Type | Precision | Recall | Accuracy | TP | FP | FN |
|---|---|---|---|---|---|---|
| Email | 1.00 | 1.00 | 1.00 | 7 | 0 | 0 |
| Phone | 1.00 | 1.00 | 1.00 | 5 | 0 | 0 |
| SSN | 1.00 | 1.00 | 1.00 | 2 | 0 | 0 |
| Credit Card | 1.00 | 1.00 | 1.00 | 2 | 0 | 0 |
| IP Address | 1.00 | 1.00 | 1.00 | 2 | 0 | 0 |
| Date of Birth | 1.00 | 1.00 | 1.00 | 2 | 0 | 0 |
| Address | 1.00 | 1.00 | 1.00 | 2 | 0 | 0 |
| Name | 0.75 | 0.75 | 0.60 | 3 | 1 | 1 |
| Company | 0.50 | 0.75 | 0.43 | 3 | 3 | 1 |

Every regex-based category is perfect — those formats are unambiguous,
so this isn't surprising. The two NER-dependent categories (Name,
Company) are noticeably weaker. That's a small general-purpose model
doing what small general-purpose models do; here's specifically where
it broke.

## Error analysis

**Missed (2):**
- `NAME — "Ananya Sharma"` — spaCy split this into two `GPE` (place)
  entities instead of one `PERSON`.
- `COMPANY — "Waterloo Industrial Park VI Private Limited"` — tagged as
  `PERSON` instead of `ORG`.

**Wrongly flagged (4):**
- `COMPANY — "SSN"` — the bare acronym got tagged as an org.
- `COMPANY — "IP"` — same problem, near the phrase "IP address."
- `NAME — "Waterloo Industrial Park VI Private Limited"` — the flip
  side of the missed company above: one wrong label produces both a
  miss (wrong type) and a false positive (right span, wrong type) at
  once.
- *[fourth company false positive — pull the exact value from
  `eval/evaluation_report.json`, since the report needs the real text
  here, not a guess]*

All of these trace back to the same thing: `en_core_web_sm` is trained
on general news/web text and struggles with names or short capitalized
tokens it hasn't seen much of. None of the regex detectors (email,
phone, SSN, credit card, IP, DOB) got anything wrong on the test set —
which makes sense, since those formats don't leave much room for
ambiguity.

## What I chose not to treat as PII

- Ticket/order/reference numbers ("Ticket #4521") — these identify a
  case, not a person.
- Company registration/CIN numbers — public regulatory identifiers.
- Job titles with no name attached.

## Running it against the real prospectus

`Red_Herring_Prospectus.docx` (400+ pages) went through the full
pipeline end to end: 4,521 total redactions — 2,321 names, 2,040
companies, 82 phone numbers, 70 emails, 8 addresses, and 0 of
SSN/credit card/DOB/IP (expected, given the document type). I converted
the output to PDF and checked it visually — table formatting, colors,
and layout all survived redaction.

One thing the small synthetic set didn't surface: **entities written in
ALL CAPS** — common in legal boilerplate, e.g. promoter and company
names on the cover page — get missed by spaCy noticeably more often
than mixed-case text does. That's a real, document-specific recall gap
worth knowing about; it's called out in `README.md` under "Known
limitations."

## Reproducing this

```bash
python eval/run_eval.py
```

Prints the same numbers above to stdout and writes them to
`eval/evaluation_report.json`.