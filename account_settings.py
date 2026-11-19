"""Private installation-specific Chess.com profile settings.

Public Chess.com profile API only. No password, OAuth token or developer account.
Never sync an unconfigured user; changing account does not copy old games.
"""
from __future__ import annotations
import json,os,re,threading
from pathlib import Path
import requests
from chess_grind import HOME
from chesscom_api import USERNAME_PATTERN
CONFIG=HOME/"chesscom_profile.json"
LOCK=threading.RLock()
def current():
 with LOCK:
  try:
   payload=json.loads(CONFIG.read_text("utf8"))
   value=payload.get("username","")
   if isinstance(value,str) and USERNAME_PATTERN.fullmatch(value):
    return {"username":value.lower(),"configured":True,"syncEnabled":bool(payload.get("syncEnabled",False))}
  except (OSError,ValueError,TypeError,AttributeError):pass
 return {"username":"","configured":False,"syncEnabled":False}

def validate(username):
 if not isinstance(username,str):raise ValueError("Enter a Chess.com username")
 # Accept exactly Chess.com profile URLs and raw usernames; do not perform arbitrary requests.
 value=username.strip()
 found=re.fullmatch(r"https://(?:www\.)?chess\.com/(?:member|player)/([A-Za-z0-9_-]{3,25})/?",value,re.I)
 if found:value=found.group(1)
 if not USERNAME_PATTERN.fullmatch(value):
  raise ValueError("Enter a valid Chess.com username or chess.com/member/username profile URL")
 return value.lower()

def verify(username):
 name=validate(username)
 # API endpoint is hardcoded, not user-supplied: prevents SSRF.
 url="https://api.chess.com/pub/player/"+name
 try:
  response=requests.get(url,timeout=(6,18),
   headers={"User-Agent":"ChessGrind/1.0 (Chess.com public profile verification)","Accept":"application/json"})
 except requests.RequestException as ex:
  raise ValueError("Could not contact Chess.com. Retry while online.") from ex
 if response.status_code==404:raise ValueError("Chess.com could not find that username")
 if not response.ok:raise ValueError("Chess.com profile verification returned HTTP "+str(response.status_code))
 try:profile=response.json()
 except ValueError as ex:raise ValueError("Chess.com returned an invalid profile response") from ex
 if not isinstance(profile,dict) or str(profile.get("username","")).lower()!=name:
  raise ValueError("Chess.com returned an unexpected profile. No settings were saved.")
 return {"username":name,"profileUrl":"https://www.chess.com/member/"+name,
         "avatar":profile.get("avatar") if isinstance(profile.get("avatar"),str) else None}

def save(username,sync_enabled=False,verified=False):
 profile=verify(username) if not verified else {"username":validate(username)}
 value={"username":profile["username"],"syncEnabled":bool(sync_enabled)}
 HOME.mkdir(parents=True,exist_ok=True)
 with LOCK:
  temp=CONFIG.with_suffix(".tmp")
  try:
   temp.write_text(json.dumps(value,indent=2),encoding="utf8")
   temp.replace(CONFIG)
  finally:temp.unlink(missing_ok=True)
 return {**current(),"profileUrl":"https://www.chess.com/member/"+value["username"]}

def disable_sync():
 with LOCK:
  existing=current()
  if not existing["configured"]:return existing
  return save(existing["username"],False,verified=True)

def username():
 return current()["username"]
