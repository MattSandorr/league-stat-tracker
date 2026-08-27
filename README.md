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
- `.gitignore` prevents local secrets, databases, caches, and generated Python
  files from being committed.

## Setup

Use Python 3.10 or newer and install the external dependencies:

```powershell
pip install requests python-dotenv
```

Create a `.env` file in the project folder:

```dotenv
RIOT_API_KEY=your_riot_development_api_key
```

Tkinter is included with the standard Windows Python installation.

## Run the GUI

```powershell
python main.py
```

The dashboard has three tabs:

- **Personal Stats** reads the matches currently stored in `data/tracker.db`.
- **Live Build** detects the active League game and creates a recommendation.
- **Build Data** collects matches and shows the current `data/builds.db`
  coverage.

## Collect build data from the command line

Look up a PUUID:

```powershell
python -c "import riot_api; print(riot_api.get_puuid_riot_id('NAME', 'TAG')['puuid'])"
```

Collect up to 20 current-patch ranked matches:

```powershell
python build_collector.py --puuid "YOUR_PUUID" --count 20
```

Include older patches when building a broader initial dataset:

```powershell
python build_collector.py --puuid "YOUR_PUUID" --count 20 --include-old-patches
```

## Run the live assistant from the command line

With League running and a game in progress:

```powershell
python live_build_assistant.py --name "NAME" --tag "TAG"
```

Role and lane-opponent arguments are optional overrides because the local Live
Client Data API normally detects them automatically.
