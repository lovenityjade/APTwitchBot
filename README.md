
# ap-bridge – Archipelago ↔ Twitch Bridge

`ap-bridge` is a two-part bridge between an [Archipelago](https://archipelago.gg/) multiworld server and a Twitch chat bot.

- **Sphere 1 – Fetcher (C++)**  
  Connects to an Archipelago server and writes a structured `state.json` file + a text log.

- **Sphere 2 – Interpreter / Twitch Bot (Python + TwitchIO)**  
  Reads `state.json`, interprets the current game state (checks, items, settings, etc.) and exposes Twitch chat commands such as `!seedinfo`, `!progress`, `!lastitem`, `!rules`, `!flags`, `!keyitems`, `!about`…

> **Status:** BETA 1 – used live, but still subject to changes and small bugs.

---

## Features

- Connects to an Archipelago server (multiworld-ready).
- Generates a JSON state file (`data/state.json`) summarizing:
  - room info (seed, server/generator version, location count),
  - player info (slot, team, game),
  - checked locations,
  - received items,
  - slot settings (`slot_data`),
  - data package (name ↔ id mappings).
- Twitch bot (TwitchIO 2.x) reading `state.json` and providing:
  - `!help` – list of commands and help URL,
  - `!seedinfo` – seed, game, server/generator,
  - `!progress` – checks completed / total, percentage, remaining,
  - `!lastitem` – last items received with proper names and locations,
  - `!rules` – human-readable summary of key settings,
  - `!flags` – compact view of the important flags,
  - `!keyitems` – list of obtained key items (HMs, badges, etc.),
  - `!about` – project / author / repo info.
- Optional **auto-announcement** of new items in chat.

---

## Repository layout

ap-bridge/
├─ fetcher/           # Sphere 1 – C++ Archipelago → state.json
├─ interpreter/       # Sphere 2 – Python Twitch bot
├─ config/
│  ├─ config.example.json  # template config (copy to config.json)
│  └─ messages.en.json     # message templates and strings
├─ data/              # runtime state (state.json, ap_uuid.txt), git-ignored
├─ docs/              # additional documentation (INSTALL, USAGE, schema…)
├─ third_party/       # vendored C++ dependencies (apclientpp, json, etc.)
├─ requirements.txt   # Python dependencies (TwitchIO 2.x, etc.)
└─ CMakeLists.txt     # CMake entry point for the fetcher

---

## Requirements

### Common

- An Archipelago server and a valid slot for your game.
- Git, CMake and a reasonably recent C++ toolchain.

### Fetcher (C++ – Sphere 1)

- CMake 3.16+
- C++17-capable compiler:
  - Linux: `g++` or `clang++`
  - Windows: expected to work under MSYS2 / MinGW (not fully tested yet)
  - macOS: should work in theory with `clang++` + CMake, but currently untested
- Internet access to connect to your Archipelago server.

### Interpreter / Bot (Python – Sphere 2)

- Python 3.10+ (3.11 recommended)
- TwitchIO 2.x (>= 2.7, < 3.0 – tested with 2.10.0)
- A Twitch account and an OAuth token for the bot.

---

## Quick start (Linux, WSL, or MSYS2)

### 1. Clone the repository

Commands (bash):

     git clone https://github.com/lovenityjade/APTwitchBot.git
     cd APTwitchBot

### 2. Configuration

Copy the example config and edit it:

    cp config/config.example.json config/config.json

Then edit `config/config.json` and fill in:

- `archipelago.host`, `archipelago.port`, `archipelago.game`, `archipelago.slot_name`, `archipelago.password` (if any),
- `paths.state_file` (usually `data/state.json`),
- `twitch.username`, `twitch.oauth_token`, `twitch.channel`,
- `bot_settings` (prefix, help URL, author, repo URL, etc.).

Important: never commit `config/config.json` – it contains secrets and is git-ignored.

---

### 3. Build the fetcher (Sphere 1)

From the repository root:

    mkdir -p build
    cd build
    cmake ..
    make -j$(nproc)

This should produce the `ap_fetcher` binary (name may vary depending on your CMake config).

Run it from the repo root (or configure paths accordingly):

    ./build/ap_fetcher

If everything works, it will connect to the Archipelago server and start writing `data/state.json`.

---

### 4. Setup the Twitch bot (Sphere 2)

From the repository root:

    python3 -m venv venv
    source venv/bin/activate    (on Windows/PowerShell: .\venv\Scripts\Activate.ps1)
    pip install -r requirements.txt

Then run the interpreter:

    cd interpreter
    python main.py

The bot should connect to Twitch (using the credentials in `config/config.json`) and start reading `data/state.json`.

In your Twitch chat, you can now test:

    !help
    !seedinfo
    !progress
    !lastitem
    !rules
    !flags
    !keyitems
    !about

---

## Platform notes

- Linux / WSL: primary development and testing target.
- Windows:
  - Expected to work under MSYS2 / MinGW for the C++ part (not fully tested yet).
  - Python / TwitchIO should work with a standard Windows Python installation.
- macOS:
  - The C++ fetcher should be buildable with `clang++` + CMake, but this is currently untested.
  - Contributions / feedback for macOS support are welcome.

---

## Roadmap (after BETA 1)

Planned (but not included in this BETA):

- Better multiworld support (`!team`, aggregation per team, etc.).
- Optional game server + seed generator layer (Sphere 3).
- Launcher to orchestrate all components (Sphere 4).

---

## Third-party components and credits

`ap-bridge` relies on several third-party projects.  
All credit for these components goes to their respective authors and maintainers.

Main components:

- Archipelago – multiworld randomizer framework and ecosystem  
  Site: https://archipelago.gg  

- apclientpp – C++ client library for Archipelago, based on the Black-Sliver apclientpp release  
  Repository: https://github.com/black-sliver/apclientpp    

- archipelago_py – Python client / tools for Archipelago  
  Repository: https://github.com/ArchipelagoMW/Archipelago  

- nlohmann/json – JSON library for modern C++  
  Repository: https://github.com/nlohmann/json  

- Valijson – C++ JSON schema validation library  
  Repository: https://github.com/tristanpenman/valijson  

- wswrap – C++ WebSocket wrapper used by apclientpp  
  Repository: https://github.com/ArchipelagoMW/wswrap  

- TwitchIO – Python framework for building Twitch chat bots  
  Documentation: https://twitchio.dev  

All trademarks and copyrights for the above projects remain with their respective owners.

---

## License

This project is licensed under the MIT License – see the `LICENSE` file for details.

FR: Ce projet a été développé et testé principalement sous Linux. Le support Windows (MSYS2) et macOS est possible mais encore expérimental pour cette BETA.
