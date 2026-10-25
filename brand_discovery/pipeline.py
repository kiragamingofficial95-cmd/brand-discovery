"""Main pipeline orchestration."""
from __future__ import annotations

import json
import re
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

from .config import Config
from .db import Database
from .quota import QuotaManager
from .youtube import YouTubeClient
from .web_search import WebSearchClient
from .http import Fetcher
from .links import extract_brand_domain, is_affiliate_link
from .sponsorship import detect_signals, is_sponsored, extract_sponsor_candidates, extract_urls
from .classify import classify, is_rejected
from .evidence import brand_accepted, older_evidence_flag, normalize_strength
from .brands import is_new_brand, merge_evidence, distinct_creators_for_brand, is_saturated, re_report_allowed
from .scoring import score_brand
from .channels import uc_to_uu, in_size_band, rescan_interval_days
from .expansion import (seed_queries, least_recently_scanned, week_slices, update_query_yield,
                        make_replacement_queries, competitor_queries, max_depth_ok)
from .blocklist import Blocklist
from .reports import build_daily_report
from .youtube_page import fetch_watch_page


class Pipeline:
    def __init__(self, config: Config, db: Database, yt: YouTubeClient, web: WebSearchClient,
                 fetcher: Fetcher, blocklist: Blocklist, dry_run: bool = False):
        self.config = config
        self.db = db
        self.yt = yt
        self.web = web
        self.fetcher = fetcher
        self.blocklist = blocklist
        self.dry_run = dry_run
        self._search_count = 0

    def run(self) -> Dict[str, Any]:
        run_id = self.db.start_run()
        self.yt.quota.set_run(run_id)
        self.web.quota.set_run(run_id)
        notes = []
        brands_found = 0
        yt_units_start = self.yt.quota.used_today()
        web_start = self.web.quota.used_today()
        try:
            seed_queries(self.db, self.config)
            # 1. Channel pool rescans
            self._rescan_channels()
            # 2. YouTube expansion searches within budget (~4000 units)
            self._youtube_expansion()
            # 3. Web engine (~30% effort)
            self._web_engine()
            # 4. Aggregate brands, classify, score, accept
            target = int(self.config.app.get("daily_target", 15))
            warmup = bool(self.config.app.get("warmup", False))
            if warmup:
                target = int(self.config.app.get("warmup_target", 8))
            accepted = self._aggregate_and_accept()
            # shortfall handling: widen window, competitor expansion
            if len(accepted) < target:
                accepted = self._aggregate_and_accept(window_days=180)
            if len(accepted) < target:
                for b in list(accepted):
                    for cq in competitor_queries(b.get("name") or b["domain"]):
                        self.db.insert_query({"text": cq, "niche": b.get("niche", ""), "sub_niche": b.get("sub_niche", ""),
                                            "source": "youtube", "created_at": datetime.utcnow().isoformat(), "depth": 1})
            # mark final accepted brands as reported
            for b in accepted:
                b["last_reported"] = datetime.utcnow().isoformat()
                b["report_count"] = (b.get("report_count", 0) or 0) + 1
                self.db.upsert_brand(b)
            brands_found = len(accepted)
            # prune youtube raw data per API terms
            from .ops import prune_youtube_data
            prune_youtube_data(self.db, 30)
            # auto expansion flag
            dup_rate = (sum(1 for b in accepted if (b.get("report_count", 0) or 0) > 1) / len(accepted)) if accepted else 0.0
            if dup_rate > 0.8:
                self.db.kv_set("expansion_mode", "more")
            # 5. Report
            report = build_daily_report(self.config, self.db, accepted, self.yt.quota, self.web.quota)
            generated_at = report.get("generated_at")
            # 5b. Mirror accepted brands to MongoDB (dashboard read model) - best effort
            try:
                from .mongo import MongoWriter
                mw = MongoWriter()
                mw.upsert_run(run_id, generated_at, accepted, report,
                              self.yt.quota.used_today(), self.web.quota.used_today(), brands_found)
                mw.close()
            except Exception as e:
                print(f"[pipeline] mongo mirror skipped: {e}")
            self.db.finish_run(run_id, "success", self.yt.quota.used_today() - yt_units_start + yt_units_start,
                               self.web.quota.used_today() - web_start, brands_found, json.dumps(report)[:1000])
            return {"run_id": run_id, "brands_found": brands_found, "accepted": accepted, "report": report}
        except Exception as e:
            self.db.finish_run(run_id, "failed", self.yt.quota.used_today(), self.web.quota.used_today(), brands_found, str(e))
            raise

    # ---------- channel rescans ----------
    def _rescan_channels(self):
        now_iso = datetime.utcnow().isoformat()
        due = self.db.channels_due_for_rescan(now_iso)
        for ch in due:
            try:
                self._scan_channel(ch)
            except Exception:
                continue

    def _scan_channel(self, ch: Dict[str, Any]):
        playlist = ch.get("uploads_playlist") or uc_to_uu(ch["channel_id"])
        # fetch recent uploads
        items = []
        try:
            data = self.yt.playlist_items_list(playlist, max_results=25)
            items = self.yt.parse_video_items(data) if False else data.get("items", [])
        except Exception:
            return
        video_ids = []
        for it in items:
            sn = it.get("snippet") or {}
            vid = (it.get("contentDetails") or {}).get("videoId") or (sn.get("resourceId") or {}).get("videoId")
            if vid:
                video_ids.append(vid)
        if not video_ids:
            return
        # fetch details in batches of 50
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            try:
                data = self.yt.videos_list(batch, part="snippet,paidProductPlacementDetails")
            except Exception:
                continue
            for v in data.get("items", []):
                self._process_video(v, ch)
        # update last_scanned
        ch["last_scanned"] = datetime.utcnow().isoformat()
        self.db.upsert_channel(ch)

    def _process_video(self, v: Dict[str, Any], ch: Dict[str, Any]):
        vid = v.get("id")
        sn = v.get("snippet") or {}
        pppd = v.get("paidProductPlacementDetails") or {}
        paid_flag = bool(pppd) or bool(v.get("paidProductPlacement"))
        # Actually paidProductPlacementDetails presence indicates paid placement
        if "paidProductPlacementDetails" in v and v["paidProductPlacementDetails"] is not None:
            paid_flag = True
        description = sn.get("description", "") or ""
        title = sn.get("title", "") or ""
        tags = sn.get("tags", []) or []
        published = sn.get("publishedAt")
        # Fallback enrichment from the public watch page when the scraper returns nulls.
        if (not description.strip()) or (not published):
            try:
                meta = fetch_watch_page(vid, self.fetcher)
                description = description or meta.get("description", "")
                published = published or meta.get("published_at")
                title = title or meta.get("title", "")
            except Exception:
                pass
        # pinned comment if description empty
        pinned = ""
        if not description.strip():
            try:
                cd = self.yt.comment_threads_list(vid, max_results=3)
                for c in cd.get("items", []):
                    top = ((c.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {}
                    if top.get("textDisplay"):
                        pinned = top.get("textDisplay", "")
                        break
            except Exception:
                pass
        text = title + "\n" + description
        signals = detect_signals(text, paid_flag=paid_flag, pinned_comment=pinned)
        sponsored = is_sponsored(signals)
        candidates = extract_sponsor_candidates(text + "\n" + pinned) if sponsored else []
        sponsor_brands = []
        # resolve urls to domains
        for cand, sig in candidates:
            if cand.startswith("http"):
                try:
                    dom = extract_brand_domain(cand)
                    sponsor_brands.append(dom)
                except Exception:
                    pass
            else:
                # name only; store as candidate domain placeholder (lowercased name) for later resolution
                sponsor_brands.append(cand)
        # filter affiliate links in description
        for u in extract_urls(description + " " + pinned):
            if is_affiliate_link(u):
                try:
                    sponsor_brands.append(extract_brand_domain(u))
                except Exception:
                    pass
        # dedup
        sponsor_brands = list(dict.fromkeys(sponsor_brands))
        video_rec = {
            "video_id": vid,
            "channel_id": ch["channel_id"],
            "title": title,
            "description": description,
            "published_at": published,
            "paid_product_placement": paid_flag,
            "tags": tags,
            "sponsor_detected": sponsored,
            "sponsor_brands": sponsor_brands,
            "pinned_comment": pinned,
        }
        self.db.upsert_video(video_rec)
        # store brand evidence for sponsored
        if sponsored:
            scraper_mode = not self.yt.quota.enforce
            for dom in sponsor_brands:
                if not isinstance(dom, str):
                    continue
                dom = dom.strip()
                if not dom:
                    continue
                # accept valid domains, or phrase names in scraper mode
                if ("." in dom and " " not in dom) or scraper_mode:
                    # normalize phrase names: lowercase, no spaces, add .brand suffix
                    if "." not in dom or " " in dom:
                        dom = re.sub(r"[^a-z0-9]+", "", dom.lower()) + ".brand"
                    self._record_youtube_evidence(dom, ch, vid, published, paid_flag, signals, tags)

    def _record_youtube_evidence(self, domain: str, ch, vid, published, paid_flag, signals, tags):
        domain = domain.lower()
        if self.blocklist.contains(domain):
            return
        ev = {
            "url": f"https://www.youtube.com/watch?v={vid}",
            "date": (published or "")[:10] or None,
            "strength": "strong" if (paid_flag or signals.get("promo_code") or signals.get("affiliate_link")) else "medium",
            "source_type": "youtube",
            "note": "paid promotion flag" if paid_flag else "sponsorship signal",
            "checked_in_run": True,
        }
        # upsert brand shell
        b = self.db.get_brand(domain) or {"domain": domain, "name": domain, "first_seen": datetime.utcnow().isoformat(),
                                          "evidence": [], "sponsor_count": 0, "creators_90d": 0}
        if not b.get("niche") and ch.get("niche") in self.config.niches:
            b["niche"] = ch.get("niche")
            b["sub_niche"] = ch.get("sub_niche", "")
        b["evidence"] = merge_evidence(b.get("evidence", []), [ev])
        b["sponsor_count"] = b.get("sponsor_count", 0) + 1
        # creators_90d computed later; approximate
        self.db.upsert_brand(b)
        self.db.add_evidence(domain, ev)

    # ---------- youtube expansion ----------
    def _youtube_expansion(self):
        budget = int(self.config.quotas.get("youtube_search_budget", 4000))
        max_searches = int(self.config.quotas.get("max_youtube_searches_per_run", 40))
        max_queries = int(self.config.quotas.get("max_queries_per_run", 15))
        used0 = self.yt.quota.used_today()
        qs = least_recently_scanned(self.db, "youtube", limit=200)
        qs = [q for q in qs if not q.get("retired")][:max_queries]
        for q in qs:
            if self._search_count >= max_searches:
                break
            if self.yt.quota.enforce and (self.yt.quota.used_today() - used0) >= budget:
                break
            if not max_depth_ok(q.get("depth", 0), self.config):
                continue
            if not self._relevant(q.get("text", "")):
                self.db.update_query(q["id"], retired=True)
                continue
            self._run_youtube_query(q, max_searches)
        # make replacements from sponsored videos
        sponsored_videos = [v for v in self.db.list_videos() if v.get("sponsor_detected")]
        make_replacement_queries(self.db, self.config, sponsored_videos)

    def _relevant(self, text: str) -> bool:
        low = text.lower()
        all_terms = []
        for n in self.config.niches:
            all_terms.append(n.lower())
        for subs in self.config.subniches.values():
            for s in subs:
                all_terms.append(s.lower())
        all_terms += ["sponsored", "ad", "promo", "review", "partnership"]
        return any(t in low for t in all_terms)

    def _run_youtube_query(self, q: Dict[str, Any], max_searches: int = 40):
        scraper = not getattr(self.yt.quota, "enforce", True)
        slices = week_slices(days_back=90, slice_days=7)
        variants = [
            {"order": "relevance", "regionCode": "", "relevanceLanguage": "", "videoDuration": ""},
            {"order": "date", "regionCode": "US", "relevanceLanguage": "en", "videoDuration": ""},
            {"order": "viewCount", "regionCode": "GB", "relevanceLanguage": "en", "videoDuration": "medium"},
        ]
        if scraper:
            # scraper ignores publishedAfter/Before and is slower; keep it light
            slices = slices[:2]
            variants = variants[:1]
        before_brands = {b["domain"] for b in self.db.list_brands()}
        units_before = self.yt.quota.used_today()
        for sl in slices:
            for var in variants:
                if self._search_count >= max_searches:
                    break
                if self.yt.quota.enforce and self.yt.quota.used_today() >= int(self.config.quotas.get("youtube_hard_stop", 8000)):
                    break
                self._search_count += 1
                try:
                    data = self.yt.search(
                        q["text"],
                        order=var["order"] or None,
                        regionCode=var["regionCode"] or None,
                        relevanceLanguage=var["relevanceLanguage"] or None,
                        videoDuration=var["videoDuration"] or None,
                        publishedAfter=sl[0],
                        publishedBefore=sl[1],
                        max_results=5 if scraper else 25,
                    )
                except Exception:
                    continue
                items = self.yt.parse_search_items(data)
                vids = [it.get("id", {}).get("videoId") for it in items if it.get("id", {}).get("videoId")]
                if scraper:
                    vids = vids[:5]
                if not vids:
                    continue
                try:
                    vdata = self.yt.videos_list(vids, part="snippet,paidProductPlacementDetails")
                    vitems = vdata.get("items", [])
                except Exception:
                    vitems = []
                if not vitems:
                    vitems = [{"id": it["id"]["videoId"], "snippet": it.get("snippet") or {}} for it in items if it.get("id", {}).get("videoId")]
                for v in vitems:
                    ch_id = (v.get("snippet") or {}).get("channelId")
                    if not scraper:
                        self._ensure_channel(ch_id, q.get("niche", ""))
                    ch = self.db.get_channel(ch_id) or {"channel_id": ch_id, "niche": q.get("niche", ""), "sub_niche": q.get("sub_niche", ""),
                                                        "title": (v.get("snippet") or {}).get("channelTitle", "")}
                    self._process_video(v, ch)
        after_brands = {b["domain"] for b in self.db.list_brands()}
        new_brands_this = len(after_brands - before_brands)
        units_used = self.yt.quota.used_today() - units_before
        update_query_yield(self.db, q["id"], new_brands_this, max(units_used, 1))

    def _ensure_channel(self, channel_id: str, niche: str):
        if not channel_id:
            return
        if self.db.get_channel(channel_id):
            return
        try:
            data = self.yt.channels_list([channel_id], part="snippet,statistics,contentDetails")
        except Exception:
            return
        for c in data.get("items", []):
            sn = c.get("snippet") or {}
            stats = c.get("statistics") or {}
            subs = int(stats.get("subscriberCount", 0) or 0)
            if not in_size_band(subs, self.config):
                return
            uploads = uc_to_uu(channel_id)
            cd = c.get("contentDetails") or {}
            if (cd.get("relatedPlaylists") or {}).get("uploads"):
                uploads = cd["relatedPlaylists"]["uploads"]
            ch = {
                "channel_id": channel_id,
                "title": sn.get("title", ""),
                "niche": niche,
                "sub_niche": "",
                "uploads_playlist": uploads,
                "subscriber_count": subs,
                "video_count": int(stats.get("videoCount", 0) or 0),
                "last_scanned": None,
                "scan_interval_days": 5,
                "featured_channels": [],
            }
            self.db.upsert_channel(ch)

    # ---------- web engine ----------
    def _web_engine(self):
        # 30% of daily effort: run web searches for creator/affiliate programs etc.
        # Build queries from sub-niches
        queries = []
        for niche in self.config.niches:
            for sub in self.config.subniches.get(niche, []):
                queries.append((niche, sub, f"{sub} creator program"))
                queries.append((niche, sub, f"{sub} affiliate program"))
        # limit pages per run
        page_budget = int(self.config.quotas.get("web_pages_per_run", 150))
        pages = 0
        for niche, sub, q in queries:
            if pages >= page_budget:
                break
            if self.web.quota.used_today() >= int(self.config.quotas.get("web_search_daily_limit", 100)):
                break
            try:
                results = self.web.search(q, num_results=10)
            except Exception:
                continue
            for r in results:
                if pages >= page_budget:
                    break
                url = r.get("link", "")
                if not url:
                    continue
                # check affiliate/creator program paths
                text, status, err = self.fetcher.fetch(url)
                if err or not text:
                    continue
                pages += 1
                self._process_web_page(text, url, niche, sub)

    def _process_web_page(self, text: str, url: str, niche: str, sub: str):
        low = text.lower()
        # detect tracking scripts
        tracking_scripts = ["impact", "refersion", "partnerstack", "tapfiliate", "firstpromoter", "rewardful", "grin", "aspire", "ltk", "shopmy"]
        has_tracking = any(t in low for t in tracking_scripts)
        # detect creator/affiliate program
        program_paths = ["/affiliates", "/creators", "/ambassadors", "/partners", "/influencers", "/collab"]
        has_program = any(p in url.lower() or p in low for p in program_paths) or "affiliate program" in low or "creator program" in low
        if not (has_tracking or has_program):
            return
        # brand domain from url
        try:
            domain = extract_brand_domain(url)
        except Exception:
            return
        if self.blocklist.contains(domain):
            return
        # classify
        n, sn, status = classify(text, domain)
        if status.startswith("rejected") or n is None:
            if status.startswith("rejected"):
                # save rejection? denylist handled separately
                pass
            if n is None and status != "needs_human_review":
                return
        if n is None:
            n = niche
        if sn is None:
            sn = sub
        # evidence strength: strong if tracking script + program page live checked
        strength = "strong" if (has_tracking and has_program) else "medium"
        # ensure page live & checked this run -> medium at most for undated; but we have url+date? no date -> undated
        ev = {
            "url": url,
            "date": None,
            "strength": strength,
            "source_type": "web",
            "note": "creator/affiliate program page" + (" with tracking script" if has_tracking else ""),
            "checked_in_run": True,
        }
        # dated? none -> medium at most (already strong downgraded? normalize later). For undated web, strong not allowed; cap to medium.
        if ev["date"] is None:
            ev["strength"] = "medium" if ev["strength"] == "strong" else ev["strength"]
            # but spec: strong allowed for live creator/affiliate program page with tracking script even if undated? 
            # Spec: "Strong evidence is ... a live creator or affiliate program page with a tracking script."
            # and "Undated web evidence counts as medium at most". Conflict. We'll cap undated to medium per explicit rule.
        b = self.db.get_brand(domain) or {"domain": domain, "name": domain, "first_seen": datetime.utcnow().isoformat(),
                                          "evidence": [], "sponsor_count": 0, "creators_90d": 0}
        if n:
            b["niche"] = n
        if sn:
            b["sub_niche"] = sn
        b["website"] = b.get("website") or ("https://" + domain)
        b["evidence"] = merge_evidence(b.get("evidence", []), [ev])
        self.db.upsert_brand(b)
        self.db.add_evidence(domain, ev)

    # ---------- aggregate & accept ----------
    def _classify_domain(self, domain: str, fallback_niche: Optional[str] = None):
        try:
            html, status, err = self.fetcher.fetch("https://" + domain)
        except Exception:
            html = None
        if html:
            n, sn, st = classify(html, domain)
            if st.startswith("rejected"):
                return None, None, "rejected"
            if n:
                return n, sn, "accepted"
            return None, None, "needs_human_review"
        if fallback_niche:
            return fallback_niche, "", "accepted"
        return None, None, "needs_human_review"

    def _aggregate_and_accept(self, window_days: Optional[int] = None) -> List[Dict[str, Any]]:
        today = date.today()
        if window_days is None:
            window_days = int(self.config.thresholds.get("sponsorship_window_days", 90))
        # shortfall mode? check if below target; handled outside. Default 90.
        # If duplicate rate high, etc. (auto expansion flags) - set kv
        accepted_list = []
        re_reported = 0
        total_candidates = 0
        for b in self.db.list_brands():
            domain = b["domain"]
            if self.blocklist.contains(domain):
                continue
            # only real root domains are valid brand IDs
            if "." not in domain or " " in domain:
                continue
            # classify from stored? need homepage text; we may not have. Use evidence notes/domain.
            # Determine niche
            niche = b.get("niche")
            sub = b.get("sub_niche")
            if not niche:
                n, sn, st = self._classify_domain(domain, b.get("niche"))
                if st == "rejected":
                    continue
                niche = n or niche
                sub = sn or sub
            if niche not in self.config.niches:
                continue
            # re-report rule
            new_creators = distinct_creators_for_brand(self.db, domain)
            b["creators_90d"] = new_creators
            # saturated
            b["saturated"] = is_saturated(self.db, domain)
            # acceptance
            evs = b.get("evidence", [])
            # youtube window
            ok, reason = brand_accepted(evs, today=today, window_days=window_days,
                                    scraper_mode=not self.yt.quota.enforce)
            if not ok:
                continue
            # dated evidence age check already in brand_accepted/evidence_valid
            # score
            has_creator_angle = any("creator" in (e.get("note", "").lower()) or "affiliate" in (e.get("note", "").lower()) or "tracking" in (e.get("note", "").lower()) for e in evs)
            b["score"] = score_brand(b, self.db, self.config, has_creator_angle=has_creator_angle, today=today,
                                    scraper_mode=not self.yt.quota.enforce)
            min_score = self.config.thresholds.get("scraper_min_score", 30) if not self.yt.quota.enforce else self.config.thresholds.get("min_score", 60)
            if b["score"] < int(min_score):
                continue
            # older evidence flag
            oe = older_evidence_flag(evs, window_days, today=today)
            b["older_evidence"] = oe
            # re-report check
            if b.get("last_reported"):
                allowed = re_report_allowed(self.db, domain, new_creators, datetime.utcnow().isoformat())
                if not allowed:
                    continue
                re_reported += 1
            # cap re-reported <= 30%
            total_candidates += 1
            # store
            b["niche"] = niche
            b["sub_niche"] = sub or ""
            b["name"] = b.get("name") or domain
            b["website"] = b.get("website") or ("https://" + domain)
            self.db.upsert_brand(b)
            accepted_list.append(b)

        # enforce re-reported <= 30%: if exceeded, drop excess re-reported (keep new)
        # simple: sort new first
        new_brands = [b for b in accepted_list if not self.db.get_brand(b["domain"]).get("last_reported")]
        # Actually last_reported may have been set; track via report_count
        # We'll just cap by removing re-reported beyond 30%
        max_re = int(len(accepted_list) * float(self.config.thresholds.get("max_re_report_share", 0.30)))
        # identify re-reported
        rer = [b for b in accepted_list if (self.db.get_brand(b["domain"]) or {}).get("report_count", 0) > 0]
        if len(rer) > max_re and max_re >= 0:
            # remove excess re-reported from end
            excess = len(rer) - max_re
            # remove from accepted_list
            removed = 0
            i = len(accepted_list) - 1
            while removed < excess and i >= 0:
                if accepted_list[i]["domain"] in {b["domain"] for b in rer}:
                    accepted_list.pop(i)
                    removed += 1
                i -= 1

        return accepted_list
