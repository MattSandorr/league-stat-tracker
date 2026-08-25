import requests

ROLE_ITEM_POOLS = {
    "BOTTOM": {  # ADC
        "offense": ["Infinity Edge", "Kraken Slayer", "Rapid Firecannon"],
        "vs_magic": ["Mercurial Scimitar"],
        "vs_physical": ["Guardian Angel"]
    },
    "TOP": {
        "offense": ["Sundered Sky", "Trinity Force"],
        "vs_magic": ["Spirit Visage", "Force of Nature"],
        "vs_physical": ["Thornmail", "Randuin's Omen"]
    }
}

def get_enemy_team(live_data, my_puuid):
   my_team_id = None

   for particpant in live_data["participants"]:
      if particpant["puuid"] == my_puuid:
         my_team_id = particpant["teamId"]
         break

   enemy_team = []
   for participant in live_data["participants"]:
      if participant["teamId"] != my_team_id:
         enemy_team.append(participant["championId"])
    
   return enemy_team

def get_latest_version():
    url = "https://ddragon.leagueoflegends.com/api/versions.json"
    response = requests.get(url)
    versions = response.json()
    return versions[0]  # most recent version is first in the list


def get_champion_data(version):
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    response = requests.get(url)
    return response.json()

def build_champion_id_map(champ_data):
    id_map = {}
    for champ_name, champ_info in champ_data["data"].items():
        champ_id = int(champ_info["key"])
        id_map[champ_id] = champ_info
    return id_map

def analyze_team_comp(champion_ids,id_map):
   total_attack = 0
   total_magic = 0
   total_defense = 0
   for champ_id in champion_ids:
      champ_info = id_map[champ_id]["info"]
      total_attack = champ_info["attack"]
      total_magic = champ_info["magic"]
      total_defense = champ_info["defense"]
   return {
      "total_attack": total_attack,
      "total_magic": total_magic,
      "total_defense": total_defense
    }

def recommend_build(my_chmapion_id,my_role,enemy_team_ids,id_map):
   enemy_analysis = analyze_team_comp(enemy_team_ids, id_map)
   role_pool = ROLE_ITEM_POOLS.get(my_role)

   if role_pool == None:
      return None

   if my_role == "BOTTOM":
      primary = role_pool["offense"]
      situational = None

      if enemy_analysis["total_magic"] > enemy_analysis["total_attack"]:
            situational = role_pool["vs_magic"]
      elif enemy_analysis["total_attack"] > enemy_analysis["total_magic"]:
            situational = role_pool["vs_physical"]

      return {
         "primary": primary,
         "situational": situational
        }

   if my_role == "TOP":
      pass

# if __name__ == "__main__":
#     version = get_latest_version()
#     champ_data = get_champion_data(version)
#     id_map = build_champion_id_map(champ_data)
    
#     print(id_map[103])
#     print(id_map[103]["tags"])

#     enemy_team_ids = [429, 154, 526, 157, 17]
#     comp_analysis = analyze_team_comp(enemy_team_ids, id_map)
#     print(comp_analysis)

# if __name__ == "__main__":
#     version = get_latest_version()
#     champ_data = get_champion_data(version)
#     id_map = build_champion_id_map(champ_data)

#     enemy_team_ids = [429, 154, 526, 157, 17]
#     result = recommend_build(221, "BOTTOM", enemy_team_ids, id_map)  # 221 = Zeri
#     print(result)