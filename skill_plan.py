"""Evidence-driven coaching plan across Chess Grind's local training tracks."""
from __future__ import annotations
import json
from collections import Counter
from chess_grind import db

LINKS={
    "opening decisions":("/strategy?tab=openings","Opening repertoire"),
    "endgame technique":("/strategy?tab=endgames","Endgame Laboratory"),
    "forks and double attacks":("/academy?lesson=forks","Chess Vision: Forks"),
    "pins":("/academy?lesson=pins","Chess Vision: Pins"),
    "piece safety":("/academy?lesson=loose-pieces","Chess Vision: Loose pieces"),
    "missed captures":("/workshop?topic=missed%20captures","Calculation Workshop"),
    "forcing checks":("/workshop?topic=forcing%20checks","Calculation Workshop"),
    "checkmate patterns":("/academy?lesson=forks","Chess Vision Academy")
}
SKILL_HINTS={
 "opening decisions":"Check development, the central squares, and king safety before committing to an opening move.",
 "endgame technique":"Count pawn moves and king access before committing to an endgame plan.",
 "forks and double attacks":"After each candidate knight jump, count valuable targets rather than looking only for checks.",
 "pins":"Trace bishop, rook, and queen rays through a piece to a more valuable piece behind it.",
 "piece safety":"Ask whether each attacked piece has a defender and which capture would follow.",
 "missed captures":"Scan checks, captures, then forcing threats before choosing a quiet move.",
 "forcing checks":"Checks force a response, but compare the opponent's most resourceful legal reply.",
 "checkmate patterns":"Count all the defender's legal escape squares before calling a position mate."
}

def plan(minutes=20):
 try:minutes=int(minutes)
 except (TypeError,ValueError):raise ValueError("Invalid daily training duration")
 if minutes<10 or minutes>90:raise ValueError("Choose 10 to 90 minutes")
 from calculation_workshop import profile as workshop_profile
 from academy_curriculum import overview as academy_profile
 from opening_repertoire import overview as opening_profile
 from endgame_lab import overview as endgame_profile
 workshop=workshop_profile()
 academy=academy_profile()
 openings=opening_profile()
 endgames=endgame_profile()
 con=db()
 try:
  rows=con.execute("""SELECT difficulty,style,state,outcome,review_json,created_at
        FROM sparring_games WHERE username='player' ORDER BY updated_at DESC LIMIT 25""").fetchall()
 except Exception:
  rows=[]
 finally:con.close()
 reviewed=[];unfinished=0;recent_games=0
 for r in rows:
  if r["state"]=="active":unfinished+=1
  else:recent_games+=1
  if r["review_json"]:
   try:reviewed.append(json.loads(r["review_json"]))
   except (TypeError,ValueError):pass
 # Conservative, explainable strength adaptation. Only consider the last
 # three sufficiently long reviewed games played at a comparable setting.
 levels=["beginner","casual","club","advanced"]
 recommendation="casual"
 strength_note="Casual is the starter setting. After three reviewed games with at least ten decisions each, the coach can suggest a change based on how often your moves are competitive at depth 9."
 qualified=[]
 for row in rows:
  if not row["review_json"]:continue
  try:
   report=json.loads(row["review_json"])
  except (TypeError,ValueError):continue
  if report.get("decisions",0)<10:continue
  if row["difficulty"] not in levels:continue
  qualified.append((row["difficulty"],report))
 if len(qualified)>=3:
  recent=qualified[:3]
  current=recent[0][0]
  comparable=[x for x in recent if x[0]==current]
  if len(comparable)==3:
   total=sum(x[1]["decisions"] for x in comparable)
   strong=sum(x[1]["strong"] for x in comparable)
   percent=100*strong/max(1,total)
   index=levels.index(current)
   if percent>=85 and index<len(levels)-1:
    recommendation=levels[index+1]
    strength_note=f"In three reviewed {current} games, {strong} of {total} decisions were within 0.65 pawns of Stockfish's depth-9 choice. Try a harder opponent if you want a challenge."
   elif percent<55 and index>0:
    recommendation=levels[index-1]
    strength_note=f"In three reviewed {current} games, {strong} of {total} decisions met the depth-limited threshold. Try a gentler opponent while reinforcing the fundamentals."
   else:
    recommendation=current
    strength_note=f"Your last three comparable reviewed games have {strong} of {total} competitive decisions. Staying at {current} is reasonable for now."
  else:
   recommendation=qualified[0][0]
   strength_note="Your last reviewed games use different difficulty settings. Keep the latest setting until three comparable games are available."
 elif qualified:
  recommendation=qualified[0][0]
  strength_note="More reviewed practice is needed before suggesting a difficulty change."
 observed=Counter()
 for r in reviewed:
  for phase,values in r["byPhase"].items():
   observed[phase]+=values["flagged"]
 total_reviewed=sum(r["decisions"] for r in reviewed)
 flagged_reviewed=sum(r["flagged"] for r in reviewed)
 topics=workshop["topics"]
 first=topics[0] if topics else None
 # Priority from historically recurring flagged moves and independent work.
 candidates=[]
 for t in topics:
  label=t["topic"]
  if t["positions"]<2:continue
  focus=(0 if t["dueCount"] else 2)+t["weightedPriority"]*.1
  candidates.append({"topic":label,"evidence":f"{t['positions']} flagged decisions across {t['games']} analyzed games",
    "priority":focus,"next":SKILL_HINTS.get(label,"Calculate the opponent's strongest reply before moving."),
    "url":LINKS.get(label,("/workshop?topic="+label.replace(" ","%20"),"Calculation Workshop"))[0],
    "action":LINKS.get(label,("","Calculation Workshop"))[1],
    "dueCount":t["dueCount"],"basis":"historical game analysis"})
 candidates.sort(key=lambda t:-t["priority"])
 focus=candidates[0] if candidates else None
 # Not every learner has analyzed games; guide to original lessons as fallback.
 if not focus:
  focus={"topic":"Tactical recognition",
         "evidence":"No historical flagged positions have been analyzed",
         "next":"Start by recognizing forks and loose pieces on new boards.",
         "url":"/academy?lesson=forks","action":"Chess Vision Academy",
         "dueCount":0,"basis":"starter curriculum"}
 secondary=next((x for x in candidates[1:] if x["topic"]!=focus["topic"]),None)
 academy_due=[x for x in academy["units"] if x["state"]!="retained"]
 endgame_due=[x for x in endgames["lessons"] if x["accuracy"] is None or x["accuracy"]<75]
 warm=5 if minutes>=20 else 3
 focused=max(5,round(minutes*.45))
 apply=max(3,minutes-warm-focused)
 tasks=[
   {"id":"recognize","minutes":warm,"title":"Warm up your chess vision",
    "why":"Train the patterns before adding the pressure of a full game.",
    "action":"Practice a visual lesson",
    "url":"/academy?lesson="+(academy_due[0]["id"] if academy_due else "forks")},
   {"id":"focus","minutes":focused,"title":"Work on "+focus["topic"],
    "why":focus["evidence"]+". "+focus["next"],"action":"Start targeted practice",
    "url":focus["url"]},
   {"id":"apply","minutes":apply,"title":"Apply it in a training game",
    "why":"Try to recognize the same principle without highlighted squares. Review afterward, not during play.",
    "action":"Play against your local coach","url":"/arena?tab=play"}
 ]
 if reviewed:
  coach_note=("Your last "+str(len(reviewed))+" reviewed practice games contain "+
    str(flagged_reviewed)+" flagged decisions across "+str(total_reviewed)+
    " analyzed player moves. Your most common flagged phase is "+
    (observed.most_common(1)[0][0].lower() if observed else "not yet established")+
    ". These observations help choose practice; they are not an Elo estimate.")
 else:
  coach_note=("You have "+str(workshop["totalFlagged"])+" historically flagged decisions in imported games. "+
   "I recommend starting with "+focus["topic"]+". "+
   ("Resume your unfinished training game when ready." if unfinished else
     "Your first sparring game will give us fresh, directly reviewable decisions."))
 return {"focus":focus,"secondary":secondary,"tasks":tasks,
   "minutes":minutes,"coachNote":coach_note,
   "recommendedDifficulty":recommendation,"difficultyExplanation":strength_note,
   "evidence":{"historicalFlagged":workshop["totalFlagged"],
      "historicalTopics":len(topics),"workshopIndependentAccuracy":workshop["independentAccuracy"],
      "academyCompleted":academy["completed"],"academyTotal":academy["total"],
      "openingSaved":openings["savedPositions"],"endgameAttempts":endgames["attempts"],
      "practiceGamesFinished":recent_games,"practiceGamesReviewed":len(reviewed),
      "practiceGamesActive":unfinished,"reviewedMoves":total_reviewed,
      "reviewFlagged":flagged_reviewed},
   "boundary":"The plan adapts to available recorded evidence; a high count is not a chess rating, and training on repeated positions alone does not establish real-game improvement."}
