from collections import Counter, defaultdict
from pathlib import Path

import build_database
import build_static_data


STARTING_SHOPPING_GAP_MS = 45_000
MAX_FULL_BUILD_ITEMS = 6


def get_enemy_team(live_data, my_puuid):
   my_team_id = None
   for participant in live_data["participants"]:
      if participant["puuid"] == my_puuid:
         my_team_id = participant["teamId"]
         break
   if my_team_id is None:
      raise ValueError("Player PUUID was not found in the live game")
   return [
      participant["championId"]
      for participant in live_data["participants"]
      if participant["teamId"] != my_team_id
   ]


def get_latest_version():
   return build_static_data.get_current_patch()


def get_champion_data(version):
   return build_static_data.get_champion_data(version)


def build_champion_id_map(champ_data):
   champions_by_id, _ = build_static_data.build_champion_maps(champ_data)
   return champions_by_id


def reconstruct_starting_items(
   sample,
   items_by_id,
   shopping_gap_ms=STARTING_SHOPPING_GAP_MS
):
   """Reconstruct paid items from the participant's first shopping session."""

   starting_item_ids = []
   session_started = False
   last_shop_timestamp = None
   item_events = sorted(
      sample.get("item_events", []),
      key=lambda event: (
         int(event.get("timestamp_ms", 0)),
         int(event.get("sequence_number", 0))
      )
   )
   for event in item_events:
      item_id = event.get("item_id")
      if item_id is None:
         continue
      item_id = int(item_id)
      item = items_by_id.get(item_id)
      if item is None:
         continue

      event_type = event.get("event_type")
      if event_type not in {"ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO"}:
         continue

      timestamp_ms = int(event.get("timestamp_ms", 0))
      if (
         session_started
         and last_shop_timestamp is not None
         and timestamp_ms - last_shop_timestamp > shopping_gap_ms
      ):
         break

      if event_type == "ITEM_PURCHASED":
         tags = {str(tag) for tag in item.get("tags", [])}
         total_gold = int(item.get("gold", {}).get("total", 0))
         maps = item.get("maps", {})
         is_summoners_rift_item = bool(maps.get("11", maps.get(11, False)))
         if "Trinket" not in tags and total_gold > 0 and is_summoners_rift_item:
            session_started = True
            last_shop_timestamp = timestamp_ms
            starting_item_ids.append(item_id)
      elif session_started:
         last_shop_timestamp = timestamp_ms
         for index in range(len(starting_item_ids) - 1, -1, -1):
            if starting_item_ids[index] == item_id:
               starting_item_ids.pop(index)
               break

   starting_item_ids.sort(
      key=lambda item_id: (
         -int(items_by_id[item_id].get("gold", {}).get("total", 0)),
         item_id
      )
   )
   return tuple(starting_item_ids)


def reconstruct_completed_build(sample, items_by_id, completed_items):
   """Reconstruct final completed core items and boots in purchase order."""

   raw_final_item_ids = [
      int(item["item_id"])
      for item in sample.get("final_items", [])
      if int(item["item_id"]) in items_by_id
   ]
   final_boot_ids = [
      item_id
      for item_id in raw_final_item_ids
      if build_static_data.is_boot_item(item_id, items_by_id)
      and int(items_by_id[item_id].get("depth", 0) or 0) >= 2
   ]
   final_item_ids = [
      item_id
      for item_id in raw_final_item_ids
      if item_id in completed_items
      and not build_static_data.is_boot_item(item_id, items_by_id)
   ]
   final_item_counts = Counter(final_item_ids)
   purchase_times = defaultdict(list)
   latest_timeline_boot = None

   item_events = sorted(
      sample.get("item_events", []),
      key=lambda event: (
         int(event.get("timestamp_ms", 0)),
         int(event.get("sequence_number", 0))
      )
   )
   for event in item_events:
      item_id = event.get("item_id")
      if item_id is None:
         continue
      item_id = int(item_id)
      event_type = event.get("event_type")
      if event_type == "ITEM_PURCHASED" and item_id in final_item_counts:
         purchase_times[item_id].append(int(event["timestamp_ms"]))

      is_completed_boot = (
         item_id in items_by_id
         and build_static_data.is_boot_item(item_id, items_by_id)
         and int(items_by_id[item_id].get("depth", 0) or 0) >= 2
      )
      if event_type == "ITEM_PURCHASED" and is_completed_boot:
         latest_timeline_boot = (int(event["timestamp_ms"]), item_id)
      elif (
         event_type == "ITEM_SOLD"
         and latest_timeline_boot is not None
         and latest_timeline_boot[1] == item_id
      ):
         latest_timeline_boot = None

   ordered_items = []
   for item_id, item_count in final_item_counts.items():
      times = sorted(purchase_times.get(item_id, []))[-item_count:]
      missing_time_count = item_count - len(times)
      times.extend([float("inf")] * missing_time_count)
      ordered_items.extend((timestamp, item_id) for timestamp in times)
   ordered_items.sort(key=lambda item: (item[0], item[1]))
   core_items = [item_id for _, item_id in ordered_items]

   if final_boot_ids:
      boot_purchase_times = {
         item_id: [
            int(event["timestamp_ms"])
            for event in item_events
            if event.get("event_type") == "ITEM_PURCHASED"
            and event.get("item_id") is not None
            and int(event["item_id"]) == item_id
         ]
         for item_id in final_boot_ids
      }
      boots = sorted(
         final_boot_ids,
         key=lambda item_id: (
            boot_purchase_times[item_id][-1]
            if boot_purchase_times[item_id]
            else float("inf"),
            item_id
         )
      )
   elif latest_timeline_boot is not None:
      # Role quests can move boots out of Match-V5's normal final item slots.
      boots = [latest_timeline_boot[1]]
   else:
      boots = []

   return {
      "starting_items": reconstruct_starting_items(sample, items_by_id),
      "core_items": tuple(core_items),
      "boots": tuple(boots)
   }


def _item_names(item_ids, items_by_id):
   return [
      items_by_id.get(item_id, {}).get("name", f"Unknown item {item_id}")
      for item_id in item_ids
   ]


def _summarize_paths(builds, field_name, path_length, items_by_id, top_n):
   path_results = defaultdict(lambda: {"games": 0, "wins": 0})
   for build in builds:
      item_path = tuple(build[field_name][:path_length])
      if len(item_path) != path_length:
         continue
      path_results[item_path]["games"] += 1
      path_results[item_path]["wins"] += int(bool(build["win"]))

   ordered_paths = sorted(
      path_results.items(),
      key=lambda result: (-result[1]["games"], -result[1]["wins"], result[0])
   )
   summaries = []
   for item_path, result in ordered_paths[:top_n]:
      summaries.append({
         "item_ids": list(item_path),
         "item_names": _item_names(item_path, items_by_id),
         "games": result["games"],
         "wins": result["wins"],
         "win_rate": round(result["wins"] / result["games"] * 100, 1)
      })
   return summaries


def _summarize_starting_loadouts(builds, items_by_id, top_n):
   loadout_results = defaultdict(lambda: {"games": 0, "wins": 0})
   for build in builds:
      loadout = tuple(build["starting_items"])
      if not loadout:
         continue
      loadout_results[loadout]["games"] += 1
      loadout_results[loadout]["wins"] += int(bool(build["win"]))

   ordered_loadouts = sorted(
      loadout_results.items(),
      key=lambda result: (-result[1]["games"], -result[1]["wins"], result[0])
   )
   return [
      {
         "item_ids": list(loadout),
         "item_names": _item_names(loadout, items_by_id),
         "games": result["games"],
         "wins": result["wins"],
         "win_rate": round(result["wins"] / result["games"] * 100, 1)
      }
      for loadout, result in ordered_loadouts[:top_n]
   ]


def _build_observed_full_build(
   builds,
   items_by_id,
   max_items=MAX_FULL_BUILD_ITEMS
):
   """Build one coherent item path by following the strongest observed prefix."""

   selected_item_ids = []
   slot_evidence = []
   candidate_builds = list(builds)
   for slot_index in range(max_items):
      item_results = defaultdict(lambda: {"games": 0, "wins": 0})
      for build in candidate_builds:
         if len(build["core_items"]) <= slot_index:
            continue
         item_id = int(build["core_items"][slot_index])
         item_results[item_id]["games"] += 1
         item_results[item_id]["wins"] += int(bool(build["win"]))
      if not item_results:
         break

      selected_item_id, result = sorted(
         item_results.items(),
         key=lambda item_result: (
            -item_result[1]["games"],
            -item_result[1]["wins"],
            item_result[0]
         )
      )[0]
      selected_item_ids.append(selected_item_id)
      slot_evidence.append({
         "slot": slot_index + 1,
         "item_id": selected_item_id,
         "item_name": items_by_id.get(selected_item_id, {}).get(
            "name", f"Unknown item {selected_item_id}"
         ),
         "games": result["games"],
         "wins": result["wins"],
         "win_rate": round(result["wins"] / result["games"] * 100, 1)
      })
      selected_prefix = tuple(selected_item_ids)
      candidate_builds = [
         build
         for build in candidate_builds
         if tuple(build["core_items"][:len(selected_prefix)]) == selected_prefix
      ]

   return {
      "item_ids": selected_item_ids,
      "item_names": _item_names(selected_item_ids, items_by_id),
      "slot_evidence": slot_evidence,
      "complete_path_games": len(candidate_builds) if selected_item_ids else 0
   }


def _summarize_situational_items(
   builds,
   excluded_item_ids,
   items_by_id,
   top_n
):
   """Rank observed completed alternatives not already in the primary build."""

   excluded_ids = {int(item_id) for item_id in excluded_item_ids}
   item_results = defaultdict(lambda: {"games": 0, "wins": 0})
   for build in builds:
      observed_alternatives = {
         int(item_id)
         for item_id in build["core_items"]
         if int(item_id) not in excluded_ids
      }
      for item_id in observed_alternatives:
         item_results[item_id]["games"] += 1
         item_results[item_id]["wins"] += int(bool(build["win"]))

   ordered_items = sorted(
      item_results.items(),
      key=lambda result: (-result[1]["games"], -result[1]["wins"], result[0])
   )
   return [
      {
         "item_id": item_id,
         "item_name": items_by_id.get(item_id, {}).get(
            "name", f"Unknown item {item_id}"
         ),
         "games": result["games"],
         "wins": result["wins"],
         "win_rate": round(result["wins"] / result["games"] * 100, 1)
      }
      for item_id, result in ordered_items[:top_n]
   ]


def aggregate_observed_builds(
   champion_id,
   role,
   patch,
   lane_opponent_champion_id=None,
   top_n=5,
   enemy_team_champion_ids=None,
   db_path=build_database.DEFAULT_BUILD_DB_PATH,
   cache_directory=build_static_data.DEFAULT_CACHE_DIRECTORY
):
   """Aggregate real completed item paths for a champion-role-patch context."""

   data_dragon_version = build_static_data.resolve_data_dragon_version(patch)
   champion_data = build_static_data.get_champion_data(
      data_dragon_version,
      cache_directory=Path(cache_directory)
   )
   item_data = build_static_data.get_item_data(
      data_dragon_version,
      cache_directory=Path(cache_directory)
   )
   champions_by_id, _ = build_static_data.build_champion_maps(champion_data)
   items_by_id, _ = build_static_data.build_item_maps(item_data)
   completed_items = build_static_data.get_completed_items(item_data)
   samples = build_database.get_build_samples(
      champion_id,
      role,
      patch,
      lane_opponent_champion_id=lane_opponent_champion_id,
      db_path=db_path
   )

   requested_enemy_ids = sorted({
      int(enemy_champion_id)
      for enemy_champion_id in (enemy_team_champion_ids or [])
   })
   if requested_enemy_ids:
      requested_enemy_id_set = set(requested_enemy_ids)
      samples = [
         sample
         for sample in samples
         if requested_enemy_id_set.intersection(
            sample.get("enemy_team_champion_ids", [])
         )
      ]

   builds = []
   for sample in samples:
      completed_build = reconstruct_completed_build(
         sample,
         items_by_id,
         completed_items
      )
      builds.append({
         **completed_build,
         "win": bool(sample["win"]),
         "lane_opponent_champion_id": sample.get("lane_opponent_champion_id"),
         "enemy_team_champion_ids": sample.get("enemy_team_champion_ids", [])
      })

   champion = champions_by_id.get(int(champion_id), {})
   lane_opponent = champions_by_id.get(int(lane_opponent_champion_id), {}) \
      if lane_opponent_champion_id is not None else {}
   full_build = _build_observed_full_build(builds, items_by_id)
   return {
      "patch": patch,
      "data_dragon_version": data_dragon_version,
      "champion_id": int(champion_id),
      "champion_name": champion.get("name", f"Unknown champion {champion_id}"),
      "role": role.upper(),
      "lane_opponent_champion_id": lane_opponent_champion_id,
      "lane_opponent_name": lane_opponent.get("name"),
      "enemy_team_filter_mode": "any_overlap" if requested_enemy_ids else None,
      "enemy_team_champion_ids": requested_enemy_ids,
      "enemy_team_champion_names": [
         champions_by_id.get(enemy_id, {}).get(
            "name", f"Unknown champion {enemy_id}"
         )
         for enemy_id in requested_enemy_ids
      ],
      "games_analyzed": len(samples),
      "builds_with_completed_items": sum(bool(build["core_items"]) for build in builds),
      "starting_items": _summarize_starting_loadouts(
         builds, items_by_id, top_n
      ),
      "full_build": full_build,
      "situational_items": _summarize_situational_items(
         builds,
         full_build["item_ids"],
         items_by_id,
         top_n
      ),
      "first_items": _summarize_paths(builds, "core_items", 1, items_by_id, top_n),
      "two_item_paths": _summarize_paths(builds, "core_items", 2, items_by_id, top_n),
      "three_item_paths": _summarize_paths(builds, "core_items", 3, items_by_id, top_n),
      "boots": _summarize_paths(builds, "boots", 1, items_by_id, top_n)
   }


def aggregate_opponent_builds(
   champion_id,
   role,
   patch,
   lane_opponent_champion_id,
   top_n=5,
   db_path=build_database.DEFAULT_BUILD_DB_PATH,
   cache_directory=build_static_data.DEFAULT_CACHE_DIRECTORY
):
   """Aggregate builds observed against one exact lane opponent."""

   if lane_opponent_champion_id is None:
      raise ValueError("A lane opponent champion ID is required")
   return aggregate_observed_builds(
      champion_id,
      role,
      patch,
      lane_opponent_champion_id=int(lane_opponent_champion_id),
      top_n=top_n,
      db_path=db_path,
      cache_directory=cache_directory
   )


def aggregate_enemy_team_builds(
   champion_id,
   role,
   patch,
   enemy_team_champion_ids,
   top_n=5,
   db_path=build_database.DEFAULT_BUILD_DB_PATH,
   cache_directory=build_static_data.DEFAULT_CACHE_DIRECTORY
):
   """Aggregate builds from games sharing at least one selected enemy."""

   if not enemy_team_champion_ids:
      raise ValueError("At least one enemy champion ID is required")
   return aggregate_observed_builds(
      champion_id,
      role,
      patch,
      top_n=top_n,
      enemy_team_champion_ids=enemy_team_champion_ids,
      db_path=db_path,
      cache_directory=cache_directory
   )


def _find_previous_patch(champion_id, role, requested_patch, db_path):
   """Find the newest earlier patch with data in the same numbered season."""

   requested_family = build_static_data.patch_family(requested_patch)
   requested_parts = tuple(int(piece) for piece in requested_family.split("."))
   for patch_result in build_database.get_champion_role_patch_counts(
      champion_id,
      role,
      db_path=db_path
   ):
      candidate_patch = build_static_data.patch_family(patch_result["patch"])
      candidate_parts = tuple(int(piece) for piece in candidate_patch.split("."))
      if (
         candidate_parts[0] == requested_parts[0]
         and candidate_parts < requested_parts
      ):
         return candidate_patch
   return None


def recommend_build(
   my_champion_id,
   my_role,
   patch,
   lane_opponent_champion_id=None,
   *,
   enemy_team_champion_ids=None,
   minimum_current_patch_games=3,
   minimum_matchup_games=3,
   minimum_enemy_team_games=3,
   top_n=5,
   db_path=build_database.DEFAULT_BUILD_DB_PATH,
   cache_directory=build_static_data.DEFAULT_CACHE_DIRECTORY
):
   """Choose matchup data when reliable, otherwise use champion-role data."""

   if minimum_current_patch_games < 1:
      raise ValueError("minimum_current_patch_games must be at least 1")
   if minimum_matchup_games < 1:
      raise ValueError("minimum_matchup_games must be at least 1")
   if minimum_enemy_team_games < 1:
      raise ValueError("minimum_enemy_team_games must be at least 1")

   requested_patch = build_static_data.patch_family(patch)
   current_patch_baseline = aggregate_observed_builds(
      my_champion_id,
      my_role,
      requested_patch,
      top_n=top_n,
      db_path=db_path,
      cache_directory=cache_directory
   )
   effective_patch = requested_patch
   patch_source = "current_patch"
   baseline = current_patch_baseline

   if (
      current_patch_baseline["builds_with_completed_items"]
      < minimum_current_patch_games
   ):
      previous_patch = _find_previous_patch(
         my_champion_id,
         my_role,
         requested_patch,
         db_path
      )
      if previous_patch is not None:
         effective_patch = previous_patch
         patch_source = "previous_patch_fallback"
         baseline = aggregate_observed_builds(
            my_champion_id,
            my_role,
            effective_patch,
            top_n=top_n,
            db_path=db_path,
            cache_directory=cache_directory
         )

   matchup = None
   enemy_team = None
   selected_build = baseline
   recommendation_source = "champion_role"

   if enemy_team_champion_ids:
      enemy_team = aggregate_enemy_team_builds(
         my_champion_id,
         my_role,
         effective_patch,
         enemy_team_champion_ids,
         top_n=top_n,
         db_path=db_path,
         cache_directory=cache_directory
      )
      if enemy_team["builds_with_completed_items"] >= minimum_enemy_team_games:
         selected_build = enemy_team
         recommendation_source = "enemy_team"
      else:
         recommendation_source = "champion_role_fallback"

   if lane_opponent_champion_id is not None:
      matchup = aggregate_opponent_builds(
         my_champion_id,
         my_role,
         effective_patch,
         lane_opponent_champion_id,
         top_n=top_n,
         db_path=db_path,
         cache_directory=cache_directory
      )
      if matchup["builds_with_completed_items"] >= minimum_matchup_games:
         selected_build = matchup
         recommendation_source = "lane_opponent"
      elif enemy_team is None or (
         enemy_team["builds_with_completed_items"] < minimum_enemy_team_games
      ):
         recommendation_source = "champion_role_fallback"

   return {
      "patch_source": patch_source,
      "requested_patch": requested_patch,
      "effective_patch": effective_patch,
      "minimum_current_patch_games": minimum_current_patch_games,
      "current_patch_games_analyzed": current_patch_baseline["games_analyzed"],
      "recommendation_source": recommendation_source,
      "minimum_matchup_games": minimum_matchup_games,
      "minimum_enemy_team_games": minimum_enemy_team_games,
      "baseline_games_analyzed": baseline["games_analyzed"],
      "matchup_games_analyzed": matchup["games_analyzed"] if matchup else 0,
      "enemy_team_games_analyzed": enemy_team["games_analyzed"] if enemy_team else 0,
      "requested_lane_opponent_champion_id": lane_opponent_champion_id,
      "requested_lane_opponent_name": matchup["lane_opponent_name"] if matchup else None,
      "requested_enemy_team_champion_ids": (
         enemy_team["enemy_team_champion_ids"] if enemy_team else []
      ),
      "requested_enemy_team_champion_names": (
         enemy_team["enemy_team_champion_names"] if enemy_team else []
      ),
      "build": selected_build
   }
