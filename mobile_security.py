"""Fail-closed origin authentication for a Cloudflare Access-protected phone app.

Local 127.0.0.1 requests continue to work. Public-host requests require
a trusted hostname and a cryptographically verified Cloudflare Access JWT.
Never publish Chess Grind through an unprotected Quick Tunnel.
"""
from functools import lru_cache
import json
import re
from pathlib import Path
import jwt
from jwt import PyJWKClient

CONFIG = Path.home()/".chess_grind"/"mobile_access.json"
HOSTNAME_RE = re.compile(r"^(?=.{4,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")
TEAM_RE = re.compile(r"^[a-z0-9-]{2,63}\.cloudflareaccess\.com$")
AUD_RE = re.compile(r"^[a-zA-Z0-9_-]{16,128}$")
LOCAL_HOSTS = frozenset(("127.0.0.1:"+__import__("os").environ.get("CHESSGRIND_PORT","8765"),"localhost:"+__import__("os").environ.get("CHESSGRIND_PORT","8765")))

def public_config():
    try:
        payload=json.loads(CONFIG.read_text(encoding="utf8"))
        h=str(payload.get("hostname","")).lower().strip()
        t=str(payload.get("team_domain","")).lower().strip()
        a=str(payload.get("audience","")).strip()
        if not (HOSTNAME_RE.fullmatch(h) and TEAM_RE.fullmatch(t) and AUD_RE.fullmatch(a)):
            return None
        if h=="127.0.0.1" or h.endswith(".cloudflareaccess.com"):
            return None
        return {"hostname":h,"team_domain":t,"audience":a}
    except (OSError,ValueError,TypeError):
        return None

@lru_cache(maxsize=4)
def verifier(team_domain):
    issuer="https://"+team_domain
    return PyJWKClient(issuer+"/cdn-cgi/access/certs", cache_jwk_set=True,lifespan=3600)

def authorize(host,headers):
    """Return (allowed, is_cloudflare_remote).

    Deny any request with a Cloudflare proxy marker masquerading as localhost.
    We do not trust a forwarded identity header without verifying its signature.
    """
    host=host.lower().strip()
    from_cloudflare=any(headers.get(k,"") for k in
       ("Cf-Connecting-Ip","Cf-Ray","Cf-Access-Jwt-Assertion"))
    if host in LOCAL_HOSTS and not from_cloudflare:
        return True,False
    if __import__("os").environ.get("CHESSGRIND_LOCAL_ONLY","1")=="1":return False,True
    config=public_config()
    if not config or host!=config["hostname"]:
        return False,True
    assertion=headers.get("Cf-Access-Jwt-Assertion","")
    if not assertion or len(assertion)>8192:
        return False,True
    try:
        team=config["team_domain"]
        key=verifier(team).get_signing_key_from_jwt(assertion)
        jwt.decode(assertion,key.key,algorithms=["RS256"],audience=config["audience"],
          issuer="https://"+team,options={"require":["iss","aud","exp","iat"]},
          leeway=20)
        return True,True
    except (jwt.PyJWTError,ValueError,OSError,TimeoutError):
        return False,True

def check_origin(origin,host,is_remote):
    if not origin:
        return True
    if is_remote:
        return origin.lower()=="https://"+host
    return origin in ("http://127.0.0.1:"+__import__("os").environ.get("CHESSGRIND_PORT","8765"),"http://localhost:"+__import__("os").environ.get("CHESSGRIND_PORT","8765"))
