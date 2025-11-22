"""
!lastitem command
Affiche les derniers items reçus avec les vrais noms (via data_package).
"""

from twitchio.ext import commands
from ..ap_utils import send_long_message


class LastItemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot  # InterpreterBot

    @commands.command(name="lastitem")
    async def lastitem(self, ctx: commands.Context):
        state = self.bot.state
        messages = self.bot.messages

        # 1) Vérifier que le state.json existe
        if not state.exists():
            try:
                text = messages.format("state_missing")
            except Exception:
                text = "State file not found. The Archipelago fetcher may not be running."
            await ctx.send(text)
            return

        # 2) Charger le state brut (state.json du fetcher)
        raw = state.load_state() or {}

        items = raw.get("items") or []
        if not isinstance(items, list):
            items = []

        if not items:
            try:
                text = messages.format("lastitem_empty")
            except Exception:
                text = "Aucun item reçu pour l'instant."
            await ctx.send(text)
            return

        # 3) Récupérer data_package pour mapper IDs -> noms
        arch = raw.get("archipelago") or {}
        me = raw.get("me") or {}

        # On préfère me["game"] à arch["game"] (ex: "Pokemon Emerald")
        game_name = (me.get("game") or arch.get("game") or "").strip()

        data_storage = raw.get("data_storage") or {}
        data_package = data_storage.get("data_package") or {}
        games_pkg = data_package.get("games") or {}

        game_pkg = None

        # Priorité 1 : nom de jeu exact
        if game_name and game_name in games_pkg:
            game_pkg = games_pkg[game_name]
        # Priorité 2 : fallback direct Emerald pour tes tests
        elif "Pokemon Emerald" in games_pkg:
            game_pkg = games_pkg["Pokemon Emerald"]
        # Priorité 3 : un seul jeu dispo
        elif len(games_pkg) == 1:
            game_pkg = next(iter(games_pkg.values()))

        item_id_to_name = {}
        location_id_to_name = {}

        if isinstance(game_pkg, dict):
            item_name_to_id = game_pkg.get("item_name_to_id") or {}
            location_name_to_id = game_pkg.get("location_name_to_id") or {}

            # Inversion : name -> id  =>  id -> name
            item_id_to_name = {item_id: name for name, item_id in item_name_to_id.items()}
            location_id_to_name = {loc_id: name for name, loc_id in location_name_to_id.items()}

        # Petit debug dans le log pour vérifier le mapping
        try:
            self.bot.log.info(
                "lastitem debug: game_name=%r, games_pkg_keys=%r, mapped_items=%d, mapped_locs=%d",
                game_name,
                list(games_pkg.keys()),
                len(item_id_to_name),
                len(location_id_to_name),
            )
        except Exception:
            pass

        # 4) Trier les items par index décroissant et prendre les N derniers
        sorted_items = sorted(items, key=lambda it: it.get("index", 0), reverse=True)
        max_count = 5
        latest_items = sorted_items[:max_count]

        if not latest_items:
            try:
                text = messages.format("lastitem_empty")
            except Exception:
                text = "Aucun item reçu pour l'instant."
            await ctx.send(text)
            return

        lines = []

        # Header : on utilise lastitem_header
        try:
            header = messages.format("lastitem_header", count=len(latest_items))
        except Exception:
            header = f"Derniers items (max {len(latest_items)}):"
        lines.append(header)

        slot_name = self.bot.config.get("archipelago", {}).get("slot_name", "")

        # 5) Construire les lignes avec les vrais noms si possible
        for i, it in enumerate(latest_items, start=1):
            item_id = it.get("item")
            location_id = it.get("location")

            # Essayer de résoudre via data_package
            item_name = item_id_to_name.get(item_id)
            location_name = location_id_to_name.get(location_id)

            # Fallback propre si le mapping n'existe pas
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

            # Debug dans le log pour le premier item
            if i == 1:
                try:
                    self.bot.log.info(
                        "lastitem first entry: index=%d, item_id=%r -> %r, loc_id=%r -> %r",
                        it.get("index"),
                        item_id,
                        item_name,
                        location_id,
                        location_name,
                    )
                except Exception:
                    pass

            try:
                line = messages.format(
                    "lastitem_entry",
                    index=i,
                    item_name=item_name,
                    location_name=location_name,
                    from_player=it.get("player", 0),
                    to_player=slot_name,
                )
            except Exception:
                # Fallback simple si jamais la clé lastitem_entry pose problème
                line = f"{slot_name or 'Player'}: {item_name} @ {location_name}"

            lines.append(line)

        await send_long_message(ctx, "\n".join(lines))
