"""Analyze imported Chess.com rapid games using a local Stockfish executable."""
import argparse
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time

import chess
import chess.engine
import chess.pgn

from chess_grind import db
from chesscom_api import ensure_schema

ROOT = Path(__file__).resolve().parent

def find_engine():
    override = os.getenv("STOCKFISH_PATH")
    if override and Path(override).is_file():
        return str(Path(override))
    candidates = sorted(ROOT.glob("engine/**/*stockfish*.exe")) + sorted(ROOT.glob("**/stockfish.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("stockfish")

def ensure_analysis(con):
    con.execute("""CREATE TABLE IF NOT EXISTS game_analysis (
      game_id TEXT PRIMARY KEY, username TEXT NOT NULL, analyzed_at TEXT NOT NULL,
      engine TEXT NOT NULL, depth INTEGER NOT NULL, data TEXT NOT NULL
    )""")
    con.commit()

def score_cp(info, pov):
    score = info["score"].pov(pov)
    return max(-1200, min(1200, score.score(mate_score=1200)))

def analyze_game(engine, raw, depth=10, max_plies=160):
    game = chess.pgn.read_game(io.StringIO(raw["pgn"]))
    if game is None:
        raise ValueError("Empty PGN")
    board = game.board()
    name = raw["username"].lower()
    player = chess.WHITE if str(raw["white_username"]).lower() == name else chess.BLACK
    info = {"id": raw["game_id"], "url": raw["url"], "date": raw["end_time"],
            "timeClass":raw["time_class"],
            "opponent": raw["black_username"] if player == chess.WHITE else raw["white_username"],
            "color": "White" if player else "Black", "result": raw["result"],
            "opening": game.headers.get("ECOUrl", game.headers.get("Opening", "Unclassified")),
            "plies": [], "mistakes": [], "counts": {"blunder":0,"mistake":0,"inaccuracy":0},
            "player_moves":0}
    before = None
    for n, move in enumerate(game.mainline_moves()):
        if n >= max_plies:
            break
        fen = board.fen()
        if not board.is_legal(move):
            break
        side = board.turn
        san = board.san(move)
        # Analyze only the player's moves; this halves compute cost.
        if side == player:
            optimal = engine.analyse(board, chess.engine.Limit(depth=depth))
            best_move = optimal.get("pv", [None])[0]
            best_san = board.san(best_move) if best_move else None
            best_cp = score_cp(optimal, side)
            info["player_moves"] += 1
        else:
            best_move, best_san, best_cp = None, None, None
        board.push(move)
        rating = None
        lost = 0
        if side == player:
            after = engine.analyse(board, chess.engine.Limit(depth=depth))
            actual_cp = score_cp(after, side)
            lost = max(0, best_cp - actual_cp)
            if lost >= 250: rating = "blunder"
            elif lost >= 120: rating = "mistake"
            elif lost >= 60: rating = "inaccuracy"
            if rating:
                info["counts"][rating] += 1
                info["mistakes"].append({"ply":n, "move":san, "fen":fen,
                  "best":best_san, "loss":lost, "kind":rating,
                  "explanation":explain(board, san, best_san, lost, rating)})
        info["plies"].append({"san":san, "fenBefore":fen, "fenAfter":board.fen(),
          "playerMove":side == player, "kind":rating, "loss":lost,
          "best":best_san, "number":n//2+1, "side":"white" if side else "black"})
    return info

def explain(board, played, best, loss, kind):
    return (f"You played {played}, but Stockfish preferred {best}. "
            f"That decision cost approximately {loss / 100:.1f} pawns in engine evaluation "
            f"({kind}). Revisit this position and calculate checks, captures, and threats before moving.")

def analyze(username="player", depth=10, max_games=30, seconds=None):
    con=db()
    ensure_schema(con)
    ensure_analysis(con)
    path=find_engine()
    if not path:
        raise RuntimeError("Stockfish is missing. Place the official Windows Stockfish executable in the engine folder, or set STOCKFISH_PATH.")
    games = con.execute("""SELECT * FROM chesscom_games WHERE username=?
      AND game_id NOT IN (SELECT game_id FROM game_analysis WHERE username=? AND depth>=?)
      ORDER BY CASE WHEN time_class='rapid' THEN 0 WHEN time_class='blitz' THEN 1
                    WHEN time_class='daily' THEN 2 ELSE 3 END,
               end_time DESC LIMIT ?""", (username.lower(),username.lower(),depth,max_games)).fetchall()
    if not games:
        return {"analyzed":0,"message":"All available games have already been analyzed at this depth."}
    count=0
    errors=[]
    with chess.engine.SimpleEngine.popen_uci(path, timeout=30) as engine:
        engine.configure({"Threads": 2, "Hash": 64})
        for raw in games:
            try:
                info=analyze_game(engine,raw,depth=depth)
                con.execute("""INSERT OR REPLACE INTO game_analysis
                 (game_id,username,analyzed_at,engine,depth,data)
                 VALUES(?,?,datetime('now'),?,?,?)""",
                 (raw["game_id"],username.lower(),Path(path).name,depth,json.dumps(info)))
                con.commit()
                count += 1
                print(f"Analyzed {count}/{len(games)}: {info['opponent']} - {len(info['mistakes'])} flagged moves",flush=True)
            except Exception as e:
                errors.append(f"{raw['game_id']}: {e}")
                print(f"Skipped game: {e}",flush=True)
    return {"analyzed":count,"errors":errors,"engine":path,"depth":depth}

def dashboard_data(username=None):
    from chesscom_api import status
    if not username:
        from account_settings import username as configured_username
        username=configured_username() or "player"
    con=db();ensure_analysis(con)
    player=status(con,username)
    rows=con.execute("""SELECT data FROM game_analysis WHERE username=?
      ORDER BY analyzed_at DESC""",(username.lower(),)).fetchall()
    games=[json.loads(r[0]) for r in rows]
    mistakes=sorted([dict(m,gameId=g["id"],opponent=g["opponent"],date=g["date"],color=g["color"],timeClass=g.get("timeClass","rapid"))
      for g in games for m in g["mistakes"]],key=lambda m:(-m["loss"],-m["date"]))
    by_type={kind:sum(g.get("timeClass","rapid")==kind for g in games)
             for kind in ("rapid","blitz","bullet","daily")}
    counts={k:sum(g["counts"][k] for g in games) for k in ("blunder","mistake","inaccuracy")}
    library=con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    return {"player":player,"games":games,"mistakes":mistakes,"counts":counts,
      "passages":library,"analyzed":len(games),"byType":by_type,
      "playerMoves":sum(g["player_moves"] for g in games)}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--username",default="player")
    p.add_argument("--depth",type=int,default=10)
    p.add_argument("--max-games",type=int,default=30)
    a=p.parse_args()
    print(json.dumps(analyze(a.username,max(6,min(18,a.depth)),a.max_games),indent=2))
