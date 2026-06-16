"""
Loads the product catalog extracted from Cash Now's price sheet
(data/products.json) and formats it for use inside Claude's system prompt.

The catalog is intentionally simple - just product name, category, and
whether Cash Now is currently buying that item. Exact pricing depends on
condition (mint/dinged/damaged) and months-to-expiration, which is too
detailed for a phone conversation; pricing is always confirmed by a human
when the draft order is reviewed. The bot's job is only to:

  1. Recognize broad categories of items Cash Now buys (so it can keep the
     caller on-topic).
  2. Flag items that are currently NOT being purchased, so the bot can set
     expectations up front.
  3. Capture the caller's own description of each item + expiration date.
"""

import json
import os
from collections import defaultdict

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "products.json")

with open(_DATA_PATH, "r") as f:
    PRODUCTS = json.load(f)


def categories() -> list[str]:
    seen = []
    for p in PRODUCTS:
        if p["category"] not in seen:
            seen.append(p["category"])
    return seen


def catalog_summary_for_prompt(max_items_per_category: int = 12) -> str:
    """
    Compact, human-readable summary grouped by category, e.g.:

      Test Strips (buying): Accuchek Aviva 100 Count, Accuchek Aviva 50
        Count, ... (+40 more)
      Lancets (mostly not buying right now): ...

    This keeps token usage reasonable while giving Claude enough context to
    recognize whether an item is in-scope and whether it's currently wanted.
    """
    by_cat = defaultdict(lambda: {"buying": [], "not_buying": []})
    for p in PRODUCTS:
        bucket = "buying" if p["currently_buying"] else "not_buying"
        by_cat[p["category"]][bucket].append(p["name"].title())

    lines = []
    for cat in categories():
        info = by_cat[cat]
        buying = info["buying"]
        not_buying = info["not_buying"]
        if buying:
            shown = buying[:max_items_per_category]
            extra = len(buying) - len(shown)
            extra_note = f" (+{extra} more)" if extra > 0 else ""
            lines.append(f"- {cat} - CURRENTLY BUYING: {', '.join(shown)}{extra_note}")
        if not_buying:
            shown = not_buying[:max_items_per_category]
            extra = len(not_buying) - len(shown)
            extra_note = f" (+{extra} more)" if extra > 0 else ""
            lines.append(f"- {cat} - NOT BUYING RIGHT NOW: {', '.join(shown)}{extra_note}")
    return "\n".join(lines)


def is_known_category(text: str) -> bool:
    text = text.lower()
    return any(cat.lower() in text for cat in categories())
