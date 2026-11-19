"""Selected documented classic games — only when exact game scores match sources.

These are curricular spotlights. Selection is editorial, but metadata,
players, date, result and entire legal move sequence come from the PGN.
Never silently invent a classic or fill a missing game with a substitute.
"""
from __future__ import annotations
import chess,chess.pgn
from masters_library import RAW,_headers_scan,_id,_sanitize,_winner,_era,ensure,db,PLAYERS
SPECS=[
 ("Anderssen","Anderssen","Kieseritzky",1851,"Immortal","The Immortal Game"),
 ("Anderssen","Anderssen","Dufresne",1852,"Evergreen","The Evergreen Game"),
 ("Fischer","Fischer","Byrne",1956,"Rosenwald","The Game of the Century"),
 ("Kasparov","Kasparov","Topalov",1999,"Hoogovens","Kasparov's attacking masterpiece"),
 ("Lasker","Lasker","Bauer",1889,"Amsterdam","Lasker's double-bishop sacrifice"),
 ("Capablanca","Capablanca","Marshall",1918,"New York","Capablanca faces the Marshall attack"),
 ("Fischer","Fischer","Spassky",1972,"World Championship","Fischer–Spassky championship battle"),
 ("Tal","Tal","Botvinnik",1960,"World Championship","Tal–Botvinnik championship"),
 ("Kasparov","Kasparov","Karpov",1985,"World Championship","Kasparov–Karpov championship"),
 ("Carlsen","Carlsen","Anand",2013,"World Championship","Carlsen–Anand championship"),
]
def import_landmarks():
 con=db();ensure(con)
 imported=[];missing=[]
 try:
  for file,player1,player2,year,event_hint,title in SPECS:
   path=RAW/(file+".pgn")
   if not path.exists():missing.append(title);continue
   candidates=[r for r in _headers_scan(path)
      if r["year"]==year and player1.casefold() in (r["white"]+" "+r["black"]).casefold()
      and player2.casefold() in (r["white"]+" "+r["black"]).casefold()
      and event_hint.casefold() in r["event"].casefold()]
   if not candidates:missing.append(title);continue
   # In the same championship, select a decisive game if one exists.
   if title=="Kasparov's attacking masterpiece":
    candidates=[r for r in candidates if r["white"].startswith("Kasparov") and
                r["black"].startswith("Topalov") and r["result"]=="1-0"]
   if len(candidates)>1:
    decisive=[r for r in candidates if r["result"] in ("1-0","0-1")]
    if decisive:candidates=decisive
   if not candidates:missing.append(title);continue
   chosen=candidates[0]
   with path.open("r",encoding="utf-8-sig",errors="replace") as handle:
    handle.seek(chosen["offset"]);g=chess.pgn.read_game(handle)
   if not g or g.errors:missing.append(title);continue
   b=g.board();ucis=[]
   for mv in g.mainline_moves():
    if mv not in b.legal_moves:break
    ucis.append(mv.uci());b.push(mv)
   if not 12<=len(ucis)<=350:missing.append(title);continue
   h=g.headers;identity=_id(h,ucis)
   clean=g.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=False))
   # Preserve exact game headers; only the curated study-title is editorial.
   con.execute("""INSERT OR IGNORE INTO master_games
    (id,white,black,event,site,date,year,result,eco,opening,plies,winner,era,
    source_player,source_url,featured,feature_reason,pgn)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (identity,_sanitize(h.get("White")),_sanitize(h.get("Black")),
     _sanitize(h.get("Event"),200),_sanitize(h.get("Site"),140),
     _sanitize(h.get("Date"),30),year,h.get("Result"),h.get("ECO"),None,len(ucis),
     _winner(h.get("Result")),_era(year),file,
     "https://www.pgnmentor.com/players/"+file+".zip",2,title,clean))
   con.execute("""UPDATE master_games SET featured=2,feature_reason=?
    WHERE id=?""",(title,identity))
   imported.append({"id":identity,"name":title,"white":h.get("White"),
                    "black":h.get("Black"),"event":h.get("Event"),"result":h.get("Result")})
  con.commit()
  return {"spotlights":imported,"unavailable":missing,
          "total":con.execute("SELECT count(*) FROM master_games").fetchone()[0]}
 finally:con.close()
def spotlights():
 con=db();ensure(con)
 try:
  rows=con.execute("""SELECT id,white,black,event,date,result,winner,eco,opening,
    plies,feature_reason FROM master_games WHERE featured=2
    ORDER BY year,id""").fetchall()
  return {"games":[dict(r) for r in rows],"note":
    "These are documented source games selected for historical teaching. Event and game score are original metadata; lesson names are editorial."}
 finally:con.close()

def import_championship_2013():
 """Add a verified decisive game from the actual 2013 World Championship event PGN."""
 from pathlib import Path
 path=RAW/"WorldChamp2013.pgn"
 if not path.is_file():return {"imported":False,"reason":"World Championship 2013 PGN missing"}
 con=db();ensure(con)
 try:
  with path.open("r",encoding="utf-8-sig",errors="replace") as f:
   candidates=[]
   while True:
    game=chess.pgn.read_game(f)
    if game is None:break
    h=game.headers
    if game.errors or h.get("Result")!="1-0":continue
    if "Carlsen" not in h.get("White","") or "Anand" not in h.get("Black",""):continue
    candidates.append(game)
  if not candidates:return {"imported":False,"reason":"No matching legal 2013 game"}
  g=candidates[0];board=g.board();moves=[]
  for m in g.mainline_moves():
   if m not in board.legal_moves:raise ValueError("Invalid championship score")
   moves.append(m.uci());board.push(m)
  h=g.headers;identity=_id(h,moves)
  pgn=g.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=False))
  con.execute("""INSERT OR IGNORE INTO master_games
  (id,white,black,event,site,date,year,result,eco,opening,plies,winner,era,
  source_player,source_url,featured,feature_reason,pgn)
  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
  (identity,_sanitize(h.get("White")),_sanitize(h.get("Black")),
   _sanitize(h.get("Event"),200),_sanitize(h.get("Site"),140),
   _sanitize(h.get("Date"),30),2013,"1-0",h.get("ECO"),None,len(moves),"White",
   _era(2013),"Carlsen","https://www.pgnmentor.com/events/WorldChamp2013.pgn",2,
   "Carlsen–Anand 2013 World Championship game",pgn))
  con.execute("""UPDATE master_games SET featured=2,feature_reason=?
   WHERE id=?""",("Carlsen–Anand 2013 World Championship game",identity))
  con.commit()
  return {"imported":True,"id":identity,"result":"1-0","event":h.get("Event"),"plies":len(moves)}
 finally:con.close()
