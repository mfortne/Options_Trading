from schwab import client as sc
from schwab.auth import easy_client
import json

CLIENT_ID = "Q9o7oQdC0KJAWEFBaVXKVjxIA3lxh6VXyjOX3OcovbSA2gQT"          # e.g. ABC123@AMER.OAUTHAPPS
CLIENT_SECRET = "BTk1WOxOg4DOToP6lhNYYFLgJpGbNyvLzBlqAG2Tb6oPe6zlN7u98o6VJzKaPofg"
REDIRECT_URI = "https://127.0.0.1:8182"       # exact match

client = easy_client(
    api_key=CLIENT_ID,
    app_secret=CLIENT_SECRET,
    callback_url=REDIRECT_URI,
    token_path="./schwab_tokens.json"
)

print("Getting user preferences...")
prefs = client.get_user_preferences()
print(json.dumps(prefs.json(), indent=2))

print("\nGetting TQQQ quote...")
quote = client.get_quote("TQQQ")
print(json.dumps(quote.json(), indent=2))

print("\nGetting TQQQ option chain...")
chain = client.get_option_chain("TQQQ")  # or specify params like strikeCount=10, contractType='PUT'
print(json.dumps(chain.json(), indent=2))