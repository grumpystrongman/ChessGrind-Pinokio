"""Offline bot roster and five locally saved, editable coach personas.

Bots are fictional. Their move quality comes exclusively from Stockfish's UCI
skill option, NOT an invented human Elo rating or an LLM.
"""
from __future__ import annotations
import json, re, threading
from pathlib import Path
from chess_grind import HOME

# name, short backstory, play style, coaching quip, portrait palette
ARCHETYPES=[
 ("Milo","The park-table newcomer","Just learned about pins. Loves lively piece play.","balanced","#88b7a0","#253d37"),
 ("Pip","The coffeehouse regular","Always looks for a fun tactical shot.","active","#e7b875","#574034"),
 ("Nora","The patient student","Careful, methodical, never rushes her development.","solid","#bc9fc9","#3b3151"),
 ("Theo","The eager club rookie","Favors straightforward attacks.","active","#a8cf82","#3b5037"),
 ("Iris","The weekend strategist","Treats pawns like long-term investments.","solid","#c9a27f","#433323"),
 ("Remy","The gambit enthusiast","Likes initiative and activity over quiet play.","active","#e5a18e","#55343a"),
 ("Ada","The neighborhood champion","Plays principled, resourceful chess.","balanced","#a3bfd7","#283f53"),
 ("Basil","The fortress builder","Prefers restraint and safe positions.","solid","#a8b69b","#344837"),
 ("Sasha","The sharp tactician","Tests every loose piece.","active","#df9dc1","#4c3047"),
 ("Felix","The positional craftsman","Presses small edges.","solid","#a1c9c8","#244746"),
 ("Kira","The fearless attacker","Scans for forcing sequences first.","active","#dbab82","#613d30"),
 ("Omar","The steady veteran","Calm decisions and stubborn defense.","solid","#93b4c9","#2c415b"),
 ("Lena","The opening explorer","Connects development to middlegame plans.","balanced","#dfb8d2","#53445c"),
 ("Dante","The tactical grinder","Never lets you forget the opponent has threats.","active","#dca078","#492e2b"),
 ("Vera","The endgame specialist","Enjoys king activity and precision.","solid","#a8c5aa","#2e493b"),
 ("Rook","The practical competitor","Keeps the pressure on in complicated positions.","balanced","#d4c38d","#544c33"),
 ("Elise","The tournament technician","Tests calculation before committing.","solid","#c0a3cf","#433659"),
 ("Kenji","The counterpuncher","Waits for overextension then strikes.","active","#9bc6c4","#33565a"),
 ("Maeve","The conversion expert","Finds sturdy ways to turn advantages into wins.","solid","#cda5a0","#553e48"),
 ("Atlas","The elite challenger","Sees deep tactical and positional resources.","balanced","#b5c6db","#30435c"),
 ("Oracle","The deep-search rival","Severe positional scrutiny, no free tactics.","balanced","#e5c991","#544a35"),
 ("MAX","Unrestricted Stockfish","Full engine skill, longer search budget. Not a human Elo rating.","balanced","#f0d9a2","#283336"),
]
BOT_ROSTER=[]
for n,(name,role,bio,style,a,b) in enumerate(ARCHETYPES):
    slug=re.sub(r"[^a-z0-9]+","-",name.lower()).strip("-")
    BOT_ROSTER.append(dict(id=slug,name=name,role=role,bio=bio,style=style,
       skill=min(n,20),maxStrength=n==21,avatar=f"/icons/bots/{slug}.svg",
       title=("MAXIMUM" if n==21 else f"Stockfish skill {n}/20")))
BOT_INDEX={p["id"]:p for p in BOT_ROSTER}
COACH_LIMIT=5
LOCK=threading.RLock()
FILE=HOME/"arena_coaches.json"
ACTIVE_FILE=HOME/"arena_active_coach.json"
KOKORO_VOICES=("af_heart","af_sarah","af_bella","af_nicole","af_sky","am_adam","am_michael","am_echo","bf_emma","bf_isabella","bm_george","bm_lewis")
QUIRKS={
 "threats":"Always asks what the opponent is threatening",
 "candidates":"Insists on two candidate moves",
 "piece-safety":"Obsessed with loose pieces",
 "king-safety":"Checks king safety first",
 "pawn-structure":"Studies pawn structure before tactics",
 "endgame":"Counts king and pawn tempos",
 "quiet":"Says less and only speaks on big decisions"
}
# Character canon. Players choose who to work with, never manufacture a quirk.
# Every coach has a distinct teaching philosophy, cadence and default voice.
COACH_CAST=[
 dict(id="coach-mentor",name="Coach Morgan",specialty="Whole-board awareness",
      tone="supportive",quirk="threats",voice="af_sarah",rate=0.96,skill=8,style="balanced",
      biography="The patient neighborhood mentor. Encourages good decisions, notices threats before tactics, and celebrates progress without excessive praise.",
      signature="What changed for your opponent?"),
 dict(id="coach-tactics",name="Coach Quinn",specialty="Calculation and tactics",
      tone="challenging",quirk="candidates",voice="am_michael",rate=1.10,skill=12,style="active",
      biography="A demanding puzzle-room veteran who insists on two candidate moves and concrete variations. Rarely accepts a vague explanation.",
      signature="Give me the second candidate."),
 dict(id="coach-iris",name="Coach Iris",specialty="Positional and pawn play",
      tone="analytical",quirk="pawn-structure",voice="bf_emma",rate=0.94,skill=14,style="solid",
      biography="A meticulous positional strategist who remembers pawn weaknesses long after flashy tactics fade.",
      signature="Which weakness stays behind?"),
 dict(id="coach-rook",name="Coach Rook",specialty="Practical defense and safety",
      tone="playful",quirk="piece-safety",voice="am_adam",rate=1.12,skill=10,style="active",
      biography="A warm but mischievous former hustler who spots hanging pieces, tells memorable stories, and gets animated when material is gifted.",
      signature="Who left that piece unattended?"),
 dict(id="coach-vera",name="Coach Vera",specialty="Endgame and precision",
      tone="calm",quirk="endgame",voice="bf_isabella",rate=0.86,skill=16,style="solid",
      biography="A quiet endgame technician who speaks only when she has something concrete to add. Loves opposition, king activity and tempi.",
      signature="Count the tempi."),
]
CAST_INDEX={c["id"]:c for c in COACH_CAST}
def _character(c):
    person=CAST_INDEX.get(c.get("id"))
    if not person:return {"character":False,"signature":"A coach selected for their individual approach"}
    # Canonical character identity and personality are fixed and not editable.
    return {**c,**{k:v for k,v in person.items() if k not in ("skill", "style", "rate")},
            "character":True}

def recruit_coach(identifier):
    if identifier not in CAST_INDEX:raise ValueError("Choose an available coach")
    with LOCK:
        rows=coaches()
        if any(row["id"]==identifier for row in rows):raise ValueError("This coach is already on your team")
        if len(rows)>=COACH_LIMIT:raise ValueError("Your five coaching spots are full")
        rows.append(dict(CAST_INDEX[identifier]))
        _write_coaches(rows)
        return {"coaches":coaches(),"limit":COACH_LIMIT}

def _write_coaches(rows):
    HOME.mkdir(parents=True,exist_ok=True)
    tmp=FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(rows,indent=2),encoding="utf8")
        tmp.replace(FILE)
    finally:tmp.unlink(missing_ok=True)

DEFAULTS=[
 dict(id="coach-mentor",name="Coach Morgan",specialty="Whole-game mentor",tone="supportive",voice="af_sarah",rate=1.0,
      biography="A patient club mentor who explains decisions in plain language.",quirk="threats"),
 dict(id="coach-tactics",name="Coach Quinn",specialty="Calculation and tactics",tone="challenging",voice="am_michael",rate=1.0,
      biography="A former tactical trainer who asks for candidate moves before conclusions.",quirk="candidates")
]
def _check(record):
    if not isinstance(record,dict):raise ValueError("Invalid coach")
    name=str(record.get("name","")).strip()
    if not 2<=len(name)<=48 or any(ord(c)<32 for c in name):raise ValueError("Coach name must be 2-48 printable characters")
    specialty=str(record.get("specialty","")).strip()
    if not 2<=len(specialty)<=70:raise ValueError("Set a coaching specialty (2-70 characters)")
    biography=str(record.get("biography","")).strip()
    if len(biography)>300:raise ValueError("Coach biography is too long")
    tone=record.get("tone","supportive")
    if tone not in ("supportive","challenging","analytical","playful","calm"):raise ValueError("Unsupported coaching tone")
    voice=record.get("voice","af_sarah")
    if voice not in KOKORO_VOICES:raise ValueError("Choose an available voice preset")
    rate=record.get("rate",1.0)
    if isinstance(rate,bool) or not isinstance(rate,(int,float)) or not 0.7<=rate<=1.4:raise ValueError("Voice speed must be 0.7-1.4")
    quirk=record.get("quirk","threats")
    if quirk not in QUIRKS:raise ValueError("Choose a supported coaching quirk")
    skill=record.get("skill",8)
    if isinstance(skill,bool) or not isinstance(skill,int) or not 0<=skill<=20:
        raise ValueError("Choose Stockfish skill 0-20 for coach challenges")
    style=record.get("style","balanced")
    if style not in ("balanced","active","solid"):
        raise ValueError("Choose a supported play style")
    return dict(name=name,specialty=specialty,biography=biography,tone=tone,
                voice=voice,rate=float(rate),skill=skill,style=style,quirk=quirk)
def normalized_coach(coach):
    # Preserve profiles created before playable coaches were introduced.
    return {"skill":8,"style":"balanced","quirk":"threats",**coach}

def coaches():
    with LOCK:
        if FILE.exists():
            try:
                raw=json.loads(FILE.read_text("utf8"))
                if isinstance(raw,list):return [_character(normalized_coach(x)) for x in raw[:COACH_LIMIT]]
            except (ValueError,OSError):pass
        return [_character(normalized_coach(x)) for x in DEFAULTS]
def save_coach(payload):
    checked=_check(payload)
    with LOCK:
        rows=coaches()
        identifier=payload.get("id")
        if identifier is not None and (not isinstance(identifier,str) or not re.fullmatch("[a-z0-9-]{3,50}",identifier)):
            raise ValueError("Invalid coach ID")
        matched=next((i for i,x in enumerate(rows) if x["id"]==identifier),None)
        if matched is not None and identifier in CAST_INDEX:
            person=CAST_INDEX[identifier]
            checked.update({k:person[k] for k in ("name","specialty","biography","tone","quirk","voice")})
        if matched is None:
            if len(rows)>=COACH_LIMIT:raise ValueError("Maximum of five coaches reached. Edit or delete one.")
            import secrets
            identifier="coach-"+secrets.token_hex(6)
            rows.append({"id":identifier,**checked})
        else:rows[matched]={"id":identifier,**checked}
        HOME.mkdir(parents=True,exist_ok=True)
        tmp=FILE.with_suffix(".tmp")
        try:tmp.write_text(json.dumps(rows,indent=2),encoding="utf8");tmp.replace(FILE)
        finally:tmp.unlink(missing_ok=True)
        return {"coaches":rows,"limit":COACH_LIMIT}
def delete_coach(identifier):
    with LOCK:
        rows=coaches()
        nxt=[x for x in rows if x.get("id")!=identifier]
        if len(nxt)==len(rows):raise ValueError("Unknown coach")
        HOME.mkdir(parents=True,exist_ok=True)
        tmp=FILE.with_suffix(".tmp")
        try:tmp.write_text(json.dumps(nxt,indent=2),encoding="utf8");tmp.replace(FILE)
        finally:tmp.unlink(missing_ok=True)
        return {"coaches":nxt,"limit":COACH_LIMIT}
def active_coach():
    rows=coaches()
    try:
        selected=json.loads(ACTIVE_FILE.read_text("utf8")).get("id")
        if any(x["id"]==selected for x in rows):return selected
    except (OSError,ValueError,AttributeError):pass
    return rows[0]["id"] if rows else None

def select_active_coach(identifier):
    with LOCK:
        if identifier not in {x["id"] for x in coaches()}:
            raise ValueError("Choose a saved coach")
        HOME.mkdir(parents=True,exist_ok=True)
        tmp=ACTIVE_FILE.with_suffix(".tmp")
        try:tmp.write_text(json.dumps({"id":identifier}),encoding="utf8");tmp.replace(ACTIVE_FILE)
        finally:tmp.unlink(missing_ok=True)
        return {"activeCoach":identifier}

def roster():
    return {"bots":BOT_ROSTER,"coaches":coaches(),"coachCast":COACH_CAST,"activeCoach":active_coach(),"coachLimit":COACH_LIMIT,
      "voices":list(KOKORO_VOICES),"disclaimer":"Fictional personas; Stockfish chooses all moves. Skill numbers and thinking budgets are not calibrated human Elo ratings."}
