# League of Legends Stat Tracker and Live Build Assistant

This is a personal League of Legends tracker that stores match statistics and
creates dynamic item recommendations for the champion and role being played in
a live game.

## Current status

**Currently improving the GUI and build recommender.**

The basic Tkinter dashboard, live-game detection, match collector, build
database, and data-driven recommendation pipeline are working. The recommender
can detect the player's champion, role, enemy team, and lane opponent, then
suggest observed starting items, a coherent full build, boots, and situational
items without champion-specific hardcoded item pools.

### Still needs to be done

- Finish automatic Riot match syncing for the Personal Stats tab.
- Store a player identifier with personal matches so stats can be filtered by
  Riot name and tag.
- Improve the GUI layout, navigation, loading feedback, and item presentation.
- Collect more current-patch matches to improve champion-role and matchup
  coverage.
- Add ally-team composition and enemy damage/profile scoring to the build
  recommender.
- Improve low-sample confidence reporting and fallback recommendations.
- Add automated tests for the collector, database, recommender, and GUI logic.
- Add an optional post-session collection workflow so build data is easier to
  keep current.

## What currently works

- Resolves Riot IDs to PUUIDs through the Riot API.
- Collects ranked Summoner's Rift matches and timelines from Match-V5.
- Stores all ten participants from each collected match as build evidence.
- Stores final items, ordered item events, team bans, roles, and lane opponents.
- Downloads and caches patch-correct champion and item metadata from Data
  Dragon.
- Detects the current patch dynamically.
- Reconstructs starting items from the player's first shopping session.
- Builds a coherent observed full-item path rather than mixing unrelated item
  slots.
- Recommends boots and situational completed items.
- Prefers lane-opponent evidence, then enemy-team overlap, then champion-role
  baseline data when sample sizes allow it.
- Falls back to the newest useful earlier patch within the same season when the
  current patch has too little data.
- Detects the live champion, role, enemy team, and lane opponent from the local
  League Live Client Data API.
- Provides a command-line live assistant and a basic Tkinter dashboard.

## Application workflow

The personal tracker and build recommender intentionally use separate SQLite
databases:

```text
Riot Match-V5 + timelines
            |
            v
    build_collector.py -----> data/builds.db
                                    |
Data Dragon metadata                v
    build_static_data.py ----> build_helper.py
                                    ^
                                    |
League Live Client --------> live_build_assistant.py
                                    |
                                    v
                              tracker_gui.py

Riot match statistics ------> data/tracker.db ------> stats.py
```

`data/tracker.db` is for the selected player's personal statistics.
`data/builds.db` is the larger learning dataset used by the recommender and can
contain build evidence from every participant in collected matches.

## File purposes

### Main application

- `main.py` is the normal application entry point. Running it launches the
  Tkinter dashboard.
- `tracker_gui.py` contains the Tkinter interface. It displays personal stats,
  runs live build detection, collects matches, and displays build-database
  coverage while network work runs in background threads.

### Personal stat tracker

- `riot_api.py` contains the original Riot account, summoner, rank, match, and
  spectator API request functions used by the personal tracker and remote live
  fallback.
- `database.py` creates and accesses `data/tracker.db`, which stores personal
  match results such as champion, K/D/A, win, duration, date, and role.
- `stats.py` calculates win rate, average K/D/A, recent win rate, most-played
  champions, role performance, and champion-pool totals.

### Dynamic build system

- `build_static_data.py` downloads and caches Data Dragon champion/item data,
  resolves patch versions, builds name/ID maps, and identifies valid completed
  items and boots. This removes the need for hardcoded role item pools.
- `build_database.py` owns the separate `data/builds.db` schema and queries for
  matches, participants, final item slots, item timeline events, and team bans.
- `build_collector.py` calls Riot Match-V5 for completed matches and timelines,
  assigns lane opponents by role, normalizes the response, and saves one atomic
  match bundle to the build database.
- `build_helper.py` is the recommendation engine. It reconstructs first-shop
  starting items and completed builds, aggregates observed results, applies
  patch fallbacks, and chooses between lane-opponent, enemy-team, and baseline
  evidence.
- `live_build_assistant.py` connects the current live game to the recommendation
  engine. It automatically detects local participants when League is running
  and also provides the standalone command-line assistant.

### Configuration and sample data

- `config.py` loads the Riot API key and region settings from `.env`.
- `sample_live_game.json` is a sample spectator payload used for development and
  manual testing.

## Languages, tools, frameworks, and skills

### Languages and data formats

- **Python** is the main programming language for the API clients, data
  collector, databases, recommendation engine, command-line tools, and GUI.
- **SQL** is used through SQLite to create tables, indexes, relationships, and
  queries for personal statistics and build evidence.
- **JSON** is used for Riot API responses, Data Dragon metadata, cached static
  data, sample live-game data, and collector output.

### Frameworks and Python libraries

- **Tkinter and ttk** provide the desktop interface, tabs, forms, buttons,
  status messages, and scrollable result panels.
- **Requests** handles Riot API, Data Dragon, and local League Live Client HTTP
  requests.
- **urllib3** is used to handle the local Live Client's self-signed HTTPS
  certificate warning.
- **python-dotenv** loads the Riot API key from the local `.env` file.
- **sqlite3** provides the two local databases without requiring a separate
  database server.
- **threading** keeps network collection and live-game detection from freezing
  the Tkinter window.
- **argparse** provides command-line interfaces for match collection and live
  recommendations.
- Standard-library modules including **pathlib**, **collections**, **json**,
  **contextlib**, and **urllib.parse** support caching, aggregation,
  serialization, safe database handling, and URL construction.

### APIs and game-data services

- **Riot Account-V1** resolves a Riot name and tag to a PUUID.
- **Summoner-V4 and League-V4** provide account and ranked information for the
  personal tracker.
- **Match-V5** supplies completed matches and detailed item-event timelines.
- **Spectator-V5** provides the remote active-game fallback.
- **League Live Client Data API** detects the current local game, participants,
  teams, champions, positions, and lane opponent.
- **Data Dragon** provides patch-aware champion and item names, IDs, tags,
  recipes, prices, and map availability.
