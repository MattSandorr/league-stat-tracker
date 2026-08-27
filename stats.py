
def win_rate(matches):
   if len(matches) == 0:
      return 0
   wins =0
   for match in matches:
      if match["win"] ==1:
         wins+=1
   return wins/len(matches) *100


def average_kda(matches):
   if len(matches) == 0:
      return None

   total_kills = 0
   total_deaths = 0
   total_assists = 0

   for match in matches:
     total_kills += match["kills"]
     total_deaths += match["deaths"]
     total_assists += match["assists"]

     num_matches = len(matches)

   return {
      "avg_kills": total_kills / num_matches,
      "avg_deaths": total_deaths / num_matches,
      "avg_assists": total_assists / num_matches
    }

def most_played_champ(matches):
   if len(matches) == 0:
      return None

   champ_count = {}

   for match in matches:
      champ = match["champion"]
      if champ in champ_count:
         champ_count[champ] +=1
      else:
         champ_count[champ] =1
   most_played = max(champ_count, key = champ_count.get)
   return most_played, champ_count[most_played]

def win_rate_by_champ(matches,champion_name):
   champ_matches = []
   for match in matches:
      if match["champion"] == champion_name:
         champ_matches.append(match)
         
   if len(champ_matches) == 0:
      return None
   return win_rate(champ_matches)

def win_rate_past_games(matches, n): #n past number of games
    sorted_matches = sorted(matches, key=lambda match: match["game_date"], reverse=True)
    recent_matches = sorted_matches[:n]
    return win_rate(recent_matches)   


def win_by_role(matches):
    role_stats = {}

    for match in matches:
        role = match["role"]
        
        if role not in role_stats:
            role_stats[role] = {"wins": 0, "total": 0}
        
        role_stats[role]["total"] += 1
        if match["win"] == 1:
            role_stats[role]["wins"] += 1

    result = {}
    for role, stats in role_stats.items():
        result[role] = stats["wins"] / stats["total"] * 100

    return result

def champ_pool(matches):
   champ_count = {}

   for match in matches:
      champ = match["champion"]
      if champ in champ_count:
         champ_count[champ] +=1
      else:
         champ_count[champ] =1
   return sorted(champ_count.items(), key=lambda item: item[1], reverse=True)
