"""Resolve shorteners and affiliate tracker domains to the real brand root domain."""
from __future__ import annotations

import urllib.parse
import urllib.request
from typing import Optional

TRACKER_HOSTS = {
    "shareasale.com", "www.shareasale.com",
    "awin.com", "www.awin.com", "awin1.com",
    "sjv.io", "pxf.io",
    "impact.com", "go.impact.com",
    "partnerstack.com",
    "tapfiliate.com",
    "firstpromoter.com",
    "rewardful.com",
    "refersion.com",
    "grin.co", "aspire.io", "ltk.com", "shopmy.us",
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "buff.ly",
    "lnkd.in", "amzn.to", "geni.us",
}

AFFILIATE_QUERY_KEYS = ("ref", "via", "utm_source", "partner", "aff", "affiliate")


def root_domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # strip port
    host = host.split(":")[0]
    return host


def resolve_url(url: str, max_hops: int = 10) -> str:
    """Follow redirects to final URL. Returns final URL string."""
    cur = url
    seen = set()
    for _ in range(max_hops):
        if cur in seen:
            break
        seen.add(cur)
        try:
            req = urllib.request.Request(cur, headers={"User-Agent": "BrandDiscoveryBot/1.0"}, method="HEAD")
            with urllib.request.urlopen(req, timeout=15) as resp:
                final = resp.geturl()
                if final == cur:
                    # maybe no redirect; try GET if HEAD not supported? keep
                    break
                cur = final
                continue
        except Exception:
            # fallback to GET
            try:
                req = urllib.request.Request(cur, headers={"User-Agent": "BrandDiscoveryBot/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    final = resp.geturl()
                    if final == cur:
                        break
                    cur = final
                    continue
            except Exception:
                break
    return cur


def extract_brand_domain(url: str) -> str:
    """Resolve and return root domain as brand ID."""
    final = resolve_url(url)
    return root_domain(final)


def is_affiliate_link(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(parsed.query)
    for k in AFFILIATE_QUERY_KEYS:
        if k in q:
            return True
    path = parsed.path.lower()
    if "/go/" in path:
        return True
    host = parsed.netloc.lower()
    if host in TRACKER_HOSTS:
        return True
    return False
