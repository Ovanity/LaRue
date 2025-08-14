from __future__ import annotations

def fmt_eur(cents: int) -> str:
    s = int(cents)
    euros = s // 100
    cents_part = abs(s) % 100
    sign = "-" if s < 0 else ""
    return f"{sign}{euros},{cents_part:02d}€"