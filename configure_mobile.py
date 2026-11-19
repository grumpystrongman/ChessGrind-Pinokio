"""Configure the Cloudflare Access gate after Cloudflare Setup.

No tunnel token, API key, or password is saved here. The config contains
only the public app hostname, team domain and expected Access audience.
"""
import argparse
import json
from mobile_security import CONFIG, HOSTNAME_RE, TEAM_RE, AUD_RE, public_config

def configure(hostname,team_domain,audience):
    hostname=hostname.strip().lower().replace('https://','').strip('/')
    team_domain=team_domain.strip().lower().replace('https://','').strip('/')
    audience=audience.strip()
    if not HOSTNAME_RE.fullmatch(hostname):
        raise ValueError("Hostname must be a valid full DNS name, such as chess.example.com")
    if not TEAM_RE.fullmatch(team_domain):
        raise ValueError("Team domain must be <your-team>.cloudflareaccess.com")
    if not AUD_RE.fullmatch(audience):
        raise ValueError("Invalid Cloudflare Access application AUD tag")
    CONFIG.parent.mkdir(parents=True,exist_ok=True)
    tmp=CONFIG.with_suffix('.tmp')
    tmp.write_text(json.dumps({"hostname":hostname,"team_domain":team_domain,
         "audience":audience},indent=2),encoding='utf8')
    tmp.replace(CONFIG)
    return {"configured":True,"hostname":hostname,"team_domain":team_domain,
            "audience_tail":audience[-6:]}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['configure','status','disable'])
    parser.add_argument('--hostname')
    parser.add_argument('--team-domain')
    parser.add_argument('--aud')
    args=parser.parse_args()
    if args.action=='configure':
        if not all((args.hostname,args.team_domain,args.aud)):
            parser.error("--hostname, --team-domain and --aud are required")
        result=configure(args.hostname,args.team_domain,args.aud)
    elif args.action=='disable':
        CONFIG.unlink(missing_ok=True)
        result={"configured":False}
    else:
        loaded=public_config()
        result=({"configured":True,"hostname":loaded["hostname"],
                 "team_domain":loaded["team_domain"],"audience_tail":loaded["audience"][-6:]}
                if loaded else {"configured":False})
    print(json.dumps(result,indent=2))
