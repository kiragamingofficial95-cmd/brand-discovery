"""Sponsorship detection signals (multi-language)."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

AD_HASHTAGS = {
    "#ad", "#ads", "#sponsored", "#sponsor", "#sponsoring",
    "#werbung", "#anzeige", "#gesponsert",
    "#patrocinado", "#publi", "#publicidad",
    "#pub", "#partenariat", "#sponsorise", "#sponsorisé",
    "#advertisement",
}

PHRASES = [
    # english
    "sponsored by", "brought to you by", "thanks to", "in partnership with",
    "partnered with", "paid promotion", "paid partnership",
    # german
    "gesponsert von", "präsentiert von", "in zusammenarbeit mit", "werbung",
    # spanish
    "patrocinado por", "gracias a", "en colaboración con",
    # portuguese
    "patrocinado por", "obrigado a", "em parceria com",
    # french
    "sponsorisé par", "sponsorise par", "en partenariat avec", "merci à",
]

PROMO_PATTERNS = [
    re.compile(r"(?:use|enter|apply|code|promo|rabattcode|código|code promo)\s*[:\-]?\s*([A-Za-z0-9_-]{3,20})", re.I),
    re.compile(r"(?:mit code|avec le code|con código|com código)\s+([A-Za-z0-9_-]{3,20})", re.I),
]

URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)


def has_ad_hashtag(text: str) -> bool:
    low = text.lower()
    return any(tag in low for tag in AD_HASHTAGS)


def has_phrase(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in PHRASES)


def has_promo_code(text: str) -> bool:
    for pat in PROMO_PATTERNS:
        if pat.search(text):
            return True
    # lines like "CODE: XYZ"
    if re.search(r"\bcode\b", text, re.I) and re.search(r"[A-Z0-9]{4,}", text):
        return True
    return False


def has_affiliate_link(text: str) -> bool:
    for url in URL_RE.findall(text):
        low = url.lower()
        if any(k in low for k in ("ref=", "via=", "utm_source=")):
            return True
        if "/go/" in low:
            return True
    # tracker domains
    for host in ("shareasale", "awin", "sjv.io", "pxf.io", "impact.com", "partnerstack", "tapfiliate", "firstpromoter", "rewardful", "refersion"):
        if host in text.lower():
            return True
    return False


def detect_signals(text: str, paid_flag: bool = False, pinned_comment: str = "") -> Dict[str, bool]:
    combined = text + "\n" + (pinned_comment or "")
    return {
        "paid_flag": bool(paid_flag),
        "ad_hashtag": has_ad_hashtag(combined),
        "phrase": has_phrase(combined),
        "promo_code": has_promo_code(combined),
        "affiliate_link": has_affiliate_link(combined),
    }


def is_sponsored(signals: Dict[str, bool]) -> bool:
    return any(signals.values())


def extract_urls(text: str) -> List[str]:
    return URL_RE.findall(text)


def extract_sponsor_candidates(text: str) -> List[Tuple[str, str]]:
    """Return list of (candidate, signal_type). Candidates may be names or urls."""
    cands: List[Tuple[str, str]] = []
    # urls
    for u in extract_urls(text):
        cands.append((u, "affiliate_link" if ("ref=" in u.lower() or "via=" in u.lower() or "/go/" in u.lower()) else "link"))
    low = text.lower()
    # phrase captures: "sponsored by BrandName"
    for phrase in ["sponsored by", "gesponsert von", "patrocinado por", "sponsorisé par", "sponsorise par", "brought to you by", "in partnership with", "en partenariat avec", "in zusammenarbeit mit", "en colaboración con", "em parceria com"]:
        for m in re.finditer(re.escape(phrase) + r"\s+([A-Z][A-Za-z0-9&.\- ]{1,40})", text, re.I):
            name = m.group(1).strip().rstrip(".,;:!?")
            if name and len(name) <= 40:
                cands.append((name, "phrase"))
    # "thanks to X" / "gracias a X" / "merci à X"
    for phrase in ["thanks to", "gracias a", "merci à", "merci a", "obrigado a"]:
        for m in re.finditer(re.escape(phrase) + r"\s+([A-Z][A-Za-z0-9&.\- ]{1,40})", text, re.I):
            name = m.group(1).strip().rstrip(".,;:!?")
            # stop at "for sponsoring"
            name = re.split(r"\bfor sponsoring\b", name, flags=re.I)[0].strip()
            if name and len(name) <= 40:
                cands.append((name, "phrase"))
    # promo codes
    for pat in PROMO_PATTERNS:
        for m in pat.finditer(text):
            cands.append((m.group(1), "promo_code"))
    return cands
