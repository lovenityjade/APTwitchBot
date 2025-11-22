"""
APTwitchInterpreter main entry point.

Created by Jade (TheLovenityJade) - 2025
Open source, free to modify and redistribute under your chosen license.
"""

import json
import logging
from pathlib import Path

from .ap_state import APState
from .ap_messages import MessageManager
from .bot import InterpreterBot


# Base du projet : .../ap-bridge
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"


def load_config() -> dict:
    """Charge config/config.json."""
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def setup_logging(config: dict) -> None:
    """Configure le logging de base de l'interpreter."""
    log_cfg = config.get("logging", {})
    level_name = log_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_file = log_cfg.get("file", str(BASE_DIR / "interpreter.log"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ],
    )


def main() -> None:
    # 1) Config
    config = load_config()
    setup_logging(config)

    logger = logging.getLogger("interpreter.main")
    logger.info("Starting Archipelago Twitch interpreter")

    # 2) Paths state.json + fetcher.log
    state_path = Path(config["paths"]["state_file"])
    fetcher_log_path = Path(config["paths"]["fetcher_log"])

    # 3) Messages (langue)
    bot_settings = config.get("bot_settings", {})
    language = bot_settings.get("language", "en")
    messages_path = BASE_DIR / "config" / f"messages.{language}.json"

    logger.info("Using messages file: %s", messages_path)

    messages = MessageManager(messages_path)
    ap_state = APState(state_path)

    # 4) Bot Twitch
    bot = InterpreterBot(config=config, messages=messages, ap_state=ap_state)

    logger.info("Connecting bot to Twitch...")
    bot.run()


if __name__ == "__main__":
    main()