"""SQLite persistence for build-learning data.

The build database is intentionally separate from data/tracker.db so collection
and schema changes cannot break the existing personal stat tracker.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping


DEFAULT_BUILD_DB_PATH = Path(__file__).resolve().parent / "data" / "builds.db"


def connect(db_path: Path | str = DEFAULT_BUILD_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_build_db(db_path: Path | str = DEFAULT_BUILD_DB_PATH) -> None:
    """Create all build-collection tables and indexes when they do not exist."""

    with closing(connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS build_matches (
                match_id TEXT PRIMARY KEY,
                patch TEXT NOT NULL,
                game_version TEXT NOT NULL,
                queue_id INTEGER NOT NULL,
                game_duration INTEGER NOT NULL,
                game_creation INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS build_participants (
                match_id TEXT NOT NULL,
                participant_id INTEGER NOT NULL,
                puuid TEXT,
                champion_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                team_id INTEGER NOT NULL,
                win INTEGER NOT NULL CHECK (win IN (0, 1)),
                physical_damage_to_champions INTEGER NOT NULL,
                magic_damage_to_champions INTEGER NOT NULL,
                true_damage_to_champions INTEGER NOT NULL,
                lane_opponent_champion_id INTEGER,
                PRIMARY KEY (match_id, participant_id),
                FOREIGN KEY (match_id) REFERENCES build_matches(match_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS final_items (
                match_id TEXT NOT NULL,
                participant_id INTEGER NOT NULL,
                slot INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                PRIMARY KEY (match_id, participant_id, slot),
                FOREIGN KEY (match_id, participant_id)
                    REFERENCES build_participants(match_id, participant_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS item_events (
                match_id TEXT NOT NULL,
                participant_id INTEGER NOT NULL,
                sequence_number INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                item_id INTEGER,
                related_item_id INTEGER,
                PRIMARY KEY (match_id, participant_id, sequence_number),
                FOREIGN KEY (match_id, participant_id)
                    REFERENCES build_participants(match_id, participant_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS team_bans (
                match_id TEXT NOT NULL,
                team_id INTEGER NOT NULL,
                pick_turn INTEGER NOT NULL,
                champion_id INTEGER NOT NULL,
                PRIMARY KEY (match_id, team_id, pick_turn),
                FOREIGN KEY (match_id) REFERENCES build_matches(match_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_participant_champion_role_patch
                ON build_participants(champion_id, role, match_id);
            CREATE INDEX IF NOT EXISTS idx_participant_lane_opponent
                ON build_participants(champion_id, role, lane_opponent_champion_id);
            CREATE INDEX IF NOT EXISTS idx_item_events_item
                ON item_events(item_id, event_type);
            """
        )
        connection.commit()


def match_exists(match_id: str, db_path: Path | str = DEFAULT_BUILD_DB_PATH) -> bool:
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            "SELECT 1 FROM build_matches WHERE match_id = ?",
            (match_id,),
        ).fetchone()
    return row is not None


def _required(record: Mapping[str, Any], field_names: Iterable[str], record_name: str) -> None:
    missing = [field_name for field_name in field_names if field_name not in record]
    if missing:
        raise ValueError(f"{record_name} is missing required fields: {', '.join(missing)}")


def save_match_bundle(
    bundle: Mapping[str, Any],
    db_path: Path | str = DEFAULT_BUILD_DB_PATH,
) -> bool:
    """Save one normalized match and all related rows in a single transaction."""

    match = bundle.get("match", {})
    _required(
        match,
        ("match_id", "patch", "game_version", "queue_id", "game_duration", "game_creation"),
        "match",
    )
    init_build_db(db_path)

    with closing(connect(db_path)) as connection, connection:
        already_saved = connection.execute(
            "SELECT 1 FROM build_matches WHERE match_id = ?",
            (match["match_id"],),
        ).fetchone()
        if already_saved:
            return False

        connection.execute(
            """
            INSERT INTO build_matches (
                match_id, patch, game_version, queue_id, game_duration, game_creation
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                match["match_id"],
                match["patch"],
                match["game_version"],
                match["queue_id"],
                match["game_duration"],
                match["game_creation"],
            ),
        )

        participant_rows = [
            (
                participant["match_id"],
                participant["participant_id"],
                participant.get("puuid"),
                participant["champion_id"],
                participant["role"],
                participant["team_id"],
                int(bool(participant["win"])),
                participant["physical_damage_to_champions"],
                participant["magic_damage_to_champions"],
                participant["true_damage_to_champions"],
                participant.get("lane_opponent_champion_id"),
            )
            for participant in bundle.get("participants", [])
        ]
        connection.executemany(
            """
            INSERT INTO build_participants (
                match_id, participant_id, puuid, champion_id, role, team_id, win,
                physical_damage_to_champions, magic_damage_to_champions,
                true_damage_to_champions, lane_opponent_champion_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            participant_rows,
        )

        final_item_rows = [
            (
                item["match_id"],
                item["participant_id"],
                item["slot"],
                item["item_id"],
            )
            for item in bundle.get("final_items", [])
        ]
        connection.executemany(
            """
            INSERT INTO final_items (match_id, participant_id, slot, item_id)
            VALUES (?, ?, ?, ?)
            """,
            final_item_rows,
        )

        event_rows = [
            (
                event["match_id"],
                event["participant_id"],
                event["sequence_number"],
                event["timestamp_ms"],
                event["event_type"],
                event.get("item_id"),
                event.get("related_item_id"),
            )
            for event in bundle.get("item_events", [])
        ]
        connection.executemany(
            """
            INSERT INTO item_events (
                match_id, participant_id, sequence_number, timestamp_ms,
                event_type, item_id, related_item_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            event_rows,
        )

        ban_rows = [
            (
                ban["match_id"],
                ban["team_id"],
                ban["pick_turn"],
                ban["champion_id"],
            )
            for ban in bundle.get("bans", [])
        ]
        connection.executemany(
            """
            INSERT INTO team_bans (match_id, team_id, pick_turn, champion_id)
            VALUES (?, ?, ?, ?)
            """,
            ban_rows,
        )
    return True


def get_collection_counts(
    db_path: Path | str = DEFAULT_BUILD_DB_PATH,
) -> dict[str, int]:
    init_build_db(db_path)
    table_names = (
        "build_matches",
        "build_participants",
        "final_items",
        "item_events",
        "team_bans",
    )
    with closing(connect(db_path)) as connection:
        return {
            table_name: int(
                connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            )
            for table_name in table_names
        }


def get_champion_role_patch_counts(
    champion_id: int,
    role: str,
    db_path: Path | str = DEFAULT_BUILD_DB_PATH,
) -> list[dict[str, Any]]:
    init_build_db(db_path)
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT m.patch, COUNT(*) AS games
            FROM build_participants AS p
            JOIN build_matches AS m ON m.match_id = p.match_id
            WHERE p.champion_id = ? AND p.role = ?
            GROUP BY m.patch
            """,
            (champion_id, role.upper()),
        ).fetchall()

    results = [
        {"patch": str(row["patch"]), "games": int(row["games"])}
        for row in rows
    ]
    results.sort(
        key=lambda result: tuple(
            int(piece) for piece in result["patch"].split(".")
        ),
        reverse=True,
    )
    return results


def get_champion_role_games(
    champion_id: int,
    role: str,
    patch: str,
    *,
    lane_opponent_champion_id: int | None = None,
    db_path: Path | str = DEFAULT_BUILD_DB_PATH,
) -> list[dict[str, Any]]:
    init_build_db(db_path)
    parameters: list[Any] = [champion_id, role.upper(), patch]
    lane_filter = ""
    if lane_opponent_champion_id is not None:
        lane_filter = "AND p.lane_opponent_champion_id = ?"
        parameters.append(lane_opponent_champion_id)

    query = f"""
        SELECT p.*, m.patch, m.game_version, m.queue_id,
               m.game_duration, m.game_creation
        FROM build_participants AS p
        JOIN build_matches AS m ON m.match_id = p.match_id
        WHERE p.champion_id = ? AND p.role = ? AND m.patch = ?
        {lane_filter}
        ORDER BY m.game_creation DESC
    """
    with closing(connect(db_path)) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_final_items(
    match_id: str,
    participant_id: int,
    db_path: Path | str = DEFAULT_BUILD_DB_PATH,
) -> list[int]:
    init_build_db(db_path)
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT item_id FROM final_items
            WHERE match_id = ? AND participant_id = ?
            ORDER BY slot
            """,
            (match_id, participant_id),
        ).fetchall()
    return [int(row["item_id"]) for row in rows]


def get_item_events(
    match_id: str,
    participant_id: int,
    db_path: Path | str = DEFAULT_BUILD_DB_PATH,
) -> list[dict[str, Any]]:
    init_build_db(db_path)
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT sequence_number, timestamp_ms, event_type, item_id, related_item_id
            FROM item_events
            WHERE match_id = ? AND participant_id = ?
            ORDER BY sequence_number
            """,
            (match_id, participant_id),
        ).fetchall()
    return [dict(row) for row in rows]


def get_build_samples(
    champion_id: int,
    role: str,
    patch: str,
    *,
    lane_opponent_champion_id: int | None = None,
    db_path: Path | str = DEFAULT_BUILD_DB_PATH,
) -> list[dict[str, Any]]:
    """Return participant results, final items, and item events as build samples."""

    games = get_champion_role_games(
        champion_id,
        role,
        patch,
        lane_opponent_champion_id=lane_opponent_champion_id,
        db_path=db_path,
    )
    samples: list[dict[str, Any]] = []
    with closing(connect(db_path)) as connection:
        for game in games:
            match_id = str(game["match_id"])
            participant_id = int(game["participant_id"])
            final_item_rows = connection.execute(
                """
                SELECT slot, item_id
                FROM final_items
                WHERE match_id = ? AND participant_id = ?
                ORDER BY slot
                """,
                (match_id, participant_id),
            ).fetchall()
            event_rows = connection.execute(
                """
                SELECT sequence_number, timestamp_ms, event_type,
                       item_id, related_item_id
                FROM item_events
                WHERE match_id = ? AND participant_id = ?
                ORDER BY sequence_number
                """,
                (match_id, participant_id),
            ).fetchall()
            enemy_rows = connection.execute(
                """
                SELECT champion_id
                FROM build_participants
                WHERE match_id = ? AND team_id != ?
                ORDER BY participant_id
                """,
                (match_id, int(game["team_id"])),
            ).fetchall()

            sample = dict(game)
            sample["final_items"] = [
                {"slot": int(row["slot"]), "item_id": int(row["item_id"])}
                for row in final_item_rows
            ]
            sample["item_events"] = [dict(row) for row in event_rows]
            sample["enemy_team_champion_ids"] = [
                int(row["champion_id"]) for row in enemy_rows
            ]
            samples.append(sample)
    return samples
