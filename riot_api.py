import config, requests

HEADERS = {"X-Riot-Token": config.API_KEY}

def get_puuid_riot_id(name, tag): # (Matchu#420)
   url = f"https://{config.REGIONAL_ROUTE}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tag}"

   response = requests.get(url, headers=HEADERS)

   if response.status_code == 200:
      return response.json()
   else:
       print(f"Error {response.status_code}: {response.text}")
       return None

def get_summoner(puuid):
   url = f"https://{config.PLATFORM_REGION}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"

   response = requests.get(url, headers=HEADERS)

   if response.status_code == 200:
      return response.json()
   else:
       print(f"Error {response.status_code}: {response.text}")
       return None 

def get_rank(puuid):
   url = f"https://{config.PLATFORM_REGION}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"

   response = requests.get(url, headers=HEADERS)

   if response.status_code == 200:
      return response.json()
   else:
       print(f"Error {response.status_code}: {response.text}")
       return None

def get_match_id(puuid, count):
   url = f"https://{config.REGIONAL_ROUTE}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"

   response = requests.get(url, headers=HEADERS,params={"count": count} )

   if response.status_code == 200:
      return response.json()
   else:
       print(f"Error {response.status_code}: {response.text}")
       return None


def get_match_stats(match_id):
   url = f"https://{config.REGIONAL_ROUTE}.api.riotgames.com/lol/match/v5/matches/{match_id}"   

   response = requests.get(url, headers=HEADERS)

   if response.status_code == 200:
      return response.json()
   else:
       print(f"Error {response.status_code}: {response.text}")
       return None
   
def get_live_stats(puuid): #live game for build helper
   url = f"https://{config.PLATFORM_REGION}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"   

   response = requests.get(url, headers=HEADERS)

   if response.status_code == 200:
      return response.json()
   else:
       print(f"Error {response.status_code}: {response.text}")
       return None
   
# def find_my_stats(match_data, my_puuid):
#     for participant in match_data["info"]["participants"]:
#         if participant["puuid"] == my_puuid:
#             return participant
#     return None
   
print("script started")

if __name__ == "__main__":
   result = get_puuid_riot_id("Matchu", "420")
   print(result)

   if result: 
      puuid = result["puuid"]
      summoner_data = get_summoner(puuid)
      print("Summoner data", summoner_data)

      rank_data = get_rank(puuid)
      print("RANK",rank_data)

      match_id = get_match_id(puuid,20)
      print("match ids",match_id)

      if match_id:
         first_match_id = match_id[0]
         match_stats = get_match_stats(first_match_id)
         print("match stats",match_stats)

      # my_stats = find_my_stats(match_stats,puuid)

      # if my_stats:
      #     print("Champion:", my_stats["championName"])
      #     print("Kills:", my_stats["kills"])
      #     print("Deaths:", my_stats["deaths"])
      #     print("Assists:", my_stats["assists"])             
      #     print("Win:", my_stats["win"])
      # else:
      #     print("Couldn't find your stats in this match")