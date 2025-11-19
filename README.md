# ap-bridge – Archipelago → Twitch Bot Bridge

`ap-bridge` is a small two-layer project that connects an **Archipelago** multiworld server to a **Twitch chat bot**.

The idea is simple:

- A **C++ fetcher** connects to the real Archipelago server (multiworld port, not the WebHost), listens to **everything it can**, and writes a raw game state to `data/state.json`.
- A **Python Twitch bot** reads `data/state.json` and exposes commands like `!checks`, `!seedinfo`, `!settings`, etc. to chat.

The fetcher is **100% read-only**: it never sends checks, never pretends to be a tracker, and never pushes gameplay actions to the server.  
All logic and presentation live on the Python side.

---

## ✨ Goals

- Connect to a running **Archipelago** seed as a passive client.
- Subscribe to all relevant callbacks via **apclientpp** (items, locations, data storage, messages, status, etc.).
- Maintain a **generic, exhaustive state** of the game in `data/state.json`:
  - room & seed info,
  - players & game,
  - items received,
  - checked locations,
  - data storage keys,
  - messages and status,
  - raw slot data & data package.
- Never have to touch the C++ fetcher again when adding features:
  - all future features are done by extending the **Python interpreter / bot** that reads `state.json`.

---

## 🧱 Architecture

### 1. Fetcher (`ap_fetcher`, C++ / apclientpp)

- Uses [`apclientpp`](https://github.com/black-sliver/apclientpp) (and its dependency [`wswrap`](https://github.com/black-sliver/wswrap)) to connect to the **real** Archipelago server:
  - host, port, slot name, password, game are read from `config/config.json`.
- Registers all useful handlers:
  - socket events (connected, disconnected, error),
  - `room_info`, `slot_connected`, `slot_refused`,
  - `items_received`,
  - `location_checked`,
  - `data_package_changed`,
  - `print` & `print_json` (for messages),
  - data storage (`retrieved`, `set_reply`),
  - `bounced`.
- Maintains a big in-memory JSON state (via **nlohmann/json**) with sections like:
  - `meta` – fetcher metadata, timestamps;
  - `connection` – connection state, last events, errors;
  - `archipelago` – host, port, slot name, game;
  - `items.received[]` – all items received by this slot;
  - `locations.checked[]` – all checked locations for this slot;
  - `messages[]` – chat / print / print_json entries;
  - `data_storage` – retrieved keys and set replies;
  - `raw.slot_data`, `raw.data_package`, `raw.last_bounce`, etc.
- Periodically flushes this state to **`data/state.json`** every `state_flush_interval_sec` seconds (configurable).
- Logs its activity to **`logs/fetcher.log`**.

> 🔒 **Important:** The fetcher is *read-only*. It does **not**:
> - send `LocationChecks`,
> - send `StatusUpdate` to change the player state,
> - act as an autotracker writing to the server.
>  
> It only listens and records.

---

### 2. Interpreter / Twitch Bot (`interpreter/`, Python)

*(Work in progress)*

- Runs in a Python virtualenv on a Linux VPS (Ubuntu 24.10, Python 3.13).
- Never talks to Archipelago directly.
- Periodically reads `data/state.json` and exposes Twitch chat commands via IRC:
  - `!checks` – number of checked locations / total (if available),
  - `!settings` – seed settings (as much as we can reconstruct from available data),
  - `!seedinfo` – game, seed name, time elapsed, etc.
  - later: multiworld info (other players’ items/progression), stats, etc.
- Logs its own operations to **`logs/bot.log`**.
- All evolution and new features (new commands, formatting, overlays, etc.) happen **here**, not in the C++ layer.


🧪 Status

✅ C++ fetcher architecture and build system.
✅ Integration with apclientpp + wswrap + websocketpp + asio + nlohmann/json.
✅ Periodic flush of a generic state to data/state.json.
🟡 Python interpreter / Twitch bot:

TODO: implement IRC connection to Twitch and chat commands.
TODO: define stable schema for the parts of state.json used by commands like !checks, !seedinfo, !settings.

🙏 Credits & Acknowledgements

This project would not be possible without the work of:

Archipelago – the multiworld randomizer ecosystem and protocol.
https://archipelago.gg
apclientpp – C++ client library for Archipelago by black-sliver.
https://github.com/black-sliver/apclientpp
wswrap – websocket wrapper used by apclientpp (also by black-sliver).
https://github.com/black-sliver/wswrap
asio – cross-platform C++ networking library by Christopher M. Kohlhoff.
https://github.com/chriskohlhoff/asio
websocketpp – C++ websocket library by Zaphoyd Studios.
https://github.com/zaphoyd/websocketpp
nlohmann/json – JSON library for modern C++ by Niels Lohmann.
https://github.com/nlohmann/json

This project is a fan/utility tool built on top of the Archipelago ecosystem.
It is not affiliated with or endorsed by the Archipelago team or the authors of the third-party libraries listed above.
