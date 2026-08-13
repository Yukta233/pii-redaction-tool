"""
PII Redaction Engine
=====================
Hybrid approach:
  - Regex for *structured* PII with predictable formats:
      email, phone, SSN, credit card, IP address, date of birth
  - spaCy NER (en_core_web_sm) for *unstructured* PII that regex can't
    reliably catch: full names (PERSON), company names (ORG), and
    physical/mailing addresses (built from GPE/LOC/FAC entities + a
    regex-based street-address fallback).

Every detected PII value is mapped to a **consistent fake replacement**
using Faker, seeded per-document so the same real value always maps to
the same fake value everywhere it appears (e.g. "Rashi Patil" -> "John
Doe" on every occurrence, not a different fake name each time).
"""

import re
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
import spacy
from faker import Faker

nlp = spacy.load("en_core_web_sm")
fake = Faker()
Faker.seed(42)  # reproducible fake values across runs


@dataclass
class Match:
    start: int
    end: int
    text: str
    label: str  # PII category


# ---------------------------------------------------------------------------
# Regex patterns for structured PII
# ---------------------------------------------------------------------------
PATTERNS: Dict[str, str] = {
    "EMAIL": r"[a-zA-Z0-9.\-+_]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    # Credit card BEFORE phone: 13-19 digits, optionally grouped in 4s.
    "CREDIT_CARD": r"\b(?:\d[ -]?){13,19}\b",
    # SSN: strict US format 3-2-4
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    # IPv4
    "IP_ADDRESS": r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
    # Phone: optional country code, separators, 10 local digits
    "PHONE": r"(?:\+\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?\d{3,5}[\s-]?\d{3,4}[\s-]?\d{0,4}\b",
    # Date of birth: matched when a DOB-indicating label appears within ~40
    # non-digit characters before the date (handles phrasing like
    # "date of birth on file is 14/03/1990", not just "DOB: 14/03/1990").
    "DOB": r"(?i)(?:DOB|Date of Birth|Born|D\.O\.B\.?)[^\d]{0,40}(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}|[A-Z][a-z]+ \d{1,2},? \d{4})",
}

# Order matters: more specific / longer patterns first so they win overlaps.
PATTERN_ORDER = ["EMAIL", "CREDIT_CARD", "SSN", "IP_ADDRESS", "DOB", "PHONE"]

# Street-address heuristic: number + words + (Street/St/Road/Rd/Avenue/...) etc.
ADDRESS_REGEX = re.compile(
    r"\b\d{1,5}[A-Za-z]?(?:[,/]\s?\d{1,5}[A-Za-z]?)*[,\s]+[A-Z][A-Za-z'-]*"
    r"(?:\s[A-Z][A-Za-z'-]*){0,6}\s"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Village|Taluka|Nagar|Marg|"
    r"Colony|Sector|Block|Society|Chowk|Pune|Mumbai|Delhi|Bengaluru)\b"
    # trailing comma-separated segments (city/state/postal/country) --
    # deliberately excludes '.' so a sentence-ending period stops the match
    # instead of swallowing the next sentence.
    r"(?:[,\s]+[A-Za-z0-9\-–—]+){0,6}"
)

CC_CONTEXT_HINT = re.compile(r"card|visa|master|amex|payment", re.I)


def _is_plausible_credit_card(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    if not (13 <= len(digits) <= 19):
        return False
    return _luhn_check(digits)


def _luhn_check(digits: str) -> bool:
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _is_plausible_phone(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    return 8 <= len(digits) <= 13


def find_regex_matches(text: str) -> List[Match]:
    matches: List[Match] = []
    for label in PATTERN_ORDER:
        for m in re.finditer(PATTERNS[label], text):
            candidate = m.group(0)
            if label == "CREDIT_CARD" and not _is_plausible_credit_card(candidate):
                continue
            if label == "PHONE" and not _is_plausible_phone(candidate):
                continue
            if label == "DOB":
                # capture only the date portion (group 1) for replacement,
                # but keep full span so the label text isn't destroyed.
                date_start = m.start(1)
                date_end = m.end(1)
                matches.append(Match(date_start, date_end, m.group(1), label))
                continue
            matches.append(Match(m.start(), m.end(), candidate, label))
    return matches


def find_address_matches(text: str) -> List[Match]:
    return [Match(m.start(), m.end(), m.group(0), "ADDRESS") for m in ADDRESS_REGEX.finditer(text)]


def find_ner_matches(text: str) -> List[Match]:
    """Run spaCy NER per-line rather than on the whole blob. Real PII
    labels (names, companies) live on single lines/paragraph fields; letting
    entities span line breaks causes the model to glue adjacent fields
    together (e.g. "Rashi Patil\\nEmail" as one PERSON span). Processing
    line-by-line also lets us batch efficiently with nlp.pipe for speed on
    long documents."""
    matches: List[Match] = []
    lines = text.splitlines(keepends=True)
    offsets = []
    running = 0
    for line in lines:
        offsets.append(running)
        running += len(line)

    stripped = [ln.rstrip("\n").rstrip("\r") for ln in lines]
    for doc, offset in zip(nlp.pipe(stripped, batch_size=200), offsets):
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                matches.append(Match(offset + ent.start_char, offset + ent.end_char, ent.text, "NAME"))
            elif ent.label_ == "ORG":
                matches.append(Match(offset + ent.start_char, offset + ent.end_char, ent.text, "COMPANY"))
    return matches


def _resolve_overlaps(matches: List[Match]) -> List[Match]:
    """Greedy interval selection that resolves overlaps by PRIORITY first
    (structured regex types > address > NAME/COMPANY), and only falls back
    to "earliest start, then longest" to break ties within the same
    priority tier. This matters because a loose NER guess (e.g. an ORG
    entity that swallows an IP address token) can start earlier in the
    text than the precise regex match for the same span -- priority must
    win regardless of which one starts first, or the sloppy match blocks
    the precise one."""
    priority = {
        "EMAIL": 0, "SSN": 0, "CREDIT_CARD": 0, "IP_ADDRESS": 0, "DOB": 0, "PHONE": 0,
        "ADDRESS": 1, "NAME": 2, "COMPANY": 2,
    }
    ordered = sorted(matches, key=lambda m: (priority[m.label], m.start, -(m.end - m.start)))
    result: List[Match] = []
    occupied: List[Tuple[int, int]] = []
    for m in ordered:
        if any(not (m.end <= s or m.start >= e) for s, e in occupied):
            continue
        result.append(m)
        occupied.append((m.start, m.end))
    return sorted(result, key=lambda m: m.start)


class Redactor:
    """Stateful redactor: keeps a consistent real -> fake mapping for the
    whole document (and can be reused across multiple documents if you
    want the same person to map to the same fake identity everywhere)."""

    def __init__(self):
        self.mapping: Dict[str, str] = {}
        self._used_fakes = set()

    def _fake_for(self, real_value: str, label: str) -> str:
        key = (label, real_value.strip().lower())
        cache_key = f"{label}:{real_value.strip().lower()}"
        if cache_key in self.mapping:
            return self.mapping[cache_key]

        seed = int(hashlib.sha256(real_value.encode()).hexdigest(), 16) % (2**32)
        local_fake = Faker()
        local_fake.seed_instance(seed)

        if label == "NAME":
            val = local_fake.name()
        elif label == "COMPANY":
            val = local_fake.company()
        elif label == "EMAIL":
            val = local_fake.free_email()
        elif label == "PHONE":
            # preserve a plausible "+countrycode local" shape
            val = "+91 " + str(local_fake.random_number(digits=10, fix_len=True))
        elif label == "SSN":
            val = local_fake.ssn()
        elif label == "CREDIT_CARD":
            val = local_fake.credit_card_number()
        elif label == "IP_ADDRESS":
            val = local_fake.ipv4()
        elif label == "DOB":
            val = local_fake.date_of_birth().strftime("%d/%m/%Y")
        elif label == "ADDRESS":
            val = local_fake.address().replace("\n", ", ")
        else:
            val = "[REDACTED]"

        self.mapping[cache_key] = val
        return val

    def redact(self, text: str) -> Tuple[str, List[Dict]]:
        matches = find_regex_matches(text)
        matches += find_address_matches(text)
        matches += find_ner_matches(text)
        matches = _resolve_overlaps(matches)

        out = []
        last = 0
        log = []
        for m in matches:
            out.append(text[last:m.start])
            fake_val = self._fake_for(m.text, m.label)
            out.append(fake_val)
            log.append({"type": m.label, "original": m.text, "replacement": fake_val,
                        "start": m.start, "end": m.end})
            last = m.end
        out.append(text[last:])
        return "".join(out), log
