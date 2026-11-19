"""Read-only analyzed-game visual coaching endpoint."""
import json
from chess_grind import db
from move_grading import grade
import chess

def review(payload,username="player"):
    try:
        game_id=str(payload["gameId"])
        ply=int(payload["ply"])
    except (KeyError,TypeError,ValueError):
        return 400,{"error":"Supply a game ID and move number."}
    if ply<0:return 400,{"error":"Invalid move number."}
    con=db()
    row=con.execute("SELECT data FROM game_analysis WHERE username=? AND game_id=?",
       (username.lower(),game_id)).fetchone()
    con.close()
    if not row:return 404,{"error":"Game not found."}
    data=json.loads(row["data"])
    chosen=next((m for m in data["mistakes"] if m["ply"]==ply),None)
    if chosen is None:
        return 404,{"error":"Only engine-flagged moves currently have comparative visual analysis."}
    try:
        board=chess.Board(chosen["fen"])
        played=board.parse_san(chosen["move"])
        analysis=grade(chosen["fen"],played,chosen["best"],depth=11)
    except (ValueError,RuntimeError,chess.engine.EngineError,TimeoutError) as error:
        return 503,{"error":"Engine visual review unavailable: "+str(error)[:200]}
    return 200,{"visual":analysis["visual"],"lesson":analysis["lesson"],
                "played":analysis["played_san"],"best":analysis["best_san"],
                "accepted":analysis["accepted"]}
