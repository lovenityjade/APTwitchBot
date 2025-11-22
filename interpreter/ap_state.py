"""
APTwitchInterpreter
Created by Jade (TheLovenityJade) - 2025

APState: wrapper around state.json produced by the C++ fetcher.
Handles reloads and new item detection.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List


class APState:
    """
    Petite couche utilitaire autour du state Archipelago.

    - Lit state.json (produit par le fetcher C++).
    - Peut aussi lire le log du fetcher pour du debug (optionnel).
    """

    def __init__(self, state_path: str | Path, fetcher_log_path: Optional[str | Path] = None) -> None:
        self.log = logging.getLogger("interpreter.state")

        self.state_path = Path(state_path)
        self.fetcher_log_path = Path(fetcher_log_path) if fetcher_log_path else None

    # ------------------------------------------------------------------ #
    # Lecture du state.json
    # ------------------------------------------------------------------ #

    def load_state(self) -> Dict[str, Any]:
        """Charge le state.json brut. Retourne {} si fichier manquant ou invalide."""
        try:
            with self.state_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            self.log.warning("state.json not found at %s", self.state_path)
            return {}
        except json.JSONDecodeError as e:
            self.log.error("Failed to parse state.json: %s", e)
            return {}

    # Helpers optionnels (peuvent servir plus tard au bot ou à un debug_view)

    def get_items(self) -> list[dict[str, Any]]:
        state = self.load_state()
        items = state.get("items") or []
        if isinstance(items, list):
            return items
        return []

    def get_checked_locations(self) -> list[int]:
        state = self.load_state()
        locs = state.get("checked_locations") or []
        # On force en int si possible
        result: List[int] = []
        for v in locs:
            try:
                result.append(int(v))
            except Exception:
                continue
        return result

    # ------------------------------------------------------------------ #
    # Lecture du log du fetcher (debug)
    # ------------------------------------------------------------------ #

    def load_fetcher_log(self, tail: int = 200) -> str:
        """
        Retourne les 'tail' dernières lignes du log du fetcher, sous forme de string.
        Si pas de log ou erreur, renvoie une string explicative.
        """
        if not self.fetcher_log_path:
            return "[no fetcher_log_path configured]"

        try:
            with self.fetcher_log_path.open("r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return f"[fetcher log not found at {self.fetcher_log_path}]"
        except Exception as e:
            return f"[error reading fetcher log: {e}]"

        if tail > 0 and len(lines) > tail:
            lines = lines[-tail:]

        return "".join(lines)
