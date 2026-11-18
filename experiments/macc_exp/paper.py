"""Numbers reported in the paper (config/paper_reference.yaml)."""

from __future__ import annotations

from typing import Dict, Optional

import yaml

from .paths import PAPER_REFERENCE


def load(path=PAPER_REFERENCE) -> Dict[str, dict]:
    try:
        with open(path) as f:
            return (yaml.safe_load(f) or {}).get("references", {})
    except OSError:
        return {}


def lookup(ref: Dict[str, dict], paper_key: Optional[str], horizon: int) -> Optional[dict]:
    if not paper_key or paper_key not in ref:
        return None
    entry = ref[paper_key]
    return entry.get(horizon) or entry.get(str(horizon))
