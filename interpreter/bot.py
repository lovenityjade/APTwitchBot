from __future__ import annotations

import asyncio
import json
import logging
import aiohttp
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from twitchio.ext import commands


MAX_TWITCH_MESSAGE_LENGTH = 450


class InterpreterBot(commands.Bot):
    """
    Archipelago -> Twitch interpreter bot.

    This bot reads a JSON state file produced by the C++ fetcher and exposes
    useful information to Twitch chat via commands and automatic messages.
    """

    def __init__(self, config: Dict[str, Any], ap_state: Any = None, messages: Any = None) -> None:
        self._item_cache: dict[str, dict[str, str]] = {}
        # Store external helpers (even if we don't use them yet)
        self.config: Dict[str, Any] = config
        self.ap_state = ap_state
        self.messages = messages

        self.log = logging.getLogger("ap_interpreter")

        # Base directory of the project (ap-bridge root)
        self.base_dir = Path(__file__).resolve().parents[1]

        # Paths config
        paths_cfg = config.get("paths", {})
        state_path_cfg = paths_cfg.get("state_file", "state.json")
        log_path_cfg = paths_cfg.get("fetcher_log", "ap_fetcher.log")

        self.state_path = Path(state_path_cfg)
        if not self.state_path.is_absolute():
            self.state_path = self.base_dir / self.state_path

        self.fetcher_log_path = Path(log_path_cfg)
        if not self.fetcher_log_path.is_absolute():
            self.fetcher_log_path = self.base_dir / self.fetcher_log_path

        # Twitch / bot config
        twitch_cfg = config.get("twitch", {})
        bot_cfg = config.get("bot_settings", {})

        token = (
            twitch_cfg.get("token")
            or twitch_cfg.get("oauth_token")
            or twitch_cfg.get("access_token")
        )
        if not token:
            raise RuntimeError("Twitch OAuth token not found in config['twitch'].")

        self.channel_name: str = twitch_cfg.get("channel") or twitch_cfg.get("nickname") or ""
        if not self.channel_name:
            raise RuntimeError("Channel name not found in config['twitch']['channel'].")

        prefix = bot_cfg.get("prefix", "!")
        initial_channels = [self.channel_name]

        # Tracking / timers
        self._about_interval_minutes: int = int(bot_cfg.get("about_interval_minutes", 15))
        self._auto_announce_items: bool = bool(bot_cfg.get("auto_announce_items", True))

        self._about_task: Optional[asyncio.Task] = None
        self._watch_items_task: Optional[asyncio.Task] = None

        initial_state = self._load_state()
        initial_items = initial_state.get("items") or []
        self._last_item_count: int = len(initial_items)

        # Admin / permissions
        self.admin_users = set(u.lower() for u in bot_cfg.get("admin_users", []))
        # broadcaster will be considered admin implicitly

        super().__init__(token=token, prefix=prefix, initial_channels=initial_channels)

    # ------------------------------------------------------------------ #
    # Utility helpers
    # ------------------------------------------------------------------ #

    def _load_state(self) -> Dict[str, Any]:
        try:
            with self.state_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            self.log.warning("state.json not found at %s", self.state_path)
            return {}
        except json.JSONDecodeError as e:
            self.log.error("Failed to parse state.json: %s", e)
            return {}

    def _get_progress(self, state: Dict[str, Any]) -> Dict[str, Any]:
        checked_locations = state.get("checked_locations") or []
        checks_done = len(checked_locations)

        # Try to obtain total locations from multiple possible places
        total_locations = (
            state.get("room", {}).get("location_count")
            or state.get("room", {}).get("locations_total")
            or state.get("archipelago", {}).get("location_count")
            or self.config.get("archipelago", {}).get("location_count")
            or self.config.get("bot_settings", {}).get("total_locations")
            or 0
        )

        remaining = max(total_locations - checks_done, 0) if total_locations else 0
        percent = (checks_done / total_locations * 100.0) if total_locations else 0.0

        return {
            "checks_done": checks_done,
            "total_locations": total_locations,
            "remaining": remaining,
            "percent": percent,
        }

    def _get_last_items(self, state: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = state.get("items") or []
        if not items:
            return []
        return items[-limit:]
    
    def _normalize_item_slug(self, item_name: str) -> str:
        """
        Convertit un nom d'item Archipelago (ex: 'Dive Ball', 'Red Flute')
        en slug PokéAPI (ex: 'dive-ball', 'red-flute').

        C'est du best-effort : on pourra ajouter des cas spéciaux au besoin.
        """
        if not item_name:
            return ""

        s = item_name.strip().lower()

        # Remplacements de base
        s = s.replace("é", "e").replace("è", "e").replace("ê", "e")
        s = s.replace("'", "").replace(".", "")

        # Espaces -> tirets
        s = re.sub(r"\s+", "-", s)

        # Quelques cas spéciaux / corrections si besoin
        special = {
            # Si Archipelago utilisait des noms un peu différents
            # "hp up": "hp-up",
            # "x atk": "x-attack",
        }
        if s in special:
            return special[s]

        return s

    async def _fetch_item_info(self, item_name: str) -> dict[str, str] | None:
        """
        Va chercher les infos d'un item sur PokéAPI.
        Retourne un dict avec name, short_effect, flavor_text.
        """
        slug = self._normalize_item_slug(item_name)
        if not slug:
            return None

        # Cache in-memory
        if slug in self._item_cache:
            return self._item_cache[slug]

        url = f"https://pokeapi.co/api/v2/item/{slug}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        self.log.warning("PokéAPI returned %s for %s", resp.status, url)
                        return None
                    data = await resp.json()
        except Exception as e:
            self.log.warning("Error fetching PokéAPI item %r: %s", slug, e)
            return None

        # Nom officiel (anglais)
        name = data.get("name", item_name)

        # Effet court (texte d'effet, ex: 'Raises HP...')
        short_effect = ""
        for entry in data.get("effect_entries", []):
            lang = entry.get("language", {}).get("name")
            if lang == "en":
                short_effect = entry.get("short_effect") or entry.get("effect") or ""
                break

        # Flavor text (description style Pokédex)
        flavor_text = ""
        for entry in data.get("flavor_text_entries", []):
            lang = entry.get("language", {}).get("name")
            if lang == "en":
                flavor_text = entry.get("text") or ""
                break

        info = {
            "name": name,
            "short_effect": short_effect.replace("\n", " ").strip(),
            "flavor_text": flavor_text.replace("\n", " ").strip(),
        }

        self._item_cache[slug] = info
        return info


    def _is_key_item(self, item: Dict[str, Any], state: Dict[str, Any]) -> bool:
        """
        Best-effort detection of "key items" using the Archipelago data package if present.
        """
        dp = state.get("data_package") or {}
        items_db = dp.get("items") or {}
        item_id = item.get("item_id")
        if item_id is None:
            return False

        info = items_db.get(str(item_id)) or items_db.get(item_id)
        if not isinstance(info, dict):
            return False

        # Archipelago item classification is usually a list under "classification"
        classification = info.get("classification") or info.get("categories") or []
        classification = [str(c).lower() for c in classification]

        # Heuristic: treat "progression" or "trap" or "useful" as key-ish.
        return any(c in ("progression", "useful", "trap", "key") for c in classification)

    def _summarize_rules(self, state: Dict[str, Any]) -> str:
        """
        Construit un petit résumé textuel des règles de la seed à partir de slot_data.

        On se base sur les options Pokemon Emerald d'Archipelago :
        - goal, badges, hms
        - key_items, bikes, event_tickets, rods
        - overworld_items, hidden_items, npc_gifts, berry_trees
        - dexsanity, trainersanity
        - elite_four_requirement / elite_four_count
        - norman_requirement / norman_count
        - remote_items, free_fly_location_id, death_link
        """
        data_storage = state.get("data_storage") or {}
        slot = data_storage.get("slot_data") or {}
        if not isinstance(slot, dict) or not slot:
            return ""

        def yes_no(val: Any) -> str:
            return "Oui" if bool(val) else "Non"

        lines: List[str] = []

        # Objectif (goal)
        goal_map = {
            0: "Champion",
            1: "Steven",
            2: "Norman",
            3: "Legendary Hunt",
        }
        goal_val = slot.get("goal")
        if goal_val is not None:
            goal_str = goal_map.get(goal_val, f"Mode {goal_val}")
            lines.append(f"Objectif: {goal_str}")

        # Badges / HMs
        badge_mode_map = {
            0: "Vanilla",
            1: "Shuffle",
            2: "Complètement random",
        }
        badges_val = slot.get("badges")
        hms_val = slot.get("hms")
        if badges_val is not None or hms_val is not None:
            badge_str = "?"
            hms_str = "?"
            if badges_val is not None:
                badge_str = badge_mode_map.get(badges_val, f"Code {badges_val}")
            if hms_val is not None:
                hms_str = badge_mode_map.get(hms_val, f"Code {hms_val}")
            lines.append(f"Badges: {badge_str} – HMs: {hms_str}")

        # Randomisation des items "globaux"
        lines.append(
            "Key items: {key_items} – Bikes: {bikes} – Event tickets: {event_tickets} – Rods: {rods}".format(
                key_items=yes_no(slot.get("key_items")),
                bikes=yes_no(slot.get("bikes")),
                event_tickets=yes_no(slot.get("event_tickets")),
                rods=yes_no(slot.get("rods")),
            )
        )

        # Items de terrain / cadeaux / baies
        lines.append(
            "Items: Overworld {ovw} – Hidden {hid} – NPC gifts {npc} – Berry trees {berries}".format(
                ovw=yes_no(slot.get("overworld_items")),
                hid=yes_no(slot.get("hidden_items")),
                npc=yes_no(slot.get("npc_gifts")),
                berries=yes_no(slot.get("berry_trees")),
            )
        )

        # Sanities
        lines.append(
            f"Dexsanity: {yes_no(slot.get('dexsanity'))} – Trainersanity: {yes_no(slot.get('trainersanity'))}"
        )

        # Item pool (si présent)
        item_pool_map = {
            0: "Shuffled",
            1: "Diverse balanced",
            2: "Diverse",
        }
        pool_val = slot.get("item_pool_type")
        if pool_val is not None:
            pool_str = item_pool_map.get(pool_val, f"Code {pool_val}")
            lines.append(f"Item pool: {pool_str}")

        # Flash requis dans les cavernes
        flash_map = {
            0: "Aucun",
            1: "Granite Cave seulement",
            2: "Victory Road seulement",
            3: "Granite Cave + Victory Road",
        }
        require_flash_val = slot.get("require_flash")
        if require_flash_val is not None:
            flash_str = flash_map.get(require_flash_val, f"Code {require_flash_val}")
            lines.append(f"Flash requis: {flash_str}")

        # Elite Four
        elite_req_map = {
            0: "Badges",
            1: "Gyms",
        }
        ef_req_val = slot.get("elite_four_requirement")
        ef_count_val = slot.get("elite_four_count")
        if ef_req_val is not None or ef_count_val is not None:
            ef_req_str = (
                elite_req_map.get(ef_req_val, f"Code {ef_req_val}")
                if ef_req_val is not None
                else "?"
            )
            if ef_count_val is not None:
                lines.append(f"Elite Four: {ef_count_val} {ef_req_str.lower()}")
            else:
                lines.append(f"Elite Four: {ef_req_str}")

        # Norman
        norm_req_val = slot.get("norman_requirement")
        norm_count_val = slot.get("norman_count")
        if norm_req_val is not None or norm_count_val is not None:
            norm_req_str = (
                elite_req_map.get(norm_req_val, f"Code {norm_req_val}")
                if norm_req_val is not None
                else "?"
            )
            if norm_count_val is not None:
                lines.append(f"Norman: {norm_count_val} {norm_req_str.lower()}")
            else:
                lines.append(f"Norman: {norm_req_str}")

        # QoL / divers
        free_fly = "Oui" if slot.get("free_fly_location_id") not in (None, 0) else "Non"
        remote_items = yes_no(slot.get("remote_items"))
        death_link = yes_no(slot.get("death_link"))
        lines.append(
            f"QoL: Remote items {remote_items} – Free Fly {free_fly} – DeathLink {death_link}"
        )

        return "\n".join(lines)

    def _summarize_flags(self, state: Dict[str, Any]) -> str:
        """
        Construit une liste compacte de 'flags' (options importantes) à partir de slot_data.
        Pensé pour Pokemon Emerald Archipelago.
        """
        data_storage = state.get("data_storage") or {}
        slot = data_storage.get("slot_data") or {}
        if not isinstance(slot, dict) or not slot:
            return ""

        flags: List[str] = []

        # -------- Goal --------
        goal_map = {
            0: "Objectif: Champion",
            1: "Objectif: Steven",
            2: "Objectif: Norman",
            3: "Objectif: Legendary Hunt",
        }
        goal_val = slot.get("goal")
        if goal_val in goal_map:
            flags.append(goal_map[goal_val])

        # -------- Badges / HMs --------
        badge_mode_map = {
            0: None,  # Vanilla -> on n'affiche pas
            1: "Badges mélangés",
            2: "Badges aléatoires",
        }
        hms_mode_map = {
            0: None,
            1: "HMs mélangées",
            2: "HMs aléatoires",
        }

        badges_val = slot.get("badges")
        if badges_val in badge_mode_map and badge_mode_map[badges_val]:
            flags.append(badge_mode_map[badges_val])

        hms_val = slot.get("hms")
        if hms_val in hms_mode_map and hms_mode_map[hms_val]:
            flags.append(hms_mode_map[hms_val])

        # -------- Petits helpers --------
        def add_bool_flag(key: str, label: str) -> None:
            if slot.get(key):
                flags.append(label)

        # -------- Randomisation d'items globaux --------
        add_bool_flag("key_items", "Key items randomisés")
        add_bool_flag("bikes", "Bikes randomisées")
        add_bool_flag("event_tickets", "Event tickets randomisés")
        add_bool_flag("rods", "Rods randomisées")

        # -------- Items de terrain / cadeaux / baies --------
        add_bool_flag("overworld_items", "Items overworld randomisés")
        add_bool_flag("hidden_items", "Items cachés randomisés")
        add_bool_flag("npc_gifts", "Cadeaux NPC randomisés")
        add_bool_flag("berry_trees", "Berry trees randomisées")

        # -------- Sanities --------
        add_bool_flag("dexsanity", "Dexsanity")
        add_bool_flag("trainersanity", "Trainersanity")

        # -------- QoL / multi --------
        add_bool_flag("remote_items", "Remote items")
        if slot.get("death_link"):
            flags.append("DeathLink")
        if slot.get("free_fly_location_id") not in (None, 0):
            flags.append("Free Fly activé")

        # -------- Elite Four / Norman --------
        elite_req_map = {
            0: "badges",
            1: "gyms",
        }
        ef_count = slot.get("elite_four_count")
        ef_req = slot.get("elite_four_requirement")
        if ef_count is not None and ef_req in elite_req_map:
            flags.append(f"Elite Four: {ef_count} {elite_req_map[ef_req]} requis")

        norm_count = slot.get("norman_count")
        norm_req = slot.get("norman_requirement")
        if norm_count is not None and norm_req in elite_req_map:
            flags.append(f"Norman: {norm_count} {elite_req_map[norm_req]} requis")

        # Si rien de spécial, on retournera chaîne vide -> le handler gérera ça.
        if not flags:
            return ""

        # Liste compacte séparée par des " · " (plus lisible qu'une grosse phrase).
        return " · ".join(flags)

    async def _send_split(self, target: Any, text: str) -> None:
        """
        Send a potentially long message, splitting it into multiple Twitch-sized messages.
        target can be a Context or a Channel; both expose .send().
        """
        if not text:
            return

        for line in text.splitlines():
            line = line.rstrip()
            if not line:
                continue

            while len(line) > MAX_TWITCH_MESSAGE_LENGTH:
                chunk = line[:MAX_TWITCH_MESSAGE_LENGTH]
                await target.send(chunk)
                line = line[MAX_TWITCH_MESSAGE_LENGTH:]
            if line:
                await target.send(line)

    def _fmt_msg(self, key: str, default: str, **kwargs: Any) -> str:
        """
        Format a message using an optional MessageManager if provided, otherwise fallback.
        """
        if self.messages is not None:
            # Very defensive: the user MessageManager might not match our expectations.
            fmt = None
            try:
                if hasattr(self.messages, "format"):
                    fmt = self.messages.format(key, **kwargs)  # type: ignore[call-arg]
                elif hasattr(self.messages, "get"):
                    template = self.messages.get(key)
                    if isinstance(template, str):
                        fmt = template.format(**kwargs)
            except Exception as e:  # pragma: no cover - defensive
                self.log.warning("MessageManager failed for key '%s': %s", key, e)

            if isinstance(fmt, str):
                return fmt

        try:
            return default.format(**kwargs)
        except Exception:
            return default

    def _is_probable_key_item_by_name(self, item_name: str) -> bool:
        """
        Heuristique simple pour détecter un 'item clé' à partir de son nom.
        Pour l'instant: HMs et Badges (Pokemon Emerald).

        On pourra étendre cette logique plus tard (Master Ball, etc.).
        """
        if not item_name:
            return False

        name_up = item_name.upper()

        # HMs: HM01 Cut, HM02 Fly, etc.
        if name_up.startswith("HM"):
            return True

        # Badges: Stone Badge, Knuckle Badge, etc.
        if "BADGE" in name_up:
            return True

        return False

    def _is_admin(self, ctx: commands.Context) -> bool:
        name = (ctx.author.name or "").lower()
        # TwitchIO marks broadcaster via author.is_broadcaster in 3.x
        if getattr(ctx.author, "is_broadcaster", False):
            return True
        if getattr(ctx.author, "is_mod", False):
            return True
        if name in self.admin_users:
            return True
        # Also treat the configured channel as owner
        if name == self.channel_name.lower():
            return True
        return False

    def _get_default_channel(self):
        if self.connected_channels:
            return self.connected_channels[0]
        return None

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #

    async def event_ready(self):
        self.log.info("InterpreterBot connected as %s", self.nick)

        # Start background tasks once
        if self._about_task is None:
            self._about_task = asyncio.create_task(self._about_loop())
        if self._watch_items_task is None and self._auto_announce_items:
            self._watch_items_task = asyncio.create_task(self._watch_items_loop())

        channel = self._get_default_channel()
        if channel:
            msg = self._fmt_msg(
                "bot_connected",
                "Archipelago bot connecté. Tapez !help pour la liste des commandes de base.",
            )
            await self._send_split(channel, msg)

    async def event_message(self, message):
        # Ignore our own messages
        if message.echo:
            return

        await self.handle_commands(message)

    async def event_command_error(self, ctx: commands.Context, error: Exception):
        # Commande inexistante (ex: !rules pour l'instant)
        from twitchio.ext.commands import CommandNotFound

        if isinstance(error, CommandNotFound):
            # On log juste, sans spammer le chat ni crasher
            self.log.error("Error in command None: %s", error)
            # Optionnel : si tu veux un message, décommente:
            # await ctx.send("Commande inconnue.")
            return

        cmd_name = getattr(getattr(ctx, "command", None), "name", "inconnue")
        self.log.error("Error in command %s: %s", cmd_name, error, exc_info=error)
        await ctx.send(f"Une erreur est survenue dans la commande {cmd_name}.")

    # ------------------------------------------------------------------ #
    # Background tasks
    # ------------------------------------------------------------------ #

    async def _about_loop(self):
        # Simple periodic !about message
        try:
            while True:
                await asyncio.sleep(self._about_interval_minutes * 60)
                channel = self._get_default_channel()
                if channel:
                    await self._cmd_about_internal(channel)
        except asyncio.CancelledError:
            return

    async def _watch_items_loop(self):
        # Watch state.json for new items and announce them automatically
        try:
            while True:
                await asyncio.sleep(2)
                state = self._load_state()
                items = state.get("items") or []
                current_count = len(items)

                # Rien de nouveau
                if current_count <= self._last_item_count:
                    continue

                # Slice des nouveaux items
                new_items = items[self._last_item_count:current_count]
                self._last_item_count = current_count

                channel = self._get_default_channel()
                if not channel:
                    continue

                # ------------------------------------------------------------------
                # Mapping ID -> nom via data_package (comme !lastitem)
                # ------------------------------------------------------------------
                archi = state.get("archipelago") or {}
                me = state.get("me") or {}

                game_name = (me.get("game") or archi.get("game") or "").strip()

                data_storage = state.get("data_storage") or {}
                data_package = data_storage.get("data_package") or {}
                games_pkg = data_package.get("games") or {}

                game_pkg = None
                if game_name and game_name in games_pkg:
                    game_pkg = games_pkg[game_name]
                elif "Pokemon Emerald" in games_pkg:
                    # Fallback pratique pour tes tests actuels
                    game_pkg = games_pkg["Pokemon Emerald"]
                elif len(games_pkg) == 1:
                    game_pkg = next(iter(games_pkg.values()))

                item_id_to_name: dict[int, str] = {}
                location_id_to_name: dict[int, str] = {}

                if isinstance(game_pkg, dict):
                    item_name_to_id = game_pkg.get("item_name_to_id") or {}
                    location_name_to_id = game_pkg.get("location_name_to_id") or {}

                    # Inversion: name -> id  =>  id -> name
                    item_id_to_name = {v: k for k, v in item_name_to_id.items()}
                    location_id_to_name = {v: k for k, v in location_name_to_id.items()}

                progress = self._get_progress(state)

                for item in new_items:
                    # Résolution des noms
                    item_id = item.get("item")
                    location_id = item.get("location")

                    item_name = item_id_to_name.get(item_id)
                    location_name = location_id_to_name.get(location_id)

                    if not item_name:
                        if item_id is not None:
                            item_name = f"Item {item_id}"
                        else:
                            item_name = "Item ?"

                    if not location_name:
                        if location_id is not None:
                            location_name = f"Loc {location_id}"
                        else:
                            location_name = "Loc ?"

                    # Pour l’instant, on ne distingue pas encore les key items proprement
                    is_key = self._is_key_item(item, state)

                    checks_done = progress["checks_done"]
                    total = progress["total_locations"]
                    percent = progress["percent"]
                    remaining = progress["remaining"]

                    if total:
                        base_msg = (
                            "{player} a obtenu {item_name} ({location_name}) - "
                            "{checks_done}/{total} checks ({percent:.1f}%) - "
                            "{remaining} restants."
                        )
                    else:
                        base_msg = (
                            "{player} a obtenu {item_name} ({location_name}) - "
                            "{checks_done} checks complétés."
                        )

                    player_name = (
                        item.get("player_name")
                        or self.config.get("archipelago", {}).get("slot_name")
                        or "Le joueur"
                    )

                    text = base_msg.format(
                        player=player_name,
                        item_name=item_name,
                        location_name=location_name,
                        checks_done=checks_done,
                        total=total,
                        percent=percent,
                        remaining=remaining,
                    )

                    if is_key:
                        text = f"🔑✨ {text} ✨🔑"

                    await self._send_split(channel, text)
        except asyncio.CancelledError:
            return

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    @commands.command(name="keyitems")
    async def cmd_keyitems(self, ctx: commands.Context):
        """
        Affiche les items 'clés' obtenus (HMs, badges, etc.) en se basant sur les noms AP.
        v1: heuristique par nom (HM*, *Badge).
        """
        state = self._load_state() or {}
        items = state.get("items") or []
        if not isinstance(items, list) or not items:
            text = self._fmt_msg(
                "keyitems.empty",
                "Aucun item clé obtenu pour l'instant.",
            )
            await self._send_split(ctx, text)
            return

        # ------------------------------------------------------------------
        # Mapping ID -> noms via data_package (comme !lastitem)
        # ------------------------------------------------------------------
        archi = state.get("archipelago") or {}
        me = state.get("me") or {}

        game_name = (me.get("game") or archi.get("game") or "").strip()

        data_storage = state.get("data_storage") or {}
        data_package = data_storage.get("data_package") or {}
        games_pkg = data_package.get("games") or {}

        game_pkg = None
        if game_name and game_name in games_pkg:
            game_pkg = games_pkg[game_name]
        elif "Pokemon Emerald" in games_pkg:
            game_pkg = games_pkg["Pokemon Emerald"]
        elif len(games_pkg) == 1:
            game_pkg = next(iter(games_pkg.values()))

        item_id_to_name: dict[int, str] = {}
        location_id_to_name: dict[int, str] = {}

        if isinstance(game_pkg, dict):
            item_name_to_id = game_pkg.get("item_name_to_id") or {}
            location_name_to_id = game_pkg.get("location_name_to_id") or {}

            item_id_to_name = {v: k for k, v in item_name_to_id.items()}
            location_id_to_name = {v: k for k, v in location_name_to_id.items()}

        # ------------------------------------------------------------------
        # Parcourir les items dans l'ordre d'index et garder uniquement
        # les items 'clés' uniques (par item_id).
        # ------------------------------------------------------------------
        sorted_items = sorted(items, key=lambda it: it.get("index", 0))
        seen_item_ids = set()
        key_items: list[tuple[str, str]] = []  # (item_name, location_name)

        for it in sorted_items:
            # Compat: certains fetchers peuvent utiliser 'item_id' / 'location_id'
            raw_item_id = it.get("item")
            if raw_item_id is None:
                raw_item_id = it.get("item_id")

            raw_loc_id = it.get("location")
            if raw_loc_id is None:
                raw_loc_id = it.get("location_id")

            if raw_item_id is None:
                continue

            if raw_item_id in seen_item_ids:
                continue

            item_name = item_id_to_name.get(raw_item_id)
            if not item_name:
                # Si on n'a même pas de nom, on ne peut pas appliquer l'heuristique
                continue

            if not self._is_probable_key_item_by_name(item_name):
                continue

            seen_item_ids.add(raw_item_id)

            loc_name = location_id_to_name.get(raw_loc_id) if raw_loc_id is not None else None
            if not loc_name:
                if raw_loc_id is not None:
                    loc_name = f"Loc {raw_loc_id}"
                else:
                    loc_name = "Lieu inconnu"

            key_items.append((item_name, loc_name))

        if not key_items:
            text = self._fmt_msg(
                "keyitems.empty",
                "Aucun item clé obtenu pour l'instant.",
            )
            await self._send_split(ctx, text)
            return

        # Construire les lignes pour le chat
        lines = [f"- {iname} ({lname})" for (iname, lname) in key_items]

        text = self._fmt_msg(
            "keyitems",
            "Items clés obtenus:\n{lines}",
            lines="\n".join(lines),
        )
        await self._send_split(ctx, text)

    @commands.command(name="rules")
    async def cmd_rules(self, ctx: commands.Context):
        """Affiche un résumé des règles / settings de la seed Archipelago."""
        state = self._load_state()
        summary = self._summarize_rules(state)

        if not summary:
            # Pas de slot_data -> on évite de mentir
            text = self._fmt_msg(
                "rules.empty",
                "Impossible de lire les règles de la seed depuis state.json.",
            )
            await self._send_split(ctx, text)
            return

        # Utilise MessageManager si une clé 'rules' existe, sinon fallback
        text = self._fmt_msg(
            "rules",
            "Règles principales de la seed:\n{summary}",
            summary=summary,
        )
        await self._send_split(ctx, text)


    @commands.command(name="iteminfo")
    async def cmd_iteminfo(self, ctx: commands.Context, *args):
        """
        Affiche la description PokéAPI du dernier item (ou du n-ième dernier).

        Usage:
          !iteminfo        -> décrit le dernier item unique reçu
          !iteminfo 3      -> décrit le 3e item unique le plus récent
        """
        state = self._load_state() or {}
        items = state.get("items") or []
        if not isinstance(items, list) or not items:
            await ctx.send("Aucun item reçu pour le moment.")
            return

        # On veut le n-ième item unique (item_id, location_id), par défaut 1
        index = 1
        if args:
            try:
                index = max(1, int(args[0]))
            except Exception:
                index = 1

        # Mapping ID -> noms via data_package, comme !lastitem
        archi = state.get("archipelago") or {}
        me = state.get("me") or {}
        game_name = (me.get("game") or archi.get("game") or "").strip()

        data_storage = state.get("data_storage") or {}
        data_package = data_storage.get("data_package") or {}
        games_pkg = data_package.get("games") or {}

        game_pkg = None
        if game_name and game_name in games_pkg:
            game_pkg = games_pkg[game_name]
        elif "Pokemon Emerald" in games_pkg:
            game_pkg = games_pkg["Pokemon Emerald"]
        elif len(games_pkg) == 1:
            game_pkg = next(iter(games_pkg.values()))

        item_id_to_name: dict[int, str] = {}
        location_id_to_name: dict[int, str] = {}

        if isinstance(game_pkg, dict):
            item_name_to_id = game_pkg.get("item_name_to_id") or {}
            location_name_to_id = game_pkg.get("location_name_to_id") or {}
            item_id_to_name = {v: k for k, v in item_name_to_id.items()}
            location_id_to_name = {v: k for k, v in location_name_to_id.items()}

        # Construire la liste des items uniques (comme !lastitem)
        sorted_items = sorted(items, key=lambda it: it.get("index", 0), reverse=True)
        uniques: list[dict] = []
        seen_pairs = set()

        for it in sorted_items:
            pair = (it.get("item"), it.get("location"))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            uniques.append(it)
            if len(uniques) >= max(index, 5):
                # on s'arrête quand on a assez d'entries pour couvrir l'index demandé
                break

        if not uniques:
            await ctx.send("Aucun item reçu pour le moment.")
            return

        if index > len(uniques):
            await ctx.send(f"Il n'y a pas encore {index} items uniques récents.")
            return

        target = uniques[index - 1]
        item_id = target.get("item")
        loc_id = target.get("location")

        item_name = item_id_to_name.get(item_id) or f"Item {item_id}"
        location_name = location_id_to_name.get(loc_id) or f"Loc {loc_id}"

        info = await self._fetch_item_info(item_name)
        if not info:
            await ctx.send(f"Infos PokéAPI introuvables pour {item_name}.")
            return

        default = (
            "Item: {name} – Dernier check: {location}\n"
            "Effet: {short_effect}\n"
            "Description: {flavor}"
        )

        text = self._fmt_msg(
            "iteminfo",
            default,
            name=info.get("name") or item_name,
            location=location_name,
            short_effect=info.get("short_effect") or "(aucun effet trouvé)",
            flavor=info.get("flavor_text") or "(aucune description trouvée)",
        )

        await self._send_split(ctx, text)

    @commands.command(name="seedinfo")
    async def cmd_seedinfo(self, ctx: commands.Context):
        """Affiche les infos de base de la seed Archipelago."""
        state = self._load_state()
        room = state.get("room", {})
        archi = state.get("archipelago", {})

        seed = room.get("seed") or archi.get("seed") or "???"
        game = archi.get("game") or "Unknown"
        server_ver = room.get("server_version") or "?"
        gen_ver = room.get("generator_version") or "?"

        text = self._fmt_msg(
            "seedinfo",
            "Seed: {seed} – Game: {game} – Archipelago {server_ver}",
            seed=seed,
            game=game,
            server_ver=server_ver,
            generator_ver=gen_ver,
            # pour les placeholders JSON
            server_version=server_ver,
        )
        await self._send_split(ctx, text)


    @commands.command(name="progress")
    async def cmd_progress(self, ctx: commands.Context):
        """Affiche la progression générale (checks complétés)."""
        # On charge le state brut
        state = self._load_state()

        # 1) Checks complétés
        checked_locations = state.get("checked_locations") or []
        checks_done = len(checked_locations)

        # 2) Total des checks : priorité à state["room"]["location_count"],
        #    sinon override dans config.archipelago.total_locations_override,
        #    sinon bot_settings.total_locations, sinon 0.
        room = state.get("room") or {}
        total = room.get("location_count") or 0

        # Lecture override depuis la config déjà chargée dans le bot
        arch_cfg = self.config.get("archipelago", {}) if hasattr(self, "config") else {}
        bot_cfg = self.config.get("bot_settings", {}) if hasattr(self, "config") else {}

        if not isinstance(total, int):
            try:
                total = int(total)
            except Exception:
                total = 0

        if total <= 0:
            override = arch_cfg.get("total_locations_override") or bot_cfg.get("total_locations") or 0
            if isinstance(override, str):
                if override.isdigit():
                    override = int(override)
                else:
                    override = 0
            if isinstance(override, int) and override > 0:
                total = override

        # 3) Calcul pourcentage / restants
        if total > 0:
            remaining = max(total - checks_done, 0)
            percent = (checks_done / total) * 100.0

            default = "{checks_done} / {total} checks ({percent:.1f}%) complétés – {remaining} restants."
            text = self._fmt_msg(
                "progress",
                default,
                checks_done=checks_done,
                total=total,
                remaining=remaining,
                percent=percent,
                # placeholders pour messages.en.json : %a %b %c %d
                a=checks_done,
                b=total,
                c=f"{percent:.1f}",
                d=remaining,
            )
        else:
            # Si on n'a vraiment aucun total fiable, on ne ment pas.
            default = "{checks_done} checks complétés – total de la seed non disponible."
            text = self._fmt_msg(
                "progress.unknown",
                default,
                checks_done=checks_done,
                a=checks_done,
            )

        await self._send_split(ctx, text)

    @commands.command(name="flags")
    async def cmd_flags(self, ctx: commands.Context):
        """Affiche une liste condensée des flags / options importantes de la seed."""
        state = self._load_state()
        summary = self._summarize_flags(state)

        if not summary:
            # Pas de slot_data ou rien de spécial
            text = self._fmt_msg(
                "flags.empty",
                "Aucun flag spécial détecté pour cette seed (ou slot_data indisponible).",
            )
            await self._send_split(ctx, text)
            return

        text = self._fmt_msg(
            "flags",
            "Flags principaux: {flags}",
            flags=summary,
        )
        await self._send_split(ctx, text)

    @commands.command(name="lastitem")
    async def cmd_lastitem(self, ctx: commands.Context):
        """Affiche les 5 derniers items obtenus (avec noms via data_package, sans doublons)."""
        state = self._load_state() or {}

        items = state.get("items") or []
        if not isinstance(items, list):
            items = []

        if not items:
            await ctx.send("Aucun item reçu pour le moment.")
            return

        # ------------------------------------------------------------------
        # Récupérer le data_package pour faire le mapping ID -> nom
        # ------------------------------------------------------------------
        archi = state.get("archipelago") or {}
        me = state.get("me") or {}

        game_name = (me.get("game") or archi.get("game") or "").strip()

        data_storage = state.get("data_storage") or {}
        data_package = data_storage.get("data_package") or {}
        games_pkg = data_package.get("games") or {}

        game_pkg = None
        if game_name and game_name in games_pkg:
            game_pkg = games_pkg[game_name]
        elif "Pokemon Emerald" in games_pkg:
            game_pkg = games_pkg["Pokemon Emerald"]
        elif len(games_pkg) == 1:
            game_pkg = next(iter(games_pkg.values()))

        item_id_to_name = {}
        location_id_to_name = {}

        if isinstance(game_pkg, dict):
            item_name_to_id = game_pkg.get("item_name_to_id") or {}
            location_name_to_id = game_pkg.get("location_name_to_id") or {}
            item_id_to_name = {v: k for k, v in item_name_to_id.items()}
            location_id_to_name = {v: k for k, v in location_name_to_id.items()}

        # ------------------------------------------------------------------
        # Trier par index décroissant et garder des entrées UNIQUES
        # (item_id, location_id) pour éviter les doublons visuels
        # ------------------------------------------------------------------
        sorted_items = sorted(items, key=lambda it: it.get("index", 0), reverse=True)

        latest: list[dict] = []
        seen_pairs = set()  # (item_id, location_id)

        for it in sorted_items:
            item_id = it.get("item")
            loc_id = it.get("location")
            pair = (item_id, loc_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            latest.append(it)
            if len(latest) >= 5:
                break

        if not latest:
            await ctx.send("Aucun item reçu pour le moment.")
            return

        # ------------------------------------------------------------------
        # Construire les lignes "player: item_name @ location_name"
        # ------------------------------------------------------------------
        slot_name = self.config.get("archipelago", {}).get("slot_name") or "Le joueur"
        lines = []

        for it in latest:
            item_id = it.get("item")
            loc_id = it.get("location")

            item_name = item_id_to_name.get(item_id)
            loc_name = location_id_to_name.get(loc_id)

            if not item_name:
                if item_id is not None:
                    item_name = f"Item {item_id}"
                else:
                    item_name = "Item ?"

            if not loc_name:
                if loc_id is not None:
                    loc_name = f"Loc {loc_id}"
                else:
                    loc_name = "Loc ?"

            player_name = (
                it.get("player_name")
                or slot_name
                or "Le joueur"
            )

            lines.append(f"{player_name}: {item_name} @ {loc_name}")

        text = self._fmt_msg(
            "lastitem",
            "Derniers items:\n{lines}",
            lines="\n".join(lines),
        )
        await self._send_split(ctx, text)


    @commands.command(name="help")
    async def cmd_help(self, ctx: commands.Context):
        """Résumé rapide des commandes principales et lien vers la doc complète."""
        bot_cfg = self.config.get("bot_settings", {})
        help_url = bot_cfg.get("help_url") or "https://github.com/lovenityjade/APTwitchBot"

        default = (
            "Commandes principales: !seedinfo, !progress, !lastitem, !about\n"
            "Pour la liste complète et la doc: {help_url}"
        )
        text = self._fmt_msg("help", default, help_url=help_url)
        await self._send_split(ctx, text)

    async def _cmd_about_internal(self, target: Any):
        """Internal helper so we can call !about depuis le timer ou le chat."""
        bot_cfg = self.config.get("bot_settings", {})
        repo_url = bot_cfg.get("repo_url") or "https://github.com/lovenityjade/APTwitchBot"
        help_url = bot_cfg.get("help_url") or repo_url
        author = bot_cfg.get("author") or "Jade (TheLovenityJade)"

        default = (
            "AP-Twitch Bridge – Archipelago → Twitch bot développé par Jade (TheLovenityJade). "
            "Code source & téléchargement: {repo_url} – Tapez !help pour les commandes."
        )

        text = self._fmt_msg(
            "about",
            default,
            # placeholders pour messages.en.json
            author=author,
            repo=repo_url,
            # placeholders pour la chaîne de fallback
            repo_url=repo_url,
            help_url=help_url,
        )
        await self._send_split(target, text)


    @commands.command(name="about")
    async def cmd_about(self, ctx: commands.Context):
        """Informations sur le bot et lien GitHub."""
        await self._cmd_about_internal(ctx)

    # ------------------------------------------------------------------ #
    # Admin / debug commands
    # ------------------------------------------------------------------ #

    @commands.command(name="apraw")
    async def cmd_apraw(self, ctx: commands.Context):
        """Admin: renvoie quelques infos brutes pour debug."""
        if not self._is_admin(ctx):
            return

        state = self._load_state()
        room = state.get("room", {})
        archi = state.get("archipelago", {})
        me = state.get("me", {})

        text = (
            f"[DEBUG] room={room.get('room_name','')} "
            f"seed={room.get('seed','')} "
            f"game={archi.get('game','')} "
            f"slot_id={me.get('slot_id',-1)} "
            f"player_number={me.get('player_number',-1)}"
        )
        await self._send_split(ctx, text)

    @commands.command(name="apreload")
    async def cmd_apreload(self, ctx: commands.Context):
        """Admin: force un rechargement du state.json."""
        if not self._is_admin(ctx):
            return

        # Just attempt to read file and update last_item_count
        state = self._load_state()
        items = state.get("items") or []
        self._last_item_count = len(items)
        await ctx.send("state.json rechargé manuellement.")
