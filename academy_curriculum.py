"""Chess Vision Academy — self-contained, board-verified visual micro-lessons.

The examples are original, manually assembled chess positions. All claimed
patterns are rechecked with python-chess at startup. The public starter
curriculum does not require Chess.com credentials, OCR books, or user games.
"""
from __future__ import annotations
import datetime as dt
import json
import random
import hashlib
from pathlib import Path
import sqlite3
import chess
from chess_grind import db

def pos(pieces,turn="w"):
    """Create a legal, explicit position from a compact piece/square dictionary."""
    board=chess.Board(None)
    for square,symbol in pieces.items():
        board.set_piece_at(chess.parse_square(square),chess.Piece.from_symbol(symbol))
    board.turn=(turn=="w")
    board.castling_rights=0
    board.ep_square=None
    board.halfmove_clock=0
    board.fullmove_number=1
    if not board.is_valid():
        raise ValueError("Illegal authored Academy board: "+str(pieces))
    return board.fen()

def boards(white_king="g1",black_king="h8",**pieces):
    return pos({white_king:"K",black_king:"k",**pieces})

UNITS=[
 {"id":"forks","title":"Spot the fork","label":"Tactical vision","symbol":"♞","level":1,
  "tagline":"One move. Two threats.","principle":"A fork occurs when a single piece attacks two or more targets at once. Knights are especially good at it because they jump over pieces.",
  "habit":"Before moving a knight, imagine every square it could jump to and scan for two valuable enemy targets.",
  "kind":"fork",
  "demo":{"fen":boards(b1="N",b5="q",e4="r"),"answer":"c3",
    "origin":"b1","prompt":"Watch the knight jump to c3. Which two pieces does it attack?",
    "why":"From c3, the knight attacks the queen on b5 and the rook on e4 simultaneously.",
    "targets":["b5","e4"]},
  "checks":[
    {"id":"forks-a","fen":boards(f3="N",f7="q",c4="r"),"answer":"e5","origin":"f3",
     "prompt":"Move the white knight to a square where it would attack both the queen and rook.",
     "why":"The knight on e5 attacks f7 and c4 at once.","targets":["f7","c4"]},
    {"id":"forks-b","fen":boards(white_king="h2",d2="N",b6="q",e5="r"),"answer":"c4","origin":"d2",
     "prompt":"Find the knight's destination that attacks both black major pieces.",
     "why":"After Nc4, the knight attacks the queen on b6 and rook on e5.","targets":["b6","e5"]}
  ]},
 {"id":"pins","title":"Understand the pin","label":"Tactical vision","symbol":"♝","level":2,
  "tagline":"A piece that cannot safely move.","principle":"An absolute pin holds a piece to its king. Moving the pinned piece off the attack line would expose the king, so it cannot legally leave that line.",
  "habit":"Trace bishop, rook and queen lines. Ask what valuable piece stands immediately behind the target.",
  "kind":"pin",
  "demo":{"fen":boards(black_king="e8",c4="B",c6="n"),"answer":"b5","origin":"c4",
   "prompt":"Move the bishop to b5 to pin the knight on c6 against the king on e8.",
   "why":"The bishop attacks along b5–c6–d7–e8. The black knight cannot leave the line without exposing its king.",
   "targets":["c6","e8"]},
  "checks":[
    {"id":"pins-a","fen":boards(black_king="e8",g2="B",d7="n"),"answer":"c6","origin":"g2",
      "prompt":"Where can the bishop move to pin the knight on d7 to the king on e8?",
      "why":"The bishop on c6 points through the knight on d7 to the king on e8.",
      "targets":["d7","e8"]},
    {"id":"pins-b","fen":boards(black_king="d7",d3="B",c6="n"),"answer":"b5","origin":"d3",
      "prompt":"Choose a square where the bishop creates an absolute pin on c6.",
      "why":"The bishop on b5 pins the knight on c6 to the king on d7.",
      "targets":["c6","d7"]}
  ]},
 {"id":"loose-pieces","title":"Find loose pieces","label":"Piece safety","symbol":"♜","level":3,
  "tagline":"Loose pieces become tactical targets.","principle":"A loose piece is unprotected. If the opponent attacks it, you may need to move, defend, exchange, or create a stronger threat.",
  "habit":"In every position, scan which pieces are attacked and which are defended—on both sides.",
  "kind":"loose",
  "demo":{"fen":boards(g2="B",b7="r"),"answer":"b7",
   "prompt":"Which black piece is attacked by the bishop and has no black defender?",
   "why":"The bishop on g2 attacks the rook on b7 along f3–e4–d5–c6. Black has no defender of b7.",
   "targets":["g2","b7"]},
  "checks":[
    {"id":"loose-a","fen":boards(a2="B",e6="q",b7="p"),"answer":"e6",
      "prompt":"Tap the black major piece that is attacked and undefended.",
      "why":"The bishop on a2 attacks the queen on e6 through b3–c4–d5, and e6 is not defended by Black.",
      "targets":["a2","e6"]},
    {"id":"loose-b","fen":boards(a1="R",a6="b",f7="p"),"answer":"a6",
      "prompt":"Which black piece is directly attacked by your rook and not defended?",
      "why":"The rook on a1 attacks the bishop on a6 up the open a-file, and no black piece protects a6.",
      "targets":["a1","a6"]}
  ]},
 {"id":"center","title":"Own the center","label":"Opening principles","symbol":"♟","level":4,
  "tagline":"Make space for your pieces.","principle":"The four central squares—d4, e4, d5, and e5—often make your pieces more active. A useful pawn advance can claim space and open lines for bishops and queens.",
  "habit":"Before a flank pawn move, check whether a central pawn advance improves your position.",
  "kind":"center",
  "demo":{"fen":boards(white_king="e1",black_king="e8",e2="P",f1="B",d1="Q"),"answer":"e4","origin":"e2",
   "prompt":"Advance the e-pawn from e2 to e4 to occupy the center.",
   "why":"e4 occupies a central square and opens the bishop's diagonal from f1.",
   "targets":["e2","e4"]},
  "checks":[
    {"id":"center-a","fen":boards(white_king="e1",black_king="e8",d2="P",c1="B",d1="Q"),"answer":"d4","origin":"d2",
      "prompt":"Which square can the d-pawn advance to, claiming central space and opening the c1 bishop?",
      "why":"d4 occupies the center, and moving the pawn off d2 frees the bishop's diagonal from c1.",
      "targets":["d2","d4"]},
    {"id":"center-b","fen":pos({"e1":"K","e8":"k","e7":"p","f8":"b","d8":"q"},turn="b"),
      "answer":"e5","origin":"e7",
      "prompt":"As Black, advance the e-pawn two squares to claim central space.",
      "why":"...e5 occupies the center and opens the f8 bishop's diagonal.",
      "targets":["e7","e5"]}
  ]},
 {"id":"passed-pawns","title":"Recognize passed pawns","label":"Endgame vision","symbol":"♙","level":5,
  "tagline":"Find the pawn no enemy pawn can stop.","principle":"A pawn is passed if there is no enemy pawn ahead of it on its file or either adjacent file. Passed pawns can become powerful promotion threats, but they may still be blocked by pieces.",
  "habit":"In simplified positions, identify passed pawns before counting the promotion race.",
  "kind":"passed",
  "demo":{"fen":boards(e5="P",g6="p"),"answer":"e5",
    "prompt":"Tap White's passed pawn.",
    "why":"No black pawn is ahead of e5 on the d-, e-, or f-files. The black pawn on g6 is too far away.",
    "targets":["e5"]},
  "checks":[
    {"id":"passed-a","fen":boards(a6="P",c5="p"),"answer":"a6",
      "prompt":"Which white pawn is passed?",
      "why":"No enemy pawn lies ahead of a6 on the a- or b-file.",
      "targets":["a6"]},
    {"id":"passed-b","fen":pos({"g1":"K","h8":"k","e3":"p","a2":"P","h2":"P"},turn="b"),
      "answer":"e3",
      "prompt":"As Black, tap the passed pawn.",
      "why":"The black e3-pawn has no white pawn ahead of it on d, e, or f. It still needs support to promote.",
      "targets":["e3"]}
  ]},
 {"id":"opposition","title":"See king opposition","label":"Endgame vision","symbol":"♚","level":6,
  "tagline":"One square between the kings.","principle":"In direct opposition, the kings face each other along a rank or file with one square between them. In many king-and-pawn endings, the side that must move gives way—but pawn tempi and the full position matter.",
  "habit":"When kings face each other, count their separating squares and identify who moves next.",
  "kind":"opposition",
  "demo":{"fen":pos({"e4":"K","e6":"k","a2":"P","h7":"p"}),"answer":"e5",
    "prompt":"Look at the two kings. Tap the empty square directly between them.",
    "why":"The kings are on e4 and e6, with e5 between them. This is direct opposition.",
    "targets":["e4","e6"]},
  "checks":[
    {"id":"opposition-a","fen":pos({"c3":"K","c5":"k","a2":"P","h7":"p"}),"answer":"c4",
      "prompt":"Tap the empty square between the opposing kings.",
      "why":"The kings on c3 and c5 face each other across c4.",
      "targets":["c3","c5"]},
    {"id":"opposition-b","fen":pos({"g4":"K","g6":"k","a2":"P","h7":"p"}),"answer":"g5",
      "prompt":"Where is the intervening square in this opposition?",
      "why":"The kings face each other across g5. The side to move still matters strategically.",
      "targets":["g4","g6"]}
  ]}
]

# Extra positions are constructed from verified original examples, then individually
# checked for legality and for the claimed chess pattern. Original question IDs persist.
SESSION_SIZE=12
BANK_TARGET=500
def _shift(square,dx,dy,flip=False):
    f=chess.square_file(chess.parse_square(square))
    r=chess.square_rank(chess.parse_square(square))
    if flip:f=7-f
    f+=dx;r+=dy
    if not (0<=f<8 and 0<=r<8):return None
    return chess.square_name(chess.square(f,r))

def _variation(unit,seed,dx,dy,flip,extras=()):
    base=chess.Board(seed["fen"])
    mapped={}
    for old,piece in base.piece_map().items():
        to=_shift(chess.square_name(old),dx,dy,flip)
        if to is None or to in mapped:return None
        mapped[to]=piece.symbol()
    origin=_shift(seed["origin"],dx,dy,flip) if seed.get("origin") else None
    answer=_shift(seed["answer"],dx,dy,flip)
    targets=[_shift(t,dx,dy,flip) for t in seed["targets"]]
    if not answer or (origin is None and seed.get("origin")) or any(t is None for t in targets):return None
    for sq,piece in extras:
        if sq in mapped:return None
        mapped[sq]=piece
    try: fen=pos(mapped,"w" if base.turn else "b")
    except ValueError:return None
    kind=unit["kind"]
    if kind=="fork":
        prompt="Find the knight move that attacks two enemy pieces at once."
        why=f"The knight jumps from {origin} to {answer}, forking the pieces on {targets[0]} and {targets[1]}."
    elif kind=="pin":
        prompt="Move the bishop to make an absolute pin against the enemy king."
        why=f"The bishop on {answer} pins the piece on {targets[0]} against the king on {targets[1]}."
    elif kind=="loose":
        prompt="Tap the attacked enemy piece that has no defender."
        why=f"The enemy piece on {answer} is attacked but not protected by its own side."
    elif kind=="center":
        prompt="Find the central pawn advance that claims space and opens development."
        why=f"The pawn advances from {origin} to {answer} and establishes central presence."
    elif kind=="passed":
        prompt="Tap the passed pawn: no enemy pawn ahead on its file or adjacent files."
        why=f"The pawn on {answer} has no enemy pawn ahead on its file or either neighboring file."
    else:
        prompt="Tap the empty square separating the two kings in direct opposition."
        why=f"The kings face each other across {answer}; the side to move influences the endgame."
    entry={"fen":fen,"answer":answer,"prompt":prompt,"why":why,"targets":targets}
    if origin:entry["origin"]=origin
    try:_validate_item(unit,entry,kind)
    except (ValueError,AssertionError):return None
    return entry

def _expand_banks():
    packaged=Path(__file__).resolve().parent/"data"/"academy_practice_bank_v4.json"
    if packaged.is_file():
        bank=json.loads(packaged.read_text(encoding="utf8"))
        for unit in UNITS:
            rows=bank[unit["id"]]
            if len(rows)!=BANK_TARGET-2:raise ValueError("Incomplete Academy bank: "+unit["id"])
            unit["checks"].extend(rows)
        return
    # Source-checkout fallback (deterministic; slow). Distribution includes packaged data.
    for unit in UNITS:
        original=list(unit["checks"])
        occupied={x["fen"].split(" ")[0] for x in [unit["demo"]]+original}
        rng=random.Random("chessgrind-academy-bank-v2-"+unit["id"])
        results=[]
        # Chess-relevant geometric shifts first, then add unobtrusive context pieces
        # if needed (especially central pawn lessons, whose destination is fixed).
        for attempt in range(260000):
            seed=original[attempt%len(original)]
            dx=rng.randint(-5,5);dy=rng.randint(-5,5);flip=bool(rng.randrange(2))
            extras=()
            if attempt>600 or unit["kind"]=="center":
                options=[("a2","P"),("b2","P"),("g2","P"),("h2","P"),
                         ("a7","p"),("b7","p"),("g7","p"),("h7","p")]
                rng.shuffle(options)
                if len(results)>=98:
                    # Broad context: pawn clutter throughout legal ranks creates genuinely
                    # different visual scenes, with every answer revalidated afterward.
                    options=[(chess.square_name(chess.square(file,rank)),symbol)
                             for file in range(8) for rank in range(1,7)
                             for symbol in ("P","p")]
                    rng.shuffle(options)
                    extras=tuple(options[:rng.randint(1,5)])
                else:
                    extras=tuple(options[:rng.randint(1,3)])
            item=_variation(unit,seed,dx,dy,flip,extras)
            if item is None:continue
            placement=item["fen"].split(" ")[0]
            if placement in occupied:continue
            occupied.add(placement)
            item["id"]=unit["id"]+"-extra-"+str(len(results)+1).zfill(3)
            results.append(item)
            if len(results)>=BANK_TARGET-len(original):break
        unit["checks"].extend(results)
        if len(unit["checks"])<BANK_TARGET:
            raise RuntimeError("Insufficient verified Academy positions for "+unit["id"]+
                               ": "+str(len(unit["checks"])))

def _session_ids(unit,events):
    seen={}
    for event in events:
        key=event["challenge_id"]
        row=seen.setdefault(key,{"attempts":0,"correct":0,"last":""})
        row["attempts"]+=1
        row["correct"]+=int(bool(event["correct"]) and not bool(event["assisted"]))
        row["last"]=event["at"]
    candidates=list(unit["checks"])
    # Randomize ties, prefer never-seen examples, then missed/assisted questions,
    # then older practice. The returned IDs remain fixed for this session.
    random.SystemRandom().shuffle(candidates)
    candidates.sort(key=lambda x:(seen.get(x["id"],{}).get("correct",0)>0,
                                  seen.get(x["id"],{}).get("last","")))
    return [x["id"] for x in candidates[:SESSION_SIZE]]

INDEX={unit["id"]:unit for unit in UNITS}
COUNT=0  # Filled after verified bank expansion

def _validate_item(unit,item,kind):
    board=chess.Board(item["fen"])
    if not board.is_valid():raise ValueError("Invalid authored board "+unit["id"])
    sq=chess.parse_square(item["answer"])
    if kind in ("fork","pin","center"):
        origin=chess.parse_square(item["origin"])
        move=chess.Move(origin,sq)
        if move not in board.legal_moves:raise ValueError(unit["id"]+" illegal move "+move.uci())
        after=board.copy();after.push(move)
        if kind=="fork":
            victims=[t for t in item["targets"] if
                     after.piece_at(chess.parse_square(t)) and
                     after.piece_at(chess.parse_square(t)).color!=board.turn and
                     chess.parse_square(t) in after.attacks(sq)]
            if len(victims)<2:raise ValueError(unit["id"]+" not a verified fork")
        if kind=="pin":
            if not any(after.is_pinned(not board.turn,chess.parse_square(t))
                       for t in item["targets"] if after.piece_at(chess.parse_square(t)) and
                           after.piece_at(chess.parse_square(t)).color!=board.turn):
                raise ValueError(unit["id"]+" not an absolute pin")
        if kind=="center" and not (board.piece_at(origin).piece_type==chess.PAWN and
                                  chess.square_name(sq) in ("e4","d4","e5","d5")):
            raise ValueError("Not a central pawn advance")
    elif kind=="loose":
        victim=board.piece_at(sq)
        if not victim or victim.color==board.turn or victim.piece_type==chess.KING:
            raise ValueError("Missing opponent piece")
        if not board.is_attacked_by(board.turn,sq) or board.is_attacked_by(victim.color,sq):
            raise ValueError("Not an attacked, unprotected piece")
    elif kind=="passed":
        pawn=board.piece_at(sq)
        if not pawn or pawn.piece_type!=chess.PAWN or pawn.color!=board.turn:
            raise ValueError("Invalid passed pawn")
        f=chess.square_file(sq);r=chess.square_rank(sq)
        for other,p in board.piece_map().items():
            if p.piece_type!=chess.PAWN or p.color==pawn.color:continue
            if abs(chess.square_file(other)-f)<=1 and (
                chess.square_rank(other)>r if pawn.color else chess.square_rank(other)<r):
                raise ValueError("Not a passed pawn")
    elif kind=="opposition":
        wk,bk=board.king(chess.WHITE),board.king(chess.BLACK)
        a,b=(chess.square_file(wk),chess.square_rank(wk)),(chess.square_file(bk),chess.square_rank(bk))
        if not ((a[0]==b[0] and abs(a[1]-b[1])==2) or
                (a[1]==b[1] and abs(a[0]-b[0])==2)):
            raise ValueError("Not direct opposition")
        middle=chess.square((a[0]+b[0])//2,(a[1]+b[1])//2)
        if sq!=middle or board.piece_at(middle):raise ValueError("Not the king opposition square")
    else:raise ValueError("Unknown curriculum kind")
    return True

def validate():
    seen=set()
    for unit in UNITS:
        assert unit["id"] not in seen
        seen.add(unit["id"])
        for item in [unit["demo"]]+unit["checks"]:
            _validate_item(unit,item,unit["kind"])
        fens=[x["fen"].split(" ")[0] for x in [unit["demo"]]+unit["checks"]]
        if len(set(fens))<3:raise ValueError("Demonstration reused as a test")
    return True

_expand_banks()
COUNT=sum(len(u["checks"]) for u in UNITS)
validate()
def ensure(con):
    con.executescript("""CREATE TABLE IF NOT EXISTS academy_attempts(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       lesson_id TEXT NOT NULL,
       challenge_id TEXT NOT NULL,
       answer TEXT NOT NULL,
       correct INTEGER NOT NULL,
       assisted INTEGER NOT NULL,
       seconds REAL NOT NULL,
       at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS academy_attempts_lesson
        ON academy_attempts(lesson_id,at);
    """)
    con.commit()

def _rows(con,unit_id):
    return [dict(r) for r in con.execute(
        "SELECT challenge_id,correct,assisted,seconds,at FROM academy_attempts WHERE lesson_id=? ORDER BY id",
        (unit_id,))]

def status(unit,events):
    """First pass means 2 independently correct on distinct test boards.
    Confirmed requires a delayed, unaided independent check on another day."""
    checks={x["id"] for x in unit["checks"][:2]}
    fresh=[r for r in events if r["challenge_id"] in {x["id"] for x in unit["checks"]} and r["correct"] and not r["assisted"]]
    # Distinct correct boards can be solved on separate days; the day the
    # last needed board is first solved is the initial completion date.
    first_by_challenge={}
    for row in fresh:
        if row["challenge_id"] in checks:first_by_challenge.setdefault(row["challenge_id"],row["at"][:10])
    legacy_day=max(first_by_challenge.values()) if len(first_by_challenge)==len(checks) else None
    all_correct={r["challenge_id"]:r["at"][:10] for r in fresh}
    # Preserve early beta achievements, but new learners need twelve distinct boards.
    first_day=legacy_day or (max(all_correct.values()) if len(all_correct)>=SESSION_SIZE else None)
    # Do not confuse learned-on-retry with unseen first-try recognition.
    first_attempts={}
    for row in events:
        if row["challenge_id"] in checks and row["challenge_id"] not in first_attempts:
            first_attempts[row["challenge_id"]]=row
    first_try_pass=bool(len(first_attempts)==len(checks) and
        all(r["correct"] and not r["assisted"] for r in first_attempts.values()))
    confirmed=bool(first_day and any(r["at"][:10]>first_day for r in fresh))
    coverage=len({r["challenge_id"] for r in events})
    unique_correct=len({r["challenge_id"] for r in fresh})
    return {"state":"retained" if confirmed else "practice-complete" if first_day else
           "in-progress" if events else "not-started",
      "firstPassDate":first_day,"firstTryPass":first_try_pass,"confirmed":confirmed,
      "independentCorrect":len(fresh),"uniqueCorrect":unique_correct,"coverage":coverage,
      "totalAttempts":len(events),
      "lastAttempt":events[-1]["at"] if events else None}

def overview():
    con=db();ensure(con)
    results=[]
    try:
        for unit in UNITS:
            result=status(unit,_rows(con,unit["id"]))
            results.append({"id":unit["id"],"title":unit["title"],
                "label":unit["label"],"level":unit["level"],
                "symbol":unit["symbol"],"tagline":unit["tagline"],
                "principle":unit["principle"],"habit":unit["habit"],
                "checks":len(unit["checks"]),"sessionSize":SESSION_SIZE,**result})
        return {"units":results,"total":len(UNITS),
             "completed":sum(x["state"] in ("practice-complete","retained") for x in results),
             "retained":sum(x["confirmed"] for x in results),
              "method":"Twelve distinct independently correct boards earn a new practice milestone. Existing beta milestones are preserved. Every session brings less-practiced positions; delayed checks are tracked separately."}
    finally:con.close()

def _presentation(item,kind,reveal=False):
    data={"fen":item["fen"],"prompt":item["prompt"],
          "kind":kind,"side":"White" if chess.Board(item["fen"]).turn else "Black"}
    if reveal:
        data.update({"answer":item["answer"],"why":item["why"],
                     "targets":item["targets"],"origin":item.get("origin")})
        if kind in ("fork","pin","center"):
            board=chess.Board(item["fen"])
            move=chess.Move(chess.parse_square(item["origin"]),
                            chess.parse_square(item["answer"]))
            data["candidateSan"]=board.san(move)
            board.push(move)
            data["afterFen"]=board.fen()
    return data

def lesson(unit_id):
    if unit_id not in INDEX:raise ValueError("Unknown Academy lesson")
    unit=INDEX[unit_id]
    con=db();ensure(con)
    try:
        events=_rows(con,unit_id)
        progress=status(unit,events)
        selected=_session_ids(unit,events)
    finally:con.close()
    return {"id":unit_id,"title":unit["title"],"label":unit["label"],
            "symbol":unit["symbol"],"level":unit["level"],
            "tagline":unit["tagline"],"principle":unit["principle"],
            "habit":unit["habit"],"kind":unit["kind"],"progress":progress,
            "demo":_presentation(unit["demo"],unit["kind"],True),
            "testCount":len(selected),"bankSize":len(unit["checks"]),"challengeIds":selected}

def challenge(unit_id,number,challenge_id=None):
    if unit_id not in INDEX:raise ValueError("Unknown Academy lesson")
    unit=INDEX[unit_id]
    if challenge_id:
        item=next((x for x in unit["checks"] if x["id"]==challenge_id),None)
        if item is None:raise ValueError("Unknown Academy test position")
    else:
        if not isinstance(number,int) or number<0 or number>=len(unit["checks"]):
            raise ValueError("Unknown Academy test position")
        item=unit["checks"][number]
    return {"id":item["id"],"unitId":unit_id,"number":number+1,
            "total":len(unit["checks"]),**_presentation(item,unit["kind"])}

def answer(unit_id,challenge_id,chosen,assisted=False,seconds=0):
    if unit_id not in INDEX:raise ValueError("Unknown Academy lesson")
    unit=INDEX[unit_id]
    item=next((x for x in unit["checks"] if x["id"]==challenge_id),None)
    if item is None:raise ValueError("Unknown Academy challenge")
    if not isinstance(chosen,str) or len(chosen)!=2 or chosen[0] not in "abcdefgh" or chosen[1] not in "12345678":
        raise ValueError("Choose a valid square on the board")
    if not isinstance(assisted,bool):raise ValueError("Invalid assistance flag")
    try:duration=float(seconds)
    except (TypeError,ValueError):raise ValueError("Invalid duration")
    correct=chosen==item["answer"]
    con=db();ensure(con)
    con.execute("INSERT INTO academy_attempts(lesson_id,challenge_id,answer,correct,assisted,seconds,at) VALUES(?,?,?,?,?,?,?)",
        (unit_id,challenge_id,chosen,int(correct),int(assisted),max(0,min(duration,3600)),
         dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
    con.commit()
    current=status(unit,_rows(con,unit_id))
    con.close()
    shown=_presentation(item,unit["kind"],True)
    return {"correct":correct,"assisted":assisted,"answer":item["answer"],
        "why":item["why"],"targets":item["targets"],
        "origin":item.get("origin"),"afterFen":shown.get("afterFen"),
        "candidateSan":shown.get("candidateSan"),
        "state":current["state"],
        "progress":current,
        "message":("Exactly. "+item["why"] if correct else
                   "Not quite. "+item["why"]),
        "nextHabit":unit["habit"]}

def hint(unit_id,number):
    if unit_id not in INDEX:raise ValueError("Unknown Academy lesson")
    unit=INDEX[unit_id];item=unit["checks"][number]
    texts={"fork":"Trace every square the knight could reach, then count its targets.",
      "pin":"Trace the bishop's diagonal. Which destination lines up the knight and king?",
      "loose":"Find the enemy piece that is attacked. Then check whether another enemy piece defends it.",
      "center":"Look for a pawn that can occupy d4, e4, d5, or e5 and activate a bishop.",
      "passed":"Look ahead on the pawn's own and neighboring files for enemy pawns.",
      "opposition":"Look at the file or rank shared by both kings. Find the empty square between them."}
    return {"hint":texts[unit["kind"]]}
