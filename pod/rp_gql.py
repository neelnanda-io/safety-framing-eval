"""(Copied from the run agent's scratch folder, 21 Nov 2026.) Send one GraphQL query to RunPod's API and print the JSON reply. Reads RUNPOD_API_KEY from .env
and sends it in a header; never prints it. Usage: python3 rp_gql.py '<query>'"""
import json, os, sys, urllib.request
from dotenv import load_dotenv
load_dotenv('.env')
key = os.environ["RUNPOD_API_KEY"]
req = urllib.request.Request("https://api.runpod.io/graphql", data=json.dumps({"query": sys.argv[1]}).encode(),
                             headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                                      "User-Agent": "sfe-client/1.0"})
try:
    out = urllib.request.urlopen(req, timeout=60).read().decode()
except urllib.error.HTTPError as e:
    out = e.read().decode()
print(out.replace(key, "<key>"))
