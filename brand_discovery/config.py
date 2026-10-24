"""Configuration loading."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class Config:
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def app(self) -> Dict[str, Any]:
        return self.raw.get("app", {})

    @property
    def quotas(self) -> Dict[str, Any]:
        return self.raw.get("quotas", {})

    @property
    def thresholds(self) -> Dict[str, Any]:
        return self.raw.get("thresholds", {})

    @property
    def niches(self) -> List[str]:
        return self.raw.get("niches", {}).get("list", [])

    @property
    def subniches(self) -> Dict[str, List[str]]:
        return self.raw.get("subniches", {})

    @property
    def scoring(self) -> Dict[str, Any]:
        return self.raw.get("scoring", {})

    @property
    def web(self) -> Dict[str, Any]:
        return self.raw.get("web", {})

    @property
    def youtube(self) -> Dict[str, Any]:
        return self.raw.get("youtube", {})

    def get(self, *keys: str, default: Any = None) -> Any:
        cur: Any = self.raw
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return default
        return cur

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> "Config":
        p = Path(path)
        if not p.exists():
            # try relative to cwd then package
            for cand in (Path.cwd() / path, Path(__file__).parent.parent / path):
                if cand.exists():
                    p = cand
                    break
        with p.open("rb") as f:
            data = tomllib.load(f)
        return cls(raw=data)

    def starter_queries(self, sub_niche: str) -> List[str]:
        templates = [
            "{s} sponsored",
            "{s} paid promotion",
            "{s} #ad",
            "{s} use code",
            "{s} review partnership",
        ]
        return [t.format(s=sub_niche) for t in templates]
