# Evaluation Strategy & Metrics Report

## 1. Why a synthetic test set, not just the prospectus

The provided document (`Red_Herring_Prospectus.docx`) is a real IPO
filing. It genuinely contains four of the nine required PII types —
names, company names, addresses, emails, and phone numbers — but it
does **not** naturally contain SSNs, credit card numbers, dates of
birth, or IP addresses (these don't belong in a securities filing).

Evaluating only against the prospectus would leave 4 of 9 required PII
types completely untested, and there is no ground truth for it anyway
(nobody has manually labeled which of the ~2,300 name occurrences and
~2,000 company mentions in a 400+ page filing are "correct").

So the evaluation uses **two complementary checks**:

1. **Quantitative** — a small, hand-labeled synthetic document styled as
   a support-ticket log (matching the format shown in the assignment
   brief), covering all 9 PII types with a known ground truth. This is
   what the precision/recall/accuracy numbers below are computed from.
2. **Qualitative** — running the tool on the real prospectus and
   visually inspecting the rendered output (converted to PDF) to confirm
   formatting/layout survives redaction and spot-check for obviously
   missed or wrongly-redacted content at full document scale (see
   "Qualitative check" section below).

## 2. Ground truth construction

`eval/test_data.py` contains a 4-ticket synthetic document and a
hand-built list of every PII instance in it: `(pii_type, exact_text)`
pairs, including deliberate repeats (e.g. an email address quoted twice
in one ticket counts as two expected detections, matching what should
happen in the real redacted output).

29 labeled PII instances total, covering all 9 required types plus
realistic noise around them (ticket numbers, order references) to test
that non-PII isn't over-redacted.

## 3. Matching method

Detections and ground truth are compared as **multisets** of
`(pii_type, normalized_value)` — not by exact character span — because
what matters for this task is "did the right *value* get flagged as the
right *type* the right number of times," not exact offsets. Values are
whitespace-normalized before comparison.

- **True Positive (TP):** a detection matches a ground-truth
  `(type, value)` pair.
- **False Positive (FP):** a detection with no matching ground-truth
  pair (something was redacted that shouldn't have been, or was tagged
  as the wrong type).
- **False Negative (FN):** a ground-truth pair with no matching
  detection (real PII that was missed).

## 4. Metrics

```
Precision = TP / (TP + FP)   — of what we redacted, how much was really PII
Recall    = TP / (TP + FN)   — of all real PII, how much did we catch
Accuracy  = TP / (TP + FP + FN)
```

Accuracy is defined over the union of detected + expected items rather
than the classic `(TP+TN)/(TP+TN+FP+FN)`, because "true negatives"
(every possible substring that correctly wasn't flagged) is unbounded in
free text and not a meaningful quantity here — this is standard practice
for span-extraction tasks like NER and information extraction.

## 5. Results

### Overall

| Metric | Value |
|---|---|
| Precision | **0.875** (28 / 32) |
| Recall | **0.933** (28 / 30) |
| Accuracy | **0.824** (28 / 34) |
| True Positives | 28 |
| False Positives | 4 |
| False Negatives | 2 |

### Per PII type

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

**Reading this:** every regex-detected category (structured formats)
hits perfect precision and recall on the test set, as expected — these
formats are unambiguous. The two NER-dependent categories (Name,
Company) are meaningfully weaker, which is expected and typical for
small general-purpose NER models; see error analysis below.

## 6. Error analysis

**False negatives (2):**
- `NAME — "Ananya Sharma"`: spaCy's small model tagged this as two
  separate `GPE` (place) entities instead of one `PERSON` entity.
- `COMPANY — "Waterloo Industrial Park VI Private Limited"`: tagged as
  `PERSON` instead of `ORG` by the same model (name/company confusion
  goes both directions).

**False positives (4):**
- `COMPANY — "SSN"`: the bare acronym "SSN" was mistagged as an ORG in
  one sentence.
- `COMPANY — "IP"`: same issue with the token "IP" near "IP address".
- `NAME — "Waterloo Industrial Park VI Private Limited"`: the flip side
  of the false negative above — one wrong label produces both an FN
  (for the correct type) and an FP (for the wrong type) simultaneously.

All four errors trace back to the same root cause: **`en_core_web_sm` is
a small, general-purpose model** trained on mixed-case news/web text,
and it occasionally confuses PERSON/ORG/GPE on names it hasn't seen much
of in training, or on short capitalized tokens near other flagged
content. None of the structured-format regex detectors (email, phone,
SSN, credit card, IP, DOB) produced a single error on the test set.

## 7. Design choice: what does NOT count as PII

To keep precision meaningful, the following are **intentionally not**
treated as PII (stated explicitly, per the assignment's evaluation
criteria):

- Ticket/order/reference numbers (e.g. "Ticket #4521") — identify a
  case, not a person.
- Company registration/CIN numbers — public regulatory identifiers.
- Standalone job titles without an attached name.

## 8. Qualitative check on the real document

`Red_Herring_Prospectus.docx` (400+ pages) was run through the full
pipeline end-to-end. Result: 4,521 total redactions (2,321 names, 2,040
companies, 82 phone numbers, 70 emails, 8 addresses; 0 SSN/credit
card/DOB/IP instances found, as expected for this document type). The
output was converted to PDF and visually spot-checked to confirm table
formatting, colors, and layout were preserved after redaction. One
limitation observed at this scale that the small synthetic test set
didn't surface: **entities written in ALL CAPS** (common in legal
boilerplate, e.g. promoter names and company names on the cover page)
are missed by spaCy more often than mixed-case text — a lower-recall
condition specific to this document's formatting register. This is
documented in `README.md` under "Known limitations."

## 9. How to reproduce

```bash
python eval/run_eval.py
```
Outputs the same numbers above to stdout and to `eval/evaluation_report.json`.
