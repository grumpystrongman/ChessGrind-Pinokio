"""Local evidence-backed chess tutor, using the games and licensed book passages."""
import datetime as dt
import json
import re
from chess_grind import db
from coaching import training,TOPIC_TERMS
from daily_coach import FUNDAMENTALS

def ensure(con):
    con.execute("""CREATE TABLE IF NOT EXISTS tutor_chat(
      id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL,
      asked_at TEXT NOT NULL,question TEXT NOT NULL,response TEXT NOT NULL)""")
    con.commit()

TRIGGERS={
    "piece safety":("blunder","hanging","protect","undefended","losing pieces","hang "),
    "forks and double attacks":("fork","double attack","knight tactic"),
    "pins":("pin","pinned"),
    "opening decisions":("opening","develop","first move","italian","queen's gambit"),
    "endgame technique":("endgame","king and pawn","opposition","rook ending"),
    "missed captures":("capture","material","exchange"),
    "forcing checks":("check","mate"),
    "calculation":("calculate","think","visual","tactic","plan","improve","training"),
}

def topic_for(question,default):
    q=question.lower()
    for label,words in TRIGGERS.items():
        if any(word in q for word in words):return label
    return default

def respond(question,username="player",save=True):
    question=" ".join(str(question).split())
    if not 3<=len(question)<=1000:raise ValueError("Question must have 3–1000 characters.")
    con=db();ensure(con)
    p=training(username)
    baseline=p["topics"][0]["topic"] if p["topics"] else "piece safety"
    topic=topic_for(question,baseline)
    heading,principle=FUNDAMENTALS.get(topic,FUNDAMENTALS["calculation"])
    from game_analysis import dashboard_data
    games=dashboard_data(username)
    from motifs import classify
    matching=[m for m in games["mistakes"] if classify(m)["topic"]==topic]
    examples=sorted(matching,key=lambda m:m["loss"],reverse=True)[:2]
    sources=[]
    try:
        from semantic_index import search,status
        if status()["embedded"]:
            sources=search("A chess coach explains "+topic+". "+question,limit=3)
    except (ImportError,RuntimeError,ValueError,OSError):
        pass
    if not sources:
        sources=p.get("bookLessons",[])[:2]
    exact=("I can connect this to "+len(games["games"]).__str__()+
      " analyzed games, but more games will make the patterns more reliable.")
    pieces=[
      heading+". "+principle,
      exact,
    ]
    if matching:
        pieces.append(f"This category currently appears in {len(matching)} of your flagged move decisions.")
        for m in examples:
            pieces.append("Example: against "+m["opponent"]+
             ", you played "+m["move"]+" where Stockfish preferred "+m["best"]+
             ". Evaluation loss: about "+str(round(m["loss"]/100,1))+" pawns. "+
             classify(m)["evidence"])
    else:
        pieces.append("I haven't found a reliably labeled instance of this theme in your imported games yet.")
    pieces.append("Your drill: spend 60 seconds finding two candidate moves, calculate an opponent reply to each, then choose. Do not reveal Stockfish until you've committed.")
    if sources:
        best=sources[0]
        pieces.append("Reading (complete excerpt): "+best["title"]+" — "+best["body"])
    result={"question":question,"topic":topic,"heading":heading,
      "answer":"\n\n".join(pieces),
      "sources":[{"title":r["title"],"author":r.get("author"),"url":r["url"],
                  "passage":r["body"],"similarity":r.get("similarity")} for r in sources],
      "examples":[{"fen":m["fen"],"color":m["color"],"played":m["move"],
                   "best":m["best"],"opponent":m["opponent"]} for m in examples],
      "engineDepthNote":"Move evaluations are approximate, and categories are inferred from legal board geometry."}
    if save:
        con.execute("""INSERT INTO tutor_chat(username,asked_at,question,response)
          VALUES(?,datetime('now'),?,?)""",(username,question,json.dumps(result)))
        con.commit()
    return result

def history(username="player",count=12):
    con=db();ensure(con)
    return [dict(r) for r in con.execute("""SELECT id,asked_at,question
          FROM tutor_chat WHERE username=? ORDER BY id DESC LIMIT ?""",
          (username,count)).fetchall()]

if __name__=="__main__":
    print(json.dumps(respond("What am I doing wrong?"),indent=2))
