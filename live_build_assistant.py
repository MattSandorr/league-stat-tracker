"""Show a dynamic build recommendation for the user's current live game."""

from __future__ import annotations

import argparse
from typing import Any, Mapping

import requests
import urllib3

import build_helper
import build_static_data


LOCAL_PLAYER_LIST_URL = "https://127.0.0.1:2999/liveclientdata/playerlist"
LOCAL_REQUEST_TIMEOUT_SECONDS = 5
ROLE_ALIASES = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MID": "MIDDLE",
    "MIDDLE": "MIDDLE",
    "ADC": "BOTTOM",
    "BOT": "BOTTOM",
    "BOTTOM": "BOTTOM",
    "SUP": "UTILITY",
    "SUPPORT": "UTILITY",
    "UTILITY": "UTILITY",
}


class LiveBuildError(RuntimeError):
    """Represent invalid input or missing live-game information."""


def normalize_role(role: str) -> str:
    normalized_role = ROLE_ALIASES.get(role.strip().upper())
    if normalized_role is None:
        valid_roles = ", ".join(sorted(ROLE_ALIASES))
        raise LiveBuildError(f"Unknown role '{role}'. Use one of: {valid_roles}")
    return normalized_role


def get_account_puuid(name: str, tag: str) -> str:
    import riot_api

    account = riot_api.get_puuid_riot_id(name, tag)
    if not account or not account.get("puuid"):
        raise LiveBuildError(f"Could not find Riot account {name}#{tag}")
    return str(account["puuid"])


def get_live_game(puuid: str) -> dict[str, Any]:
    import riot_api

    live_data = riot_api.get_live_stats(puuid)
    if not live_data:
        raise LiveBuildError("No active live game was found for this account")
    if not isinstance(live_data.get("participants"), list):
        raise LiveBuildError("The live-game response did not contain participants")
    return live_data


def get_local_players() -> list[dict[str, Any]] | None:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        response = requests.get(
            LOCAL_PLAYER_LIST_URL,
            verify=False,
            timeout=LOCAL_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        players = response.json()
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(players, list) or not players:
        return None
    return [dict(player) for player in players if isinstance(player, Mapping)]


def find_local_player(
    players: list[Mapping[str, Any]], name: str, tag: str
) -> Mapping[str, Any]:
    requested_name = name.strip().casefold()
    requested_tag = tag.strip().casefold()
    requested_riot_id = f"{name.strip()}#{tag.strip()}".casefold()
    for player in players:
        player_name = str(player.get("riotIdGameName") or "").casefold()
        player_tag = str(player.get("riotIdTagLine") or "").casefold()
        player_riot_id = str(player.get("riotId") or "").casefold()
        if (
            player_name == requested_name
            and player_tag == requested_tag
        ) or player_riot_id == requested_riot_id:
            return player
    raise LiveBuildError(f"Could not find {name}#{tag} in the local live game")


def find_my_participant(
    live_data: Mapping[str, Any], puuid: str
) -> Mapping[str, Any]:
    for participant in live_data.get("participants", []):
        if participant.get("puuid") == puuid:
            return participant
    raise LiveBuildError("Your PUUID was not present in the live-game participants")


def get_enemy_champion_ids(
    live_data: Mapping[str, Any], my_team_id: int
) -> list[int]:
    enemy_ids = [
        int(participant["championId"])
        for participant in live_data.get("participants", [])
        if int(participant.get("teamId", 0)) != int(my_team_id)
        and int(participant.get("championId", 0)) > 0
    ]
    if not enemy_ids:
        raise LiveBuildError("No enemy champions were found in the live game")
    return enemy_ids


def load_champion_maps(
    version: str,
) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    champion_data = build_static_data.get_champion_data(version)
    return build_static_data.build_champion_maps(champion_data)


def resolve_lane_opponent(
    opponent_name: str | None,
    enemy_champion_ids: list[int],
    champions_by_id: Mapping[int, Mapping[str, Any]],
    champion_ids_by_name: Mapping[str, int],
) -> int | None:
    """Resolve and validate an optional lane-opponent champion name."""

    if not opponent_name:
        return None

    normalized_name = build_static_data.normalize_name(opponent_name)
    opponent_id = champion_ids_by_name.get(normalized_name)
    if opponent_id is None:
        raise LiveBuildError(f"Unknown lane-opponent champion '{opponent_name}'")
    if opponent_id not in enemy_champion_ids:
        enemy_names = [
            str(champions_by_id.get(champion_id, {}).get("name", champion_id))
            for champion_id in enemy_champion_ids
        ]
        raise LiveBuildError(
            f"{opponent_name} is not on the enemy team. "
            f"Current enemies: {', '.join(enemy_names)}"
        )
    return int(opponent_id)


def resolve_champion_id(
    champion_name: str,
    champion_ids_by_name: Mapping[str, int],
) -> int:
    champion_id = champion_ids_by_name.get(
        build_static_data.normalize_name(champion_name)
    )
    if champion_id is None:
        raise LiveBuildError(f"Unknown live champion '{champion_name}'")
    return int(champion_id)


def get_local_enemy_players(
    players: list[Mapping[str, Any]], my_team: str
) -> list[Mapping[str, Any]]:
    enemies = [
        player
        for player in players
        if str(player.get("team") or "")
        and str(player.get("team")) != str(my_team)
    ]
    if not enemies:
        raise LiveBuildError("No enemy champions were found in the local game")
    return enemies


def detect_lane_opponent_name(
    enemy_players: list[Mapping[str, Any]], role: str
) -> str | None:
    """Find the single enemy whose local position matches the user's role."""

    matching_enemies = [
        player
        for player in enemy_players
        if str(player.get("position") or "").upper() == role
    ]
    if len(matching_enemies) != 1:
        return None
    champion_name = matching_enemies[0].get("championName")
    return str(champion_name) if champion_name else None


def format_path(path_results: list[Mapping[str, Any]]) -> str:
    if not path_results:
        return "No reliable data"
    leading_path = path_results[0]
    names = " -> ".join(str(name) for name in leading_path["item_names"])
    game_label = "game" if leading_path["games"] == 1 else "games"
    return (
        f"{names} "
        f"({leading_path['games']} {game_label}, "
        f"{leading_path['win_rate']}% win rate)"
    )


def format_starting_items(loadout_results: list[Mapping[str, Any]]) -> str:
    if not loadout_results:
        return "No reliable data"
    loadout = loadout_results[0]
    names = ", ".join(str(name) for name in loadout["item_names"])
    game_label = "game" if loadout["games"] == 1 else "games"
    return (
        f"{names} ({loadout['games']} {game_label}, "
        f"{loadout['win_rate']}% win rate)"
    )


def format_full_build(full_build: Mapping[str, Any]) -> str:
    item_names = full_build.get("item_names", [])
    if not item_names:
        return "No reliable data"
    path = " -> ".join(str(name) for name in item_names)
    slot_samples = ", ".join(
        f"slot {slot['slot']}: {slot['games']}"
        for slot in full_build.get("slot_evidence", [])
    )
    return f"{path}\n  Evidence by slot: {slot_samples}"


def format_situational_items(item_results: list[Mapping[str, Any]]) -> str:
    if not item_results:
        return "No reliable data"
    return "\n".join(
        (
            f"  - {item['item_name']} "
            f"({item['games']} "
            f"{'game' if item['games'] == 1 else 'games'}, "
            f"{item['win_rate']}% win rate)"
        )
        for item in item_results
    )


def print_recommendation(result: Mapping[str, Any]) -> None:
    build = result["build"]
    print()
    print(f"{build['champion_name']} - {build['role']}")
    if result.get("live_role_source"):
        print(f"Role source: {result['live_role_source']}")
    if result.get("requested_lane_opponent_name"):
        print(f"Lane opponent: {result['requested_lane_opponent_name']}")
        if result.get("live_lane_opponent_source"):
            print(f"Lane opponent source: {result['live_lane_opponent_source']}")
    print(
        f"Patch: {result['requested_patch']} "
        f"(using {result['effective_patch']})"
    )
    print(f"Patch source: {result['patch_source']}")
    print(f"Recommendation source: {result['recommendation_source']}")
    print(f"Games analyzed: {build['games_analyzed']}")
    print()
    print(f"Starting items: {format_starting_items(build['starting_items'])}")
    print(f"Full build: {format_full_build(build['full_build'])}")
    print(f"Boots: {format_path(build['boots'])}")
    print("Situational items:")
    print(format_situational_items(build["situational_items"]))


def create_live_recommendation(
    name: str,
    tag: str,
    role: str | None = None,
    lane_opponent: str | None = None,
) -> dict[str, Any]:
    """Combine live-game, static, and collected data into one recommendation."""

    current_version = build_static_data.get_current_patch()
    champions_by_id, champion_ids_by_name = load_champion_maps(current_version)
    local_players = get_local_players()

    if local_players is not None:
        my_player = find_local_player(local_players, name, tag)
        detected_role = normalize_role(str(my_player.get("position") or ""))
        normalized_role = normalize_role(role) if role else detected_role
        role_source = "manual_override" if role else "local_live_client"
        my_champion_id = resolve_champion_id(
            str(my_player.get("championName") or ""),
            champion_ids_by_name,
        )
        my_team = str(my_player.get("team") or "")
        if not my_team:
            raise LiveBuildError("Your local participant record is missing its team")
        enemy_players = get_local_enemy_players(local_players, my_team)
        enemy_champion_ids = [
            resolve_champion_id(
                str(enemy.get("championName") or ""),
                champion_ids_by_name,
            )
            for enemy in enemy_players
        ]
        detected_lane_opponent = detect_lane_opponent_name(
            enemy_players,
            normalized_role,
        )
        selected_lane_opponent = lane_opponent or detected_lane_opponent
        lane_opponent_source = (
            "manual_override"
            if lane_opponent
            else "local_position" if detected_lane_opponent else None
        )
    else:
        if role is None:
            raise LiveBuildError(
                "Local role detection is unavailable; provide --role as a fallback"
            )
        normalized_role = normalize_role(role)
        role_source = "manual_remote_fallback"
        puuid = get_account_puuid(name, tag)
        live_data = get_live_game(puuid)
        my_participant = find_my_participant(live_data, puuid)
        my_champion_id = int(my_participant.get("championId", 0))
        my_team_id = int(my_participant.get("teamId", 0))
        if my_champion_id <= 0 or my_team_id <= 0:
            raise LiveBuildError(
                "Your live participant record is missing champion/team IDs"
            )
        enemy_champion_ids = get_enemy_champion_ids(live_data, my_team_id)
        selected_lane_opponent = lane_opponent
        lane_opponent_source = "manual_remote_fallback" if lane_opponent else None

    lane_opponent_id = resolve_lane_opponent(
        selected_lane_opponent,
        enemy_champion_ids,
        champions_by_id,
        champion_ids_by_name,
    )
    result = build_helper.recommend_build(
        my_champion_id,
        normalized_role,
        current_version,
        lane_opponent_champion_id=lane_opponent_id,
        enemy_team_champion_ids=enemy_champion_ids,
    )
    result["live_role_source"] = role_source
    result["live_lane_opponent_source"] = lane_opponent_source
    return result


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recommend a build for your current League live game"
    )
    parser.add_argument("--name", required=True, help="Riot game name")
    parser.add_argument("--tag", required=True, help="Riot tag without #")
    parser.add_argument(
        "--role",
        help=(
            "Optional override: TOP, JUNGLE, MIDDLE/MID, "
            "BOTTOM/ADC, or UTILITY/SUPPORT"
        ),
    )
    parser.add_argument(
        "--lane-opponent",
        help="Optional enemy champion name, such as Jinx",
    )
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    try:
        result = create_live_recommendation(
            args.name,
            args.tag,
            args.role,
            lane_opponent=args.lane_opponent,
        )
        print_recommendation(result)
        return 0
    except (
        LiveBuildError,
        build_static_data.StaticDataError,
        requests.RequestException,
    ) as exc:
        print(f"Live build assistant error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
