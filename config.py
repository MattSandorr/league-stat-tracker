import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("RIOT_API_KEY")
PLATFORM_REGION = "na1"
REGIONAL_ROUTE = "americas"