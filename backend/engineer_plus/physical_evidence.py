"""Checks that a generated CalculiX deck contains a solvable structural model."""
from __future__ import annotations
from pathlib import Path
from typing import Any

REQUIRED_CARDS = {
    "material": ("*MATERIAL", "*ELASTIC"),
    "constraints": ("*BOUNDARY", "*EQUATION", "*COUPLING"),
    "loads": ("*CLOAD", "*DLOAD", "*DSLOAD", "*STEADY STATE DYNAMICS"),
}

def audit_calculix_deck(path: str | Path) -> dict[str, Any]:
    deck = Path(path).expanduser().resolve()
    if not deck.is_file():
        raise FileNotFoundError(deck)
    text = deck.read_text(encoding="utf-8", errors="replace").upper()
    present = {kind: any(card in text for card in cards) for kind, cards in REQUIRED_CARDS.items()}
    missing = [kind for kind, ok in present.items() if not ok]
    return {"path": str(deck), "solvable_structural_model": not missing,
            "present": present, "missing": missing, "bytes": deck.stat().st_size}

__all__ = ["audit_calculix_deck"]
