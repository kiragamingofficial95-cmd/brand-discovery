"""Brand classification from cached homepage using keyword rules."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

NICHE_KEYWORDS: Dict[str, List[str]] = {
    "AI": ["artificial intelligence", "ai ", "machine learning", "llm", "generative", "chatbot", "gpt", "neural"],
    "SaaS": ["saas", "software as a service", "cloud software", "platform", "subscription", "dashboard", "workflow"],
    "tech": ["gadget", "smart home", "audio", "headphones", "phone", "camera", "pc parts", "electronics", "device"],
    "health and wellness": ["health", "wellness", "fitness", "sleep", "supplement", "nutrition", "skincare", "mental health", "meditation", "wearable"],
    "tourism": ["hotel", "resort", "tour", "cruise", "airline", "destination", "travel", "booking", "vacation", "tourism board"],
}

SUBNICHE_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "AI": {
        "video tools": ["video", "editing", "clip", "footage"],
        "coding assistants": ["code", "coding", "developer", "ide", "copilot"],
        "writing": ["writing", "copywriting", "essay", "text generation"],
        "note-taking": ["notes", "note-taking", "knowledge base", "second brain"],
        "voice": ["voice", "text to speech", "tts", "audio generation"],
        "image generation": ["image", "art", "picture", "diffusion", "midjourney"],
        "agents": ["agent", "automation", "assistant", "workflow agent"],
    },
    "SaaS": {
        "CRM": ["crm", "customer relationship", "sales pipeline", "leads"],
        "project management": ["project management", "tasks", "kanban", "sprint"],
        "email": ["email", "newsletter", "inbox", "mail"],
        "invoicing": ["invoice", "billing", "accounting", "payments"],
        "no-code": ["no-code", "low-code", "builder", "drag and drop"],
        "security and VPN": ["security", "vpn", "password", "privacy", "encryption"],
        "design": ["design", "figma", "ui", "ux", "prototype"],
        "HR": ["hr", "human resources", "payroll", "hiring", "recruiting"],
    },
    "tech": {
        "gadgets": ["gadget", "device", "tech accessory"],
        "smart home": ["smart home", "iot", "smart bulb", "thermostat"],
        "audio": ["audio", "headphones", "speakers", "earbuds", "sound"],
        "desk setups": ["desk", "monitor", "keyboard", "mouse", "stand"],
        "phones": ["phone", "smartphone", "mobile", "iphone", "android"],
        "cameras": ["camera", "lens", "photography", "dslr", "mirrorless"],
        "PC parts": ["pc parts", "gpu", "cpu", "motherboard", "ram", "ssd"],
    },
    "health and wellness": {
        "sleep": ["sleep", "mattress", "pillow", "insomnia"],
        "fitness gear": ["fitness", "gym", "workout", "equipment", "dumbbell"],
        "nutrition and supplements": ["nutrition", "supplement", "vitamin", "protein", "probiotic"],
        "meditation apps": ["meditation", "mindfulness", "calm", "breathing"],
        "skincare": ["skincare", "skin", "serum", "moisturizer", "beauty"],
        "mental health apps": ["mental health", "therapy", "counseling", "anxiety", "depression"],
        "wearables": ["wearable", "smartwatch", "fitness tracker", "ring"],
    },
    "tourism": {
        "hotels": ["hotel", "inn", "lodging", "accommodation"],
        "resorts": ["resort", "spa resort", "all-inclusive"],
        "tours": ["tour", "excursion", "guided", "experience"],
        "cruises": ["cruise", "cruising", "ship", "voyage"],
        "airlines": ["airline", "flight", "aviation", "airways"],
        "destinations and tourism boards": ["tourism board", "destination", "visit", "dmo", "tourism authority"],
        "travel gear": ["travel gear", "luggage", "backpack", "suitcase"],
        "booking platforms": ["booking", "reservation", "ota", "travel platform"],
    },
}

REJECT_KEYWORDS = [
    # marketing / PR / influencer / talent / MCN / UGC / platforms
    "influencer marketing", "influencer agency", "influencer platform", "creator marketplace", "ugc marketplace",
    "user generated content platform", "talent management", "talent agency", "mcn", "multi-channel network",
    "creator network", "social media agency", "growth hacking", "growth agency", "pr agency", "public relations",
    "media buying", "ad network", "affiliate network", "affiliate platform", "influencer discovery",
    "creator economy platform", "influencer software",
]

PLATFORM_REJECT = {"youtube.com", "youtu.be", "patreon.com", "spotify.com", "twitch.tv"}


def is_rejected(text: str, domain: str) -> Tuple[bool, str]:
    low = (text or "").lower()
    d = (domain or "").lower()
    if d in PLATFORM_REJECT or any(d.endswith("." + p) for p in PLATFORM_REJECT):
        return True, "platform"
    for kw in REJECT_KEYWORDS:
        if kw in low:
            return True, f"marketing_service:{kw}"
    # creator's own channel/merch heuristic
    if "merch" in low and "official store" in low:
        # not necessarily reject; only if domain is youtube-ish
        pass
    return False, ""


def classify(text: str, domain: str = "") -> Tuple[Optional[str], Optional[str], str]:
    """Return (niche, sub_niche, status). status in {accepted, needs_human_review, rejected}."""
    low = (text or "").lower()
    # reject first
    rej, reason = is_rejected(text, domain)
    if rej:
        return None, None, f"rejected:{reason}"
    # niche scoring
    niche_scores: Dict[str, int] = {}
    for niche, kws in NICHE_KEYWORDS.items():
        niche_scores[niche] = sum(1 for k in kws if k in low)
    best_niche = max(niche_scores, key=lambda n: niche_scores[n])
    if niche_scores[best_niche] == 0:
        return None, None, "needs_human_review"
    # sub-niche
    sub_scores = {}
    for sub, kws in SUBNICHE_KEYWORDS.get(best_niche, {}).items():
        sub_scores[sub] = sum(1 for k in kws if k in low)
    best_sub = None
    if sub_scores:
        best_sub = max(sub_scores, key=lambda s: sub_scores[s])
        if sub_scores[best_sub] == 0:
            best_sub = None
    if best_sub is None:
        # niche known but sub unclear -> still accepted with first sub? require at least weak; mark review
        pass
    return best_niche, best_sub, "accepted"
