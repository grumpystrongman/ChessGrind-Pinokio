"""Daily structured chess-coaching sessions, completion and rating history."""
import datetime as dt
import json
from chess_grind import db
from coaching import training
from chesscom_api import status

FUNDAMENTALS={
    "calculation":("Calculate, don't guess",
       "Before moving, choose two candidates. Calculate checks, captures and threats for both sides, then compare the final positions."),
    "opening decisions":("Develop with a purpose",
       "Control central squares, develop your knights and bishops, keep your king safe, and avoid moving the same piece repeatedly without a concrete reason."),
    "missed captures":("Account for every loose piece",
       "Scan all forcing captures, including ones by your opponent. Count attackers and defenders before committing."),
    "piece safety":("The 3-second blunder check",
       "After choosing a move, imagine it has already been played. Ask what your opponent would capture or check next."),
    "forcing checks":("Checks demand attention",
       "Check all legal forcing checks, but never give a check just because it exists. Calculate the forced replies."),
    "pins":("The piece behind the piece",
       "When a bishop, rook or queen lines up with two enemy pieces, identify what cannot safely move."),
    "forks and double attacks":("Attack two targets",
       "Look for knight, pawn and queen moves that attack two valuable targets at once, especially a king and queen or rook."),
    "checkmate patterns":("Find forcing mate nets",
       "Calculate checks first. Inspect escape squares, defenders, and whether your checking piece can be captured."),
    "endgame technique":("Activate your king",
       "In simple endings, the king becomes an attacking piece. Study opposition, pawn squares and promotion races."),
}

def ensure(con):
    con.executescript("""CREATE TABLE IF NOT EXISTS daily_tasks(
      username TEXT NOT NULL,day TEXT NOT NULL,task_id TEXT NOT NULL,
      completed_at TEXT,PRIMARY KEY(username,day,task_id));
    CREATE TABLE IF NOT EXISTS rating_snapshots(
      username TEXT NOT NULL,day TEXT NOT NULL,rating INTEGER,
      PRIMARY KEY(username,day));""")
    con.commit()

def today(username="player",day=None):
    day=day or dt.date.today().isoformat()
    parsed=dt.date.fromisoformat(day)
    con=db();ensure(con)
    student=status(con,username)
    rating=student.get("rapid_rating")
    if isinstance(rating,int):
        con.execute("""INSERT OR REPLACE INTO rating_snapshots VALUES(?,?,?)""",
                    (username,day,rating))
        con.commit()
    t=training(username)
    priority=t["topics"][0]["topic"] if t["topics"] else "piece safety"
    secondary=t["topics"][1]["topic"] if len(t["topics"])>1 else "calculation"
    heading,explanation=FUNDAMENTALS.get(priority,FUNDAMENTALS["calculation"])
    book=t["bookLessons"][0] if t["bookLessons"] else None
    play_day=parsed.weekday() in (0,2,4,5)
    tasks=[
      {"id":"review","minutes":10,"name":"Learn from yesterday",
       "description":"Replay two lost positions and explain your original choice before revealing Stockfish's line.",
       "action":"reviews"},
      {"id":"practice","minutes":15 if not play_day else 10,
       "name":"Personal tactical repair",
       "description":"Train threat spotting, three-move prediction and unseen-position transfer for "+priority+".",
       "action":"learning_lab"},
      {"id":"study","minutes":15 if not play_day else 5,
       "name":"Read and teach it back",
       "description":"Read a sourced chess-book excerpt on "+priority+" and write one sentence you could use in your next game.",
       "action":"lab_books"},
      {"id":"endgame","minutes":20 if not play_day else 5,
       "name":"Fundamentals drill",
       "description":"Practice "+secondary+": "+FUNDAMENTALS.get(secondary,FUNDAMENTALS["calculation"])[1],
       "action":"learning_lab"},
      {"id":"games","minutes":0 if not play_day else 30,
       "name":"One serious Rapid game" if play_day else "One annotated game",
       "description":"Play 15|10, then review your decisions before the engine." if play_day
            else "Review a previous Rapid loss and explain every missed forcing move.",
       "action":"reviews"}]
    # Both training variants total 60 minutes (game-day 10+10+5+5+30).
    for task in tasks:
        if not play_day and task["id"]=="games":task["minutes"]=0
    records=con.execute("SELECT task_id,completed_at FROM daily_tasks WHERE username=? AND day=?",
                        (username,day)).fetchall()
    completed={r["task_id"]:r["completed_at"] for r in records}
    for task in tasks:
        task["completed"]=task["id"] in completed
        task["completedAt"]=completed.get(task["id"])
    history=[dict(r) for r in con.execute("""SELECT day,rating FROM rating_snapshots
      WHERE username=? ORDER BY day DESC LIMIT 100""",(username,)).fetchall()]
    count=sum(1 for task in tasks if task["completed"])
    return {"date":day,"rating":rating,"goal":1500,
       "name":"Chess Grind · "+heading,
       "principle":explanation,
       "priority":priority,"secondary":secondary,
       "minutes":sum(x["minutes"] for x in tasks),
       "tasks":tasks,"complete":count,"total":len(tasks),
       "gameDay":play_day,"gamesToReview":len(t["queue"]),
       "book":book,"history":list(reversed(history)),
       "practiceAttempts":t["attempts"],"practiceCorrect":t["correct"],
       "mastered":t["mastered"],"confidenceNote":
         "Preliminary patterns: fewer than 30 analyzed Rapid games."
         if len(t["queue"])<120 else "Based on the games currently imported."}

def complete(task_id,completed,username="player"):
    con=db();ensure(con)
    if task_id not in {"review","practice","study","endgame","games"}:
        raise ValueError("Unknown daily task")
    day=dt.date.today().isoformat()
    if completed:
        con.execute("""INSERT INTO daily_tasks(username,day,task_id,completed_at)
          VALUES(?,?,?,datetime('now')) ON CONFLICT(username,day,task_id)
          DO UPDATE SET completed_at=excluded.completed_at""",(username,day,task_id))
    else:
        con.execute("DELETE FROM daily_tasks WHERE username=? AND day=? AND task_id=?",
                    (username,day,task_id))
    con.commit()
    return today(username)
if __name__=="__main__":
    print(json.dumps(today(),indent=2))
