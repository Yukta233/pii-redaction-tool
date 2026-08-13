"""
Evaluation harness.

Method: multiset matching by (pii_type, normalized_text_value).
For each PII type we compute:
  TP = detections that match a ground-truth (type, value) pair
  FP = detections that don't match any ground-truth pair (false alarms)
  FN = ground-truth pairs with no matching detection (missed PII)

Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
Accuracy  = TP / (TP + FP + FN)   [a strict "how much of the union did we get right" metric,
                                    since true negatives are undefined/unbounded in free text]

We use multisets (Counter) rather than sets so that repeated PII values
(e.g. an email quoted twice) are each counted as a separate expected hit,
matching how they'd appear in the real redacted document.
"""

import sys
import os
import json
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.redactor import Redactor
from eval.test_data import TEST_DOCUMENT, GROUND_TRUTH


def normalize(text: str) -> str:
    return " ".join(text.strip().split())


def evaluate():
    redactor = Redactor()
    _, log = redactor.redact(TEST_DOCUMENT)

    predicted = Counter((entry["type"], normalize(entry["original"])) for entry in log)
    expected = Counter((label, normalize(value)) for label, value in GROUND_TRUTH)

    all_types = sorted(set([t for t, _ in predicted] + [t for t, _ in expected]))
    per_type = {}
    total_tp = total_fp = total_fn = 0

    for t in all_types:
        pred_t = Counter({k: v for k, v in predicted.items() if k[0] == t})
        exp_t = Counter({k: v for k, v in expected.items() if k[0] == t})

        tp = sum((pred_t & exp_t).values())
        fp = sum((pred_t - exp_t).values())
        fn = sum((exp_t - pred_t).values())

        precision = tp / (tp + fp) if (tp + fp) else (1.0 if fn == 0 else 0.0)
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        accuracy = tp / (tp + fp + fn) if (tp + fp + fn) else 1.0

        per_type[t] = {
            "true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "precision": round(precision, 3), "recall": round(recall, 3),
            "accuracy": round(accuracy, 3),
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    overall_accuracy = total_tp / (total_tp + total_fp + total_fn) if (total_tp + total_fp + total_fn) else 0.0

    report = {
        "per_type": per_type,
        "overall": {
            "true_positives": total_tp, "false_positives": total_fp, "false_negatives": total_fn,
            "precision": round(overall_precision, 3),
            "recall": round(overall_recall, 3),
            "accuracy": round(overall_accuracy, 3),
        },
        "false_positive_examples": [
            {"type": t, "value": v} for (t, v), c in predicted.items()
            if c > expected.get((t, v), 0)
        ][:20],
        "false_negative_examples": [
            {"type": t, "value": v} for (t, v), c in expected.items()
            if c > predicted.get((t, v), 0)
        ][:20],
    }
    return report


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, indent=2))
    with open(os.path.join(os.path.dirname(__file__), "evaluation_report.json"), "w") as f:
        json.dump(report, f, indent=2)
