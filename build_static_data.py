"""Patch-aware access to League of Legends Data Dragon static data.

This module describes what champions and items exist on a patch. It does not
contain build recommendations or champion-specific item pools.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import requests


DATA_DRAGON_BASE_URL = "https://ddragon.leagueoflegends.com"
DEFAULT_CACHE_DIRECTORY = Path(__file__).resolve().parent / "data" / "static_cache"
DEFAULT_LOCALE = "en_US"
REQUEST_TIMEOUT_SECONDS = 10


class StaticDataError(RuntimeError):
    """Represent a network, cache, or response error from Data Dragon."""


def _request_json(url: str, session: requests.Session | None = None) -> dict[str, Any]:
    """Download one JSON object and turn request failures into a clear error."""

    requester = session or requests
    try:
        response = requester.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise StaticDataError(f"Could not load Data Dragon data from {url}: {exc}") from exc

    if not isinstance(data, dict):
        raise StaticDataError(f"Data Dragon returned an unexpected response from {url}")
    return data


def get_realm(region: str = "na", session: requests.Session | None = None) -> dict[str, Any]:
    normalized_region = region.lower()
    url = f"{DATA_DRAGON_BASE_URL}/realms/{normalized_region}.json"
    return _request_json(url, session=session)


def get_current_versions(
    region: str = "na", session: requests.Session | None = None
) -> dict[str, str]:
    realm = get_realm(region=region, session=session)
    component_versions = realm.get("n", {})
    try:
        return {
            "champion": str(component_versions["champion"]),
            "item": str(component_versions["item"]),
        }
    except KeyError as exc:
        raise StaticDataError("The regional realm did not include champion/item versions") from exc


def get_current_patch(region: str = "na", session: requests.Session | None = None) -> str:
    return get_current_versions(region=region, session=session)["champion"]


def get_available_versions(session: requests.Session | None = None) -> list[str]:
    url = f"{DATA_DRAGON_BASE_URL}/api/versions.json"
    requester = session or requests
    try:
        response = requester.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        versions = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise StaticDataError(f"Could not load Data Dragon versions: {exc}") from exc
    if not isinstance(versions, list) or not all(
        isinstance(version, str) for version in versions
    ):
        raise StaticDataError("Data Dragon returned an unexpected versions response")
    return versions


def resolve_data_dragon_version(
    patch: str,
    *,
    available_versions: list[str] | None = None,
    session: requests.Session | None = None,
) -> str:
    """Resolve a database patch family such as 16.16 to a full version."""

    versions = available_versions or get_available_versions(session=session)
    if patch in versions:
        return patch
    requested_family = patch_family(patch)
    for version in versions:
        if patch_family(version) == requested_family:
            return version
    raise StaticDataError(f"No Data Dragon version exists for patch {patch}")


def patch_family(version: str) -> str:
    """Reduce versions such as 16.16.1 and 16.16.702.1234 to major.minor."""

    pieces = str(version).split(".")
    if len(pieces) < 2:
        raise ValueError(f"Invalid League patch version: {version}")
    return ".".join(pieces[:2])


def _cache_path(
    data_type: str,
    version: str,
    locale: str,
    cache_directory: Path,
) -> Path:
    return cache_directory / version / locale / f"{data_type}.json"


def _read_cached_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as cache_file:
            data = json.load(cache_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise StaticDataError(f"Could not read static-data cache {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise StaticDataError(f"Static-data cache does not contain a JSON object: {path}")
    return data


def _write_cached_json(path: Path, data: Mapping[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as cache_file:
            json.dump(data, cache_file, ensure_ascii=False)
    except OSError as exc:
        raise StaticDataError(f"Could not write static-data cache {path}: {exc}") from exc


def _get_versioned_data(
    data_type: str,
    version: str,
    locale: str,
    cache_directory: Path,
    force_refresh: bool,
    session: requests.Session | None,
) -> dict[str, Any]:
    cache_path = _cache_path(data_type, version, locale, cache_directory)
    if not force_refresh:
        cached_data = _read_cached_json(cache_path)
        if cached_data is not None:
            return cached_data

    url = (
        f"{DATA_DRAGON_BASE_URL}/cdn/{version}/data/{locale}/{data_type}.json"
    )
    data = _request_json(url, session=session)
    if not isinstance(data.get("data"), dict):
        raise StaticDataError(f"Data Dragon {data_type} data is missing its data object")
    _write_cached_json(cache_path, data)
    return data


def get_champion_data(
    version: str | None = None,
    *,
    region: str = "na",
    locale: str = DEFAULT_LOCALE,
    cache_directory: Path = DEFAULT_CACHE_DIRECTORY,
    force_refresh: bool = False,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    selected_version = version or get_current_versions(region, session)["champion"]
    return _get_versioned_data(
        "champion",
        selected_version,
        locale,
        Path(cache_directory),
        force_refresh,
        session,
    )


def get_item_data(
    version: str | None = None,
    *,
    region: str = "na",
    locale: str = DEFAULT_LOCALE,
    cache_directory: Path = DEFAULT_CACHE_DIRECTORY,
    force_refresh: bool = False,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    selected_version = version or get_current_versions(region, session)["item"]
    return _get_versioned_data(
        "item",
        selected_version,
        locale,
        Path(cache_directory),
        force_refresh,
        session,
    )


def normalize_name(name: str) -> str:
    return "".join(character for character in name.casefold() if character.isalnum())


def build_champion_maps(
    champion_data: Mapping[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    champions_by_id: dict[int, dict[str, Any]] = {}
    champion_ids_by_name: dict[str, int] = {}
    for champion in champion_data["data"].values():
        champion_id = int(champion["key"])
        champion_record = dict(champion)
        champions_by_id[champion_id] = champion_record
        champion_ids_by_name[normalize_name(str(champion["name"]))] = champion_id
        champion_ids_by_name[normalize_name(str(champion["id"]))] = champion_id
    return champions_by_id, champion_ids_by_name


def build_item_maps(
    item_data: Mapping[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[str, list[int]]]:
    items_by_id: dict[int, dict[str, Any]] = {}
    item_ids_by_name: dict[str, list[int]] = {}
    for raw_item_id, item in item_data["data"].items():
        item_id = int(raw_item_id)
        item_record = dict(item)
        items_by_id[item_id] = item_record
        normalized_name = normalize_name(str(item["name"]))
        item_ids_by_name.setdefault(normalized_name, []).append(item_id)
    return items_by_id, item_ids_by_name


def is_summoners_rift_item(item: Mapping[str, Any]) -> bool:
    maps = item.get("maps", {})
    available_on_map = bool(maps.get("11", maps.get(11, False)))
    purchasable = bool(item.get("gold", {}).get("purchasable", False))
    in_store = bool(item.get("inStore", True))
    return available_on_map and purchasable and in_store


def get_summoners_rift_items(
    item_data: Mapping[str, Any],
) -> dict[int, dict[str, Any]]:
    items_by_id, _ = build_item_maps(item_data)
    return {
        item_id: item
        for item_id, item in items_by_id.items()
        if is_summoners_rift_item(item)
    }


def is_boot_item(
    item_id: int,
    items_by_id: Mapping[int, Mapping[str, Any]],
) -> bool:
    """Identify boots from Data Dragon tags or their component ancestry."""

    pending_item_ids = [int(item_id)]
    visited_item_ids: set[int] = set()
    while pending_item_ids:
        current_item_id = pending_item_ids.pop()
        if current_item_id in visited_item_ids:
            continue
        visited_item_ids.add(current_item_id)

        item = items_by_id.get(current_item_id, {})
        if "Boots" in item.get("tags", []):
            return True

        for component_id in item.get("from", []):
            try:
                pending_item_ids.append(int(component_id))
            except (TypeError, ValueError):
                continue
    return False


def is_completed_item(item: Mapping[str, Any], minimum_total_gold: int = 1000) -> bool:
    """Identify likely completed gear without maintaining champion item pools."""

    maps = item.get("maps", {})
    if not bool(maps.get("11", maps.get(11, False))):
        return False
    if item.get("into"):
        return False
    tags = {str(tag) for tag in item.get("tags", [])}
    if tags.intersection({"Consumable", "Trinket"}):
        return False
    total_gold = int(item.get("gold", {}).get("total", 0))
    depth = int(item.get("depth", 0) or 0)
    return total_gold >= minimum_total_gold or depth >= 2


def get_completed_items(
    item_data: Mapping[str, Any], minimum_total_gold: int = 1000
) -> dict[int, dict[str, Any]]:
    items_by_id, _ = build_item_maps(item_data)
    return {
        item_id: item
        for item_id, item in items_by_id.items()
        if is_completed_item(item, minimum_total_gold=minimum_total_gold)
    }
