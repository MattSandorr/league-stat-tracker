import sqlite3

DB_PATH = "data/tracker.db"

def init_db():

   conn = sqlite3.connect(DB_PATH)
   cursor = conn.cursor()

   cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            champion TEXT,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            win INTEGER,
            game_duration INTEGER,
            game_date INTEGER,
            role TEXT
        )
    """)
   conn.commit()
   conn. close()

def save_match(my_stats: dict, match_id: str, game_duration: int, game_date: int):
   conn = sqlite3.connect(DB_PATH)
   cursor = conn.cursor()

   cursor.execute("""
         INSERT INTO matches (match_id, champion, kills, deaths, assists, win, game_duration, game_date, role)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      """, (
         match_id,
         my_stats["championName"],
         my_stats["kills"],
         my_stats["deaths"],
         my_stats["assists"],
         1 if my_stats["win"] else 0,
         game_duration,
         game_date,
         my_stats["teamPosition"]
      ))
   conn.commit()
   conn. close()
   
def get_all_matches():
   conn = sqlite3.connect(DB_PATH)
   cursor = conn.cursor()

   cursor.execute("SELECT * FROM matches")
   rows = cursor.fetchall()
   columns = [description[0] for description in cursor.description]
   conn.close()
   return [dict(zip(columns, row)) for row in rows]