"""Local test: Al Jazeera headline — run: python _test_headline_cleanup.py"""
import json
from models.text_model import (
    _rewrite_with_transformer,
    _clean_headline_suggestion,
    check_and_rewrite_headline,
)

TITLE = "Maps: Israel has attacked six countries in the past 72 hours"
PARAS = """
On Tuesday, Israel launched a targeted air strike on a Hamas leadership compound in Qatar's capital, Doha, during a meeting to discuss a US-proposed ceasefire for Gaza.

The strike killed six people, including the son of senior Hamas leader Khalil al-Hayya. The attack was part of a wider wave of Israeli strikes extending beyond its immediate borders, and marked the sixth country attacked in just 72 hours.
""".strip()

# Simulate bad T5 output (two sentences jammed together)
bad = (
    "on tuesday, Israel launched a targeted air strike on a Hamas leadership compound in Qatar capital, doha. "
    "on tuesday, a meeting was held to discuss a US-proposed ceasefire for Gaza"
)
print("RAW T5-like:", bad)
print("CLEANED:  ", _clean_headline_suggestion(bad))
print("Has extra '. on' mid-string:", ". on" in _clean_headline_suggestion(bad).lower())
print()

print("LIVE T5:")
live = _rewrite_with_transformer(TITLE, PARAS)
print(" ", repr(live))
print(" Period count:", live.count('.') if live else 0)
print()

report = check_and_rewrite_headline(TITLE, PARAS)
print("FULL REPORT:")
print(json.dumps(report, indent=2))
