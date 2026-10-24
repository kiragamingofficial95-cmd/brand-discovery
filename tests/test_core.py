import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brand_discovery.config import Config
from brand_discovery.db import Database
from brand_discovery.quota import QuotaManager, QuotaExceeded
from brand_discovery.sponsorship import detect_signals, is_sponsored, has_ad_hashtag
from brand_discovery.classify import classify, is_rejected
from brand_discovery.evidence import brand_accepted, evidence_valid
from brand_discovery.brands import normalize_domain, saturation_threshold
from brand_discovery.scoring import score_brand
from brand_discovery.channels import uc_to_uu, in_size_band
from brand_discovery.links import root_domain, is_affiliate_link
from brand_discovery.blocklist import Blocklist


class TestSponsorship(unittest.TestCase):
    def test_paid_flag(self):
        sigs = detect_signals("hello", paid_flag=True)
        self.assertTrue(is_sponsored(sigs))

    def test_ad_hashtag(self):
        sigs = detect_signals("Check this #ad out")
        self.assertTrue(sigs["ad_hashtag"])
        self.assertTrue(is_sponsored(sigs))

    def test_phrase_multi_lang(self):
        for txt in ["gesponsert von Acme", "patrocinado por Acme", "sponsorisé par Acme"]:
            sigs = detect_signals(txt)
            self.assertTrue(sigs["phrase"], txt)

    def test_promo_code(self):
        sigs = detect_signals("use code SAVE20")
        self.assertTrue(sigs["promo_code"])

    def test_affiliate_link(self):
        sigs = detect_signals("https://example.com/?ref=yt")
        self.assertTrue(sigs["affiliate_link"])

    def test_non_sponsored(self):
        sigs = detect_signals("just a vlog")
        self.assertFalse(is_sponsored(sigs))


class TestClassify(unittest.TestCase):
    def test_ai(self):
        n, sub, st = classify("AI writing assistant tool", "")
        self.assertEqual(n, "AI")
        self.assertEqual(st, "accepted")

    def test_reject_agency(self):
        rej, reason = is_rejected("influencer marketing agency", "example.com")
        self.assertTrue(rej)

    def test_platform_reject(self):
        rej, reason = is_rejected("anything", "youtube.com")
        self.assertTrue(rej)

    def test_unclear(self):
        n, sub, st = classify("lorem ipsum dolor", "")
        self.assertEqual(st, "needs_human_review")


class TestEvidence(unittest.TestCase):
    def test_one_strong_accepts(self):
        ev = [{"url": "u", "date": "2026-10-01", "strength": "strong", "source_type": "youtube", "checked_in_run": True}]
        ok, reason = brand_accepted(ev, window_days=90)
        self.assertTrue(ok)

    def test_two_medium_accepts(self):
        ev = [
            {"url": "u1", "date": "2026-10-01", "strength": "medium", "source_type": "web", "checked_in_run": True},
            {"url": "u2", "date": "2026-09-15", "strength": "medium", "source_type": "youtube", "checked_in_run": True},
        ]
        ok, reason = brand_accepted(ev, window_days=90)
        self.assertTrue(ok)

    def test_weak_alone_rejects(self):
        ev = [{"url": "u", "date": "2026-10-01", "strength": "weak", "source_type": "web", "checked_in_run": True}]
        ok, _ = brand_accepted(ev, window_days=90)
        self.assertFalse(ok)

    def test_youtube_window(self):
        ev = [{"url": "u", "date": "2025-01-01", "strength": "strong", "source_type": "youtube", "checked_in_run": True}]
        ok, _ = brand_accepted(ev, window_days=90)
        self.assertFalse(ok)

    def test_undated_web_capped_medium(self):
        ev = [{"url": "u", "date": None, "strength": "strong", "source_type": "web", "checked_in_run": True}]
        ok, _ = brand_accepted(ev, window_days=90)
        # capped to medium -> single medium insufficient
        self.assertFalse(ok)


class TestQuota(unittest.TestCase):
    def test_hard_stop(self):
        d = tempfile.mkdtemp()
        db = Database(os.path.join(d, "t.sqlite"))
        cfg = Config.load(os.path.join(ROOT, "config.toml"))
        qm = QuotaManager(db, cfg, "youtube")
        # charge up to hard stop
        qm.charge("search", 8000)
        with self.assertRaises(QuotaExceeded):
            qm.charge("search", 100)

    def test_can_afford(self):
        d = tempfile.mkdtemp()
        db = Database(os.path.join(d, "t.sqlite"))
        cfg = Config.load(os.path.join(ROOT, "config.toml"))
        qm = QuotaManager(db, cfg, "youtube")
        self.assertTrue(qm.can_afford(100))
        qm.charge("search", 7900)
        self.assertFalse(qm.can_afford(200))


class TestBrands(unittest.TestCase):
    def test_normalize_domain(self):
        self.assertEqual(normalize_domain("https://www.Notion.so/x"), "notion.so")

    def test_uc_to_uu(self):
        self.assertEqual(uc_to_uu("UCabc"), "UUabc")

    def test_in_size_band(self):
        cfg = Config.load(os.path.join(ROOT, "config.toml"))
        self.assertTrue(in_size_band(50000, cfg))
        self.assertFalse(in_size_band(500, cfg))

    def test_blocklist(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "bl.txt")
        bl = Blocklist(p)
        bl.add("example.com")
        self.assertTrue(bl.contains("example.com"))
        self.assertFalse(bl.contains("other.com"))


class TestLinks(unittest.TestCase):
    def test_root_domain(self):
        self.assertEqual(root_domain("https://www.Foo.com/bar"), "foo.com")

    def test_affiliate_link(self):
        self.assertTrue(is_affiliate_link("https://x.com/?ref=yt"))
        self.assertFalse(is_affiliate_link("https://x.com/about"))


class TestScoring(unittest.TestCase):
    def test_score_range(self):
        cfg = Config.load(os.path.join(ROOT, "config.toml"))
        d = tempfile.mkdtemp()
        db = Database(os.path.join(d, "t.sqlite"))
        brand = {"domain": "x.com", "creators_90d": 3, "evidence": [{"date": "2026-10-20", "source_type": "youtube", "strength": "strong", "note": "promo code"}], "saturated": False, "momentum": 0.5}
        s = score_brand(brand, db, cfg, has_creator_angle=True)
        self.assertGreaterEqual(s, 0)
        self.assertLessEqual(s, 100)


class TestConfig(unittest.TestCase):
    def test_load(self):
        cfg = Config.load(os.path.join(ROOT, "config.toml"))
        self.assertIn("AI", cfg.niches)
        self.assertTrue(len(cfg.subniches["AI"]) >= 7)

    def test_starter_queries(self):
        cfg = Config.load(os.path.join(ROOT, "config.toml"))
        qs = cfg.starter_queries("writing")
        self.assertEqual(len(qs), 5)


if __name__ == "__main__":
    unittest.main()
