"""Collect Match-V5 build evidence without changing the existing stat tracker.

The collector downloads completed matches and timelines, normalizes their build
data, and hands one atomic bundle to build_database.py.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

import requests

import build_database
import build_static_data
import config


REQUEST_TIMEOUT_SECONDS = 10
ITEM_EVENT_TYPES = frozenset(
    {"ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO", "ITEM_DESTROYED"}
)
VALID_ROLES = frozenset({"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"})


class CollectorError(RuntimeError):
    """Represent an invalid configuration or Riot Match-V5 request failure."""


class RiotMatchClient:
    """Provide only the Match-V5 endpoints required by the build collector."""

    def __init__(
        self,
        api_key: str | None = None,
        regional_route: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key or config.API_KEY
        self.regional_route = regional_route or config.REGIONAL_ROUTE
        self.session = session or requests.Session()
        if not self.api_key:
            raise CollectorError("RIOT_API_KEY is missing. Add it to your .env file.")

    def _get_json(
        self, endpoint: str, params: Mapping[str, Any] | None = None
    ) -> Any:
        """Request one Match-V5 endpoint and report rate limits and API errors."""

        url = f"https://{self.regional_route}.api.riotgames.com{endpoint}"
        try:
            response = self.session.get(
                url,
                headers={"X-Riot-Token": self.api_key},
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise CollectorError(f"Could not reach Riot Match-V5: {exc}") from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            raise CollectorError(f"Riot rate limit reached; retry after {retry_after} seconds")
        if not response.ok:
            raise CollectorError(
                f"Riot Match-V5 returned HTTP {response.status_code}: {response.text}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise CollectorError("Riot Match-V5 returned invalid JSON") from exc

    def get_match_ids(
        self,
        puuid: str,
        *,
        count: int = 20,
        start: int = 0,
        queue_id: int | None = 420,
        match_type: str | None = "ranked",
    ) -> list[str]:
        if not 1 <= count <= 100:
            raise ValueError("count must be between 1 and 100")
        if start < 0:
            raise ValueError("start cannot be negative")

        params: dict[str, Any] = {"start": start, "count": count}
        if queue_id is not None:
            params["queue"] = queue_id
        if match_type is not None:
            params["type"] = match_type
        endpoint = (
            "/lol/match/v5/matches/by-puuid/"
            f"{quote(puuid, safe='')}/ids"
        )
        data = self._get_json(endpoint, params=params)
        if not isinstance(data, list):
            raise CollectorError("Match-ID endpoint returned an unexpected response")
        return [str(match_id) for match_id in data]

    def get_match(self, match_id: str) -> dict[str, Any]:
        endpoint = f"/lol/match/v5/matches/{quote(match_id, safe='')}"
        data = self._get_json(endpoint)
        if not isinstance(data, dict):
            raise CollectorError("Match endpoint returned an unexpected response")
        return data

    def get_timeline(self, match_id: str) -> dict[str, Any]:
        endpoint = f"/lol/match/v5/matches/{quote(match_id, safe='')}/timeline"
        data = self._get_json(endpoint)
        if not isinstance(data, dict):
            raise CollectorError("Timeline endpoint returned an unexpected response")
        return data


def normalize_role(participant: Mapping[str, Any]) -> str:
    team_position = str(participant.get("teamPosition") or "").upper()
    individual_position = str(participant.get("individualPosition") or "").upper()
    if team_position in VALID_ROLES:
        return team_position
    if individual_position in VALID_ROLES:
        return individual_position
    return "UNKNOWN"


def get_match_patch(match: Mapping[str, Any]) -> str:
    game_version = str(match.get("info", {}).get("gameVersion", ""))
    return build_static_data.patch_family(game_version)


def _assign_lane_opponents(participants: list[dict[str, Any]]) -> None:
    """Attach the opposing champion with the same unique role when available."""

    participants_by_team_role: dict[tuple[int, str], list[dict[str, Any]]] = {}
    team_ids = {int(participant["team_id"]) for participant in participants}
    for participant in participants:
        key = (int(participant["team_id"]), str(participant["role"]))
        participants_by_team_role.setdefault(key, []).append(participant)

    for participant in participants:
        participant["lane_opponent_champion_id"] = None
        role = str(participant["role"])
        if role == "UNKNOWN":
            continue
        opposing_team_ids = team_ids - {int(participant["team_id"])}
        opponents = [
            opponent
            for opposing_team_id in opposing_team_ids
            for opponent in participants_by_team_role.get((opposing_team_id, role), [])
        ]
        if len(opponents) == 1:
            participant["lane_opponent_champion_id"] = opponents[0]["champion_id"]


def _extract_participants(
    match_id: str, match_info: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    participants: list[dict[str, Any]] = []
    final_items: list[dict[str, Any]] = []
    for participant in match_info.get("participants", []):
        participant_id = int(participant["participantId"])
        participants.append(
            {
                "match_id": match_id,
                "participant_id": participant_id,
                "puuid": participant.get("puuid"),
                "champion_id": int(participant["championId"]),
                "role": normalize_role(participant),
                "team_id": int(participant["teamId"]),
                "win": bool(participant["win"]),
                "physical_damage_to_champions": int(
                    participant.get("physicalDamageDealtToChampions", 0)
                ),
                "magic_damage_to_champions": int(
                    participant.get("magicDamageDealtToChampions", 0)
                ),
                "true_damage_to_champions": int(
                    participant.get("trueDamageDealtToChampions", 0)
                ),
            }
        )

        for slot in range(7):
            item_id = int(participant.get(f"item{slot}", 0) or 0)
            if item_id:
                final_items.append(
                    {
                        "match_id": match_id,
                        "participant_id": participant_id,
                        "slot": slot,
                        "item_id": item_id,
                    }
                )

    _assign_lane_opponents(participants)
    return participants, final_items


def _extract_item_events(match_id: str, timeline: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize purchases, sales, undos, and destroyed-item timeline events."""

    item_events: list[dict[str, Any]] = []
    participant_sequences: Counter[int] = Counter()
    frames = timeline.get("info", {}).get("frames", [])
    for frame in frames:
        for event in frame.get("events", []):
            event_type = str(event.get("type", ""))
            if event_type not in ITEM_EVENT_TYPES or "participantId" not in event:
                continue
            participant_id = int(event["participantId"])
            sequence_number = participant_sequences[participant_id]
            participant_sequences[participant_id] += 1
            primary_item_id = event.get("itemId", event.get("beforeId"))
            related_item_id = event.get("afterId")
            item_events.append(
                {
                    "match_id": match_id,
                    "participant_id": participant_id,
                    "sequence_number": sequence_number,
                    "timestamp_ms": int(event.get("timestamp", frame.get("timestamp", 0))),
                    "event_type": event_type,
                    "item_id": int(primary_item_id) if primary_item_id else None,
                    "related_item_id": int(related_item_id) if related_item_id else None,
                }
            )
    return item_events


def _extract_bans(match_id: str, match_info: Mapping[str, Any]) -> list[dict[str, Any]]:
    bans: list[dict[str, Any]] = []
    for team in match_info.get("teams", []):
        team_id = int(team["teamId"])
        for ban in team.get("bans", []):
            champion_id = int(ban.get("championId", -1))
            if champion_id <= 0:
                continue
            bans.append(
                {
                    "match_id": match_id,
                    "team_id": team_id,
                    "pick_turn": int(ban.get("pickTurn", 0)),
                    "champion_id": champion_id,
                }
            )
    return bans


def extract_match_bundle(
    match: Mapping[str, Any], timeline: Mapping[str, Any]
) -> dict[str, Any]:
    """Convert raw Match-V5 match and timeline responses into database records."""

    metadata = match.get("metadata", {})
    match_info = match.get("info", {})
    match_id = str(metadata.get("matchId", ""))
    if not match_id:
        raise ValueError("Match response is missing metadata.matchId")
    if not match_info.get("participants"):
        raise ValueError(f"Match {match_id} does not contain participants")

    game_version = str(match_info.get("gameVersion", ""))
    participants, final_items = _extract_participants(match_id, match_info)
    valid_participant_ids = {
        int(participant["participant_id"]) for participant in participants
    }
    item_events = [
        event
        for event in _extract_item_events(match_id, timeline)
        if int(event["participant_id"]) in valid_participant_ids
    ]
    return {
        "match": {
            "match_id": match_id,
            "patch": build_static_data.patch_family(game_version),
            "game_version": game_version,
            "queue_id": int(match_info.get("queueId", 0)),
            "game_duration": int(match_info.get("gameDuration", 0)),
            "game_creation": int(match_info.get("gameCreation", 0)),
        },
        "participants": participants,
        "final_items": final_items,
        "item_events": item_events,
        "bans": _extract_bans(match_id, match_info),
    }


def collect_matches_for_puuid(
    puuid: str,
    *,
    client: RiotMatchClient | None = None,
    db_path: Path | str = build_database.DEFAULT_BUILD_DB_PATH,
    count: int = 20,
    start: int = 0,
    queue_id: int | None = 420,
    target_patch: str | None = None,
    current_patch_only: bool = True,
) -> dict[str, Any]:
    """Collect one page of matches for a PUUID and return progress statistics."""

    selected_client = client or RiotMatchClient()
    build_database.init_build_db(db_path)
    selected_patch = target_patch
    if current_patch_only and selected_patch is None:
        selected_patch = build_static_data.get_current_patch()
    target_patch_family = (
        build_static_data.patch_family(selected_patch) if selected_patch else None
    )

    match_ids = selected_client.get_match_ids(
        puuid,
        count=count,
        start=start,
        queue_id=queue_id,
    )
    summary: dict[str, Any] = {
        "requested": len(match_ids),
        "collected": 0,
        "already_saved": 0,
        "skipped_patch": 0,
        "failed": 0,
        "errors": [],
    }

    for match_id in match_ids:
        if build_database.match_exists(match_id, db_path=db_path):
            summary["already_saved"] += 1
            continue
        try:
            match = selected_client.get_match(match_id)
            if target_patch_family and get_match_patch(match) != target_patch_family:
                summary["skipped_patch"] += 1
                continue
            timeline = selected_client.get_timeline(match_id)
            bundle = extract_match_bundle(match, timeline)
            if build_database.save_match_bundle(bundle, db_path=db_path):
                summary["collected"] += 1
            else:
                summary["already_saved"] += 1
        except (CollectorError, KeyError, TypeError, ValueError) as exc:
            summary["failed"] += 1
            summary["errors"].append({"match_id": match_id, "error": str(exc)})
    return summary


def collect_matches_for_puuids(
    puuids: Iterable[str],
    **collection_options: Any,
) -> dict[str, Any]:
    options = dict(collection_options)
    client = options.pop("client", None) or RiotMatchClient()
    results: dict[str, Any] = {}
    for puuid in dict.fromkeys(puuids):
        results[puuid] = collect_matches_for_puuid(
            puuid,
            client=client,
            **options,
        )
    return results


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Match-V5 build evidence")
    parser.add_argument("--puuid", action="append", required=True, help="PUUID to collect")
    parser.add_argument("--count", type=int, default=20, help="Matches per PUUID")
    parser.add_argument("--start", type=int, default=0, help="Match-list offset")
    parser.add_argument("--queue", type=int, default=420, help="Riot queue ID")
    parser.add_argument(
        "--include-old-patches",
        action="store_true",
        help="Collect returned matches even when they are not on the current patch",
    )
    return parser


def main() -> None:
    args = _build_argument_parser().parse_args()
    result = collect_matches_for_puuids(
        args.puuid,
        count=args.count,
        start=args.start,
        queue_id=args.queue,
        current_patch_only=not args.include_old_patches,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
