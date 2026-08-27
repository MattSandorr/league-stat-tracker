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
   
print("script started")

import json

if __name__ == "__main__":
    account_data = get_puuid_riot_id("Matchu", "420")
    puuid = account_data["puuid"]
    
    live_data = get_live_stats(puuid)
    
    if live_data:
        with open("sample_live_game.json", "w") as f:
            json.dump(live_data, f, indent=2)
        print("Saved live game data!")
    else:
        print("Not currently in a game")
