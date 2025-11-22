# Interpreter (Python + TwitchIO)

The interpreter is a Twitch bot that reads `data/state.json` (written by the C++ fetcher)
and exposes information to Twitch chat.

## Features

- Reads Archipelago state (seed, room, items, checked locations, etc.).
- User commands:
  - `!seedinfo`
  - `!rules`
  - `!progress`
  - `!lastitem`
  - `!flags`
  - `!keyitems`
  - `!identity`
  - `!team`
  - `!help`
  - `!about`
- Admin/debug commands (for the streamer / mods), e.g.:
  - `!apreload`
  - `!aplog <lines>`
  - `!apraw <section>`
  - `!apstatus`
- Automatic messages:
  - Announcement on new items from Archipelago
  - Periodic `!about` reminder every X minutes

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

## Config

Main config is in `config/config.json`:

- Twitch:
  - OAuth token
  - Channel name
- Paths:
  - `data/state.json`
  - `logs/fetcher.log`
  - `logs/interpreter.log`
  - `config/messages.en.json`
- Settings:
  - Prefix (`!`)
  - Admins
  - About timer interval
  - Help URL (`help_url`) shown in `!help` and `!about`.

## Running

```bash
cd interpreter
python3 main.py
```

Make sure the C++ fetcher is connected and updating `data/state.json` before running the interpreter.
