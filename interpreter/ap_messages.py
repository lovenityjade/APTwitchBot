from __future__ import annotations

"""
APTwitchInterpreter
Created by Jade (TheLovenityJade) - 2025

Message loading and formatting from JSON.
"""

"""
Archipelago → Twitch Interpreter
ap_messages.py

Créé par TheLovenityJade (Jade Lovenity).
Projet open source : libre utilisation, modification et redistribution
sous réserve de conserver cet en-tête et les crédits.

Ce module gère le chargement et le formatage des messages
(type "messages.en.json") pour le bot Twitch.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


class MessageManager:
    """
    Charge les messages depuis un fichier JSON et fournit
    get() + format()/format_message() avec placeholders %nom.

    Deux façons de l'instancier sont supportées :

    - MessageManager(language="en")
      => utilisera <base_path>/config/messages.en.json

    - MessageManager(Path("/chemin/vers/messages.en.json"))
      => utilisera directement ce fichier (cas actuel de main.py)
    """

    def __init__(
        self,
        language_or_path: Union[str, Path] = "en",
        base_path: Optional[Path] = None,
        logger_: Optional[logging.Logger] = None,
    ) -> None:
        # Racine du projet ap-bridge (par défaut : 1 niveau au-dessus de /interpreter)
        if base_path is None:
            base_path = Path(__file__).resolve().parents[1]

        self.base_path: Path = Path(base_path)
        self.logger: logging.Logger = logger_ or logger

        # Si on reçoit un Path (ou une string qui ressemble à un chemin/.json),
        # on le traite comme un chemin explicite vers le fichier de messages.
        self._explicit_path: Optional[Path] = None

        if isinstance(language_or_path, Path):
            self._explicit_path = language_or_path
            self.language: str = "en"
        else:
            s = str(language_or_path)
            if s.endswith(".json") or "/" in s or "\\" in s:
                # Exemple: "config/messages.en.json"
                self._explicit_path = Path(s)
                self.language = "en"
            else:
                # Cas normal: "en", "fr", etc.
                self.language = s

        self._messages: Dict[str, str] = {}
        self._load_messages()

    # ---------- Chemins / chargement ----------

    @property
    def messages_path(self) -> Path:
        """Chemin complet du fichier de messages."""
        if self._explicit_path is not None:
            return self._explicit_path
        return self.base_dir / "config" / f"messages.{self.language}.json"

    @property
    def base_dir(self) -> Path:
        return self.base_path

    def _load_messages(self) -> None:
        path = self.messages_path
        try:
            if not path.exists():
                self.logger.error("Messages file not found: %s", path)
                self._messages = {}
                return

            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                self.logger.error(
                    "Messages file %s does not contain a JSON object at top level.",
                    path,
                )
                self._messages = {}
                return

            # On force tout en str par sécurité
            self._messages = {str(k): str(v) for k, v in data.items()}
            self.logger.info("Loaded %d messages from %s", len(self._messages), path)

        except json.JSONDecodeError as e:
            self.logger.exception("Failed to decode JSON messages from %s: %s", path, e)
            self._messages = {}
        except Exception as e:  # pragma: no cover (sécurité)
            self.logger.exception("Unexpected error while loading messages: %s", e)
            self._messages = {}

    def reload(self, language: Optional[str] = None) -> None:
        """Recharge le fichier de messages (optionnellement avec une nouvelle langue)."""
        if language is not None:
            # Si on change de langue, on invalide le chemin explicite.
            self._explicit_path = None
            self.language = language
        self._load_messages()

    # ---------- API publique ----------

    def get(self, key: str, default: Optional[str] = None) -> str:
        """
        Retourne le message brut (template) associé à la clé.
        Ne fait AUCUN remplacement.
        """
        if key in self._messages:
            return self._messages[key]

        # Pas de clé : on log et on renvoie le default si fourni,
        # sinon on renvoie la clé pour rendre le problème visible.
        if default is not None:
            return default
        self.logger.warning("Message key '%s' not found in messages JSON.", key)
        return key

    def format_message(self, key: str, **kwargs: Any) -> str:
        """
        Lit la template et remplace tous les placeholders %nom
        par les valeurs fournies en kwargs.

        Exemple :
            messages.format_message("progress", a=12, b=295, c="4.1", d=283)

        -> prend le texte "progress" dans le JSON,
           puis applique .replace("%a", "12"), etc.

        IMPORTANT :
        - Seuls les %nom présents dans kwargs sont remplacés.
        - Les autres %xxx restent tels quels.
        """
        if key not in self._messages:
            raise KeyError(key)

        template = self._messages[key]
        msg = str(template)

        for name, value in kwargs.items():
            placeholder = f"%{name}"
            msg = msg.replace(placeholder, str(value))

        return msg

    def format(self, key: str, **kwargs: Any) -> str:
        """
        Alias pour compatibilité avec InterpreterBot._fmt_msg(),
        qui appelle messages.format(key, **kwargs) si disponible.
        """
        return self.format_message(key, **kwargs)


# Instance globale éventuellement utilisable ailleurs
messages = MessageManager()


def get(key: str, default: Optional[str] = None) -> str:
    """Shortcut pour messages.get()."""
    return messages.get(key, default=default)


def format_message(key: str, **kwargs: Any) -> str:
    """Shortcut pour messages.format_message()."""
    return messages.format_message(key, **kwargs)
