"""Permanent blocklist of already-emailed brand domains."""
from __future__ import annotations

from pathlib import Path
from typing import Set


class Blocklist:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def load(self) -> Set[str]:
        domains = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#"):
                domains.add(line)
        return domains

    def contains(self, domain: str) -> bool:
        return domain.lower() in self.load()

    def add(self, domain: str) -> None:
        domains = self.load()
        d = domain.lower().strip()
        if d in domains:
            return
        with self.path.open("a", encoding="utf-8") as f:
            f.write(d + "\n")

    def filter_brands(self, domains: list[str]) -> list[str]:
        bl = self.load()
        return [d for d in domains if d.lower() not in bl]
