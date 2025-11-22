# Usage – Commands and behaviour

This document describes how the Twitch bot behaves at runtime and which commands are available in BETA 1.

---

## General behaviour

- The C++ fetcher connects to an Archipelago server and writes a `data/state.json` file.
- The Python interpreter (Twitch bot) periodically reads `data/state.json`.
- All user-facing texts are defined in `config/messages.en.json` and formatted using the internal message manager.
- If `auto_announce_items` is enabled in `config/config.json`, the bot can automatically announce new items as they are received.

The command prefix is defined by `bot_settings.prefix` in `config/config.json`. The default in most setups is `!`.

---

## Commands (BETA 1)

### help

Command:

    !help

Behaviour:

- Shows a short summary of the available commands.
- Includes a help URL if `bot_settings.help_url` is configured.
- Uses the templates defined in `messages.en.json`.

---

### seedinfo

Command:

    !seedinfo

Behaviour:

- Displays basic information about the current Archipelago session:
  - Seed name
  - Game name
  - Server and generator version (if available)
- Uses the `room` and `archipelago` fields stored in `data/state.json`.

---

### progress

Command:

    !progress

Behaviour:

- Computes progression based on:
  - number of checked locations (from `checked_locations`),
  - total number of locations.
- Priority for total locations:
  1. `room.location_count` from `state.json` if present and reliable.
  2. `archipelago.total_locations_override` from `config/config.json`.
  3. `bot_settings.total_locations` as a last-resort fallback.

Output includes:

- completed checks,
- total checks,
- percentage,
- remaining checks.

If the total cannot be determined, a variant with an unknown total is used.

---

### lastitem

Command:

    !lastitem

Behaviour:

- Lists the most recent unique items received.
- Uses `items` from `data/state.json`, sorted by index.
- Maps item and location IDs to readable names using:
  - `data_storage.data_package.games[game].item_name_to_id`
  - `data_storage.data_package.games[game].location_name_to_id`
- Typically shows a short list such as:
  player name, item name, and location name.

---

### rules

Command:

    !rules

Behaviour:

- Summarises the main gameplay settings from `data_storage.slot_data`.
- Typical information includes:
  - victory goal,
  - badge and HM randomisation,
  - key items, bikes, rods, tickets randomisation,
  - overworld and hidden items,
  - NPC gifts and berry trees,
  - dexsanity or trainersanity,
  - Elite Four or gym requirements,
  - flash requirements,
  - DeathLink, remote items, free fly, and other relevant flags.
- Output is a compact multi-line block designed for readability.

---

### flags

Command:

    !flags

Behaviour:

- Provides a compact view of the same information as `!rules`.
- Output is one or a few short lines, focusing on:
  - main victory goal,
  - badge and key item randomisation,
  - various important toggles (for example: dexsanity, DeathLink).
- Intended as a quick-glance summary for viewers familiar with Archipelago.

---

### keyitems

Command:

    !keyitems

Behaviour:

- Shows a unique list of "key items" already obtained during the run.
- Detection is heuristic and based on item names via an internal function similar to `_is_probable_key_item_by_name`.
  Typical examples include:
  - HMs,
  - badges,
  - potentially other progression-critical items.
- Items are listed with their readable names and (optionally) their locations.

---

### about

Command:

    !about

Behaviour:

- Displays project metadata such as:
  - author name or handle,
  - GitHub repository URL,
  - documentation URL,
  - optional credits.
- Most of the text is configured through `bot_settings` and `messages.en.json`.

---

## Auto announcer (optional)

If `auto_announce_items` is set to `true` in `config/config.json`:

- The bot tracks the last seen item index in `data["items"]`.
- On each refresh, it compares current items with the last known index.
- Any new items are announced in chat using resolved item and location names.
- Key items can optionally be highlighted differently or given special wording.

This feature is intended for streamers who want the chat to be automatically informed whenever an important item is received.

---

## Limitations – BETA 1

Current known limitations of BETA 1:

- Multiworld and team support:
  - The bot reads `me.team_id` and related fields,
  - but per-team views and advanced multiworld summaries are only partially implemented.
- Only TwitchIO 2.x is supported and tested.
- macOS and native Windows C++ builds are not formally tested.
  Contributions and feedback for additional platforms are welcome.

