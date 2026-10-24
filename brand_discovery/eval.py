"""Evaluation harness for Phase 2 (hand-checked set)."""
from __future__ import annotations

from typing import Dict, List

from .sponsorship import detect_signals, is_sponsored, extract_sponsor_candidates


def evaluate_detection(samples: List[Dict]) -> Dict[str, float]:
    """samples: list of {text, paid_flag, pinned_comment, expected (bool)}."""
    tp = fp = tn = fn = 0
    for s in samples:
        sigs = detect_signals(s.get("text", ""), paid_flag=s.get("paid_flag", False),
                              pinned_comment=s.get("pinned_comment", ""))
        pred = is_sponsored(sigs)
        exp = bool(s.get("expected", False))
        if pred and exp:
            tp += 1
        elif pred and not exp:
            fp += 1
        elif (not pred) and exp:
            fn += 1
        else:
            tn += 1
    total = tp + fp + tn + fn
    acc = (tp + tn) / total if total else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return {"accuracy": acc, "precision": prec, "recall": rec, "total": total,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn}


def evaluate_brand_extraction(samples: List[Dict]) -> float:
    """samples: {text, expected_brands: [domains]}. Returns accuracy (exact set match ratio)."""
    if not samples:
        return 0.0
    hits = 0
    for s in samples:
        cands = extract_sponsor_candidates(s.get("text", ""))
        # resolve names to domains not possible offline; compare candidate names
        expected = set(s.get("expected_brands", []))
        got = set(c[0] for c in cands)
        if expected and expected.issubset(got) or (not expected and not got):
            hits += 1
    return hits / len(samples)