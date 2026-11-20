"""Local-first Chess Grind sparring games and honest post-game reviews.

Games are real python-chess positions. Only the local Stockfish executable
chooses opponent moves; there are no prerecorded/impossible replies. Game
history is persisted to SQLite, with no account, cloud or network dependency.
"""
from __future__ import annotations
import datetime as dt
import json
import re
import secrets
import threading
import chess
import chess.engine
from chess_grind import db
from game_analysis import find_engine
from lesson_explainer import move_reasons
from arena_personas import BOT_INDEX,coaches
from master_rivals import valid_master, source_move, STRENGTH as MASTER_STRENGTH, STYLES as MASTER_STYLES

USER = "player"
GAME_LOCK = threading.RLock()
LEVELS = {"beginner": 1, "casual": 4, "club": 9, "advanced": 15}
STYLES = {"balanced", "active", "solid"}
MAX_PLIES = 240

def ensure(con):
    con.executescript("""CREATE TABLE IF NOT EXISTS sparring_games (
      id TEXT PRIMARY KEY,
      username TEXT NOT NULL,
      user_color TEXT NOT NULL,
      difficulty TEXT NOT NULL,
      style TEXT NOT NULL,
      start_fen TEXT NOT NULL,
      uci_moves TEXT NOT NULL DEFAULT '[]',
      state TEXT NOT NULL DEFAULT 'active',
      outcome TEXT,
      review_json TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS sparring_games_user
      ON sparring_games(username,updated_at DESC);
    """)
    con.commit()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def _get(con,game_id):
    if not isinstance(game_id,str) or not re.fullmatch(r"[a-f0-9]{24}",game_id):
        raise ValueError("Invalid training game ID")
    row=con.execute("SELECT * FROM sparring_games WHERE id=? AND username=?",(game_id,USER)).fetchone()
    if row is None:raise ValueError("Training game not found")
    return dict(row)

def _board(row):
    board=chess.Board(row["start_fen"])
    moves=json.loads(row["uci_moves"])
    if not isinstance(moves,list) or len(moves)>MAX_PLIES:raise RuntimeError("Corrupted training game history")
    for uci in moves:
        move=chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise RuntimeError("Stored training game contains an illegal move")
        board.push(move)
    return board

def _game_state(board):
    if board.is_checkmate():
        return "White wins by checkmate" if board.turn==chess.BLACK else "Black wins by checkmate"
    if board.is_stalemate():return "Draw by stalemate"
    if board.is_insufficient_material():return "Draw by insufficient material"
    if board.is_fivefold_repetition():return "Draw by fivefold repetition"
    if board.is_seventyfive_moves():return "Draw by seventy-five move rule"
    if board.can_claim_threefold_repetition():return "Draw claim available (threefold repetition)"
    if board.can_claim_fifty_moves():return "Draw claim available (fifty-move rule)"
    return None

def _response(row, board, detail=None):
    user_white=row["user_color"]=="White"
    side_white=board.turn==chess.WHITE
    moves=[]
    for i,uci in enumerate(json.loads(row["uci_moves"])):
        pass
    replay=chess.Board(row["start_fen"])
    for uci in json.loads(row["uci_moves"]):
        move=chess.Move.from_uci(uci)
        san=replay.san(move)
        replay.push(move)
        moves.append({"san":san,"uci":uci,"fen":replay.fen(),
                      "by":"White" if not replay.turn else "Black"})
    from rival_dialogue import dialogue
    detail=detail or {}
    grade=(detail.get("coaching") or {}).get("category")
    mode="intro" if not moves or (len(moves)==1 and row["user_color"]=="Black") else "turn"
    speech=dialogue(row["difficulty"],mode,len(moves),grade,row["state"]=="finished",detail.get("yourMove"),detail.get("opponentMove"))
    return {"id":row["id"],"fen":board.fen(),"startFen":row["start_fen"],
        "color":row["user_color"],"difficulty":row["difficulty"],"style":row["style"],
        "rivalDialogue":speech,
       "bot":BOT_INDEX.get(row["difficulty"][4:]) if row["difficulty"].startswith("bot:") else None,
       "masterOpponent":_master_metadata(row["difficulty"][7:])
                      if row["difficulty"].startswith("master:") else None,
       "coachOpponent":next((c for c in coaches() if c["id"]==row["difficulty"][6:]),None)
                      if row["difficulty"].startswith("coach:") else None,
       "turn":"White" if side_white else "Black",
       "yourTurn":bool(user_white==side_white),
       "legalMoves":board.legal_moves.count(),"moves":moves,
       "state":row["state"],"outcome":row["outcome"],
       "inCheck":board.is_check(),"canClaimDraw":board.can_claim_draw(),
       "reviewAvailable":bool(row["review_json"]),
       "detail":detail,
       "note":"No engine hints are shown while playing. Post-game analysis is separate."}

def _master_metadata(key):
    if not valid_master(key):return None
    from masters_library import PLAYERS
    return {"id":key,"name":PLAYERS[key][0],"era":PLAYERS[key][1],
            "avatar":"/icons/masters/"+key+".svg",
            "skill":MASTER_STRENGTH.get(key,18),
            "style":MASTER_STYLES.get(key,"balanced"),
            "sourceNote":"Moves follow the archived master only when a matching historical position is found. Otherwise Stockfish plays approximately."}

def _engine():
    path=find_engine()
    if not path:raise RuntimeError("Install Stockfish locally before starting a training game")
    return path

def _bot_move(board,difficulty,style):
    persona=BOT_INDEX.get(difficulty[4:]) if difficulty.startswith("bot:") else None
    coach=next((c for c in coaches() if c["id"]==difficulty[6:]),None) if difficulty.startswith("coach:") else None
    master_id=difficulty[7:] if difficulty.startswith("master:") else None
    maximum=bool(persona and persona["maxStrength"])
    skill=MASTER_STRENGTH.get(master_id,18) if master_id else (
        persona["skill"] if persona else (coach["skill"] if coach else LEVELS.get(difficulty,8)))
    budget=(1.8 if maximum else .15+skill*.027) if (persona or coach or master_id) else (
        .11 if difficulty in ("beginner","casual") else .22)
    with chess.engine.SimpleEngine.popen_uci(_engine(),timeout=35) as eng:
        eng.configure({"Threads":2 if maximum else 1,"Hash":96 if maximum else 32,
                       "Skill Level":20 if maximum else skill,"UCI_LimitStrength":False})
        limit=chess.engine.Limit(time=budget)
        historical=source_move(board,master_id) if master_id else None
        if historical:
            # A historical recorded choice is informative, but do not force
            # a gross tactical blunder just to imitate the source.
            try:
                info=eng.analyse(board,chess.engine.Limit(depth=8))
                top=info["score"].pov(board.turn).score(mate_score=20000)
                rated=eng.analyse(board,chess.engine.Limit(depth=8),root_moves=[historical])
                actual=rated["score"].pov(board.turn).score(mate_score=20000)
                if top is not None and actual is not None and top-actual<=180:
                    return historical
            except (chess.engine.EngineError,KeyError,ValueError):
                pass
        result=eng.play(board,limit)
        move=result.move
        if not move or move not in board.legal_moves:
            raise RuntimeError("Stockfish could not choose a legal move")
        # "Active" and "solid" are modest move-selection preferences, NOT
        # guaranteed human-like personalities. Never sacrifice >0.8 pawn
        # according to a shallow comparison just to fulfill a style label.
        if not maximum and style!="balanced" and board.legal_moves.count()>1:
            info=eng.analyse(board,chess.engine.Limit(depth=7),
                             multipv=min(4,board.legal_moves.count()))
            if isinstance(info,dict):info=[info]
            root=board.turn
            valid=[r for r in info if r.get("pv")]
            if valid:
                best=valid[0]["score"].pov(root).score(mate_score=20000)
                options=[]
                for r in valid:
                    m=r["pv"][0];cp=r["score"].pov(root).score(mate_score=20000)
                    if best is None or cp is None or best-cp>80:continue
                    b=board.copy();is_capture=b.is_capture(m);is_check=b.gives_check(m)
                    b.push(m)
                    if style=="active":
                        metric=3*is_check+2*is_capture+len(b.attackers(not b.turn,m.to_square))*.1
                    else:
                        metric=2*(not is_check and not is_capture)
                    options.append((metric,cp,m))
                if options:
                    move=max(options,key=lambda x:(x[0],x[1]))[2]
        return move

def _update_state(row,board):
    result=_game_state(board)
    if result and not result.startswith("Draw claim"):
        row["state"]="finished"
        row["outcome"]=result
    elif len(json.loads(row["uci_moves"]))>=MAX_PLIES:
        row["state"]="finished"
        row["outcome"]="Training move limit reached; game ended without a result"
    return row

def _persist(con,row):
    row["updated_at"]=now()
    con.execute("""UPDATE sparring_games SET uci_moves=?,state=?,outcome=?,
          review_json=?,updated_at=? WHERE id=? AND username=?""",
       (row["uci_moves"],row["state"],row["outcome"],row["review_json"],
        row["updated_at"],row["id"],USER))
    con.commit()

def start(color="White",difficulty="casual",style="balanced",bot_id=None,coach_opponent_id=None,master_id=None):
    if color not in ("White","Black"):raise ValueError("Choose White or Black")
    if master_id is not None:
        if not valid_master(master_id):raise ValueError("Choose an available historic master")
        if bot_id is not None or coach_opponent_id is not None:
            raise ValueError("Choose one opponent")
        difficulty="master:"+master_id
        style=MASTER_STYLES.get(master_id,"balanced")
    if coach_opponent_id is not None:
        if not isinstance(coach_opponent_id,str):
            raise ValueError("Select a saved chess coach")
        selected=next((c for c in coaches() if c["id"]==coach_opponent_id),None)
        if selected is None:raise ValueError("Coach not found; choose a saved coach")
        difficulty="coach:"+coach_opponent_id
        style=selected["style"]
    if bot_id is not None and coach_opponent_id is not None:
        raise ValueError("Choose either a coach or a rival")
    if bot_id is not None:
        if not isinstance(bot_id,str) or bot_id not in BOT_INDEX:
            raise ValueError("Unknown chess opponent")
        difficulty="bot:"+bot_id
        style=BOT_INDEX[bot_id]["style"]
    if difficulty not in LEVELS and not (
        difficulty.startswith("bot:") and difficulty[4:] in BOT_INDEX
    ) and not (difficulty.startswith("coach:") and difficulty[6:] in {x["id"] for x in coaches()}) and not (
        difficulty.startswith("master:") and valid_master(difficulty[7:])):
        raise ValueError("Unknown opponent difficulty")
    if style not in STYLES:raise ValueError("Unknown sparring style")
    with GAME_LOCK:
        con=db()
        try:
            ensure(con)
            identifier=secrets.token_hex(12)
            row={"id":identifier,"username":USER,"user_color":color,"difficulty":difficulty,
                 "style":style,"start_fen":chess.STARTING_FEN,"uci_moves":"[]",
                 "state":"active","outcome":None,"review_json":None,
                 "created_at":now(),"updated_at":now()}
            board=chess.Board()
            if color=="Black":
                bot=_bot_move(board,difficulty,style)
                board.push(bot)
                row["uci_moves"]=json.dumps([bot.uci()])
            con.execute("""INSERT INTO sparring_games
                (id,username,user_color,difficulty,style,start_fen,uci_moves,
                 state,outcome,review_json,created_at,updated_at)
                VALUES(:id,:username,:user_color,:difficulty,:style,:start_fen,
                 :uci_moves,:state,:outcome,:review_json,:created_at,:updated_at)""",row)
            con.commit()
            return _response(row,board)
        finally:con.close()

def status(game_id):
    con=db()
    try:
        ensure(con);row=_get(con,game_id)
        return _response(row,_board(row))
    finally:con.close()

def recent(offset=0,limit=20,state="all",color="all"):
    """Paginated, searchable saved games. No history is evicted by this view."""
    if type(offset) is not int or offset<0 or offset>1000000:raise ValueError("Invalid archive offset")
    if type(limit) is not int or not 1<=limit<=100:raise ValueError("Invalid archive page size")
    if state not in ("all","active","finished"):raise ValueError("Invalid game status filter")
    if color not in ("all","White","Black"):raise ValueError("Invalid player color filter")
    clauses=["username=?"];args=[USER]
    if state!="all":
        clauses.append("state=?");args.append(state)
    if color!="all":
        clauses.append("user_color=?");args.append(color)
    where=" AND ".join(clauses)
    con=db()
    try:
        ensure(con)
        total=con.execute("SELECT COUNT(*) FROM sparring_games WHERE "+where,args).fetchone()[0]
        rows=con.execute("""SELECT id,user_color,difficulty,style,state,outcome,created_at,
                   updated_at,uci_moves,review_json FROM sparring_games
                   WHERE """+where+" ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?",
                   args+[limit,offset]).fetchall()
        return {"games":[{"id":r["id"],"color":r["user_color"],"difficulty":r["difficulty"],
                 "style":r["style"],"state":r["state"],"outcome":r["outcome"],
                 "moves":len(json.loads(r["uci_moves"])),"createdAt":r["created_at"],
                 "updatedAt":r["updated_at"],"reviewAvailable":bool(r["review_json"])}
                for r in rows],
                "total":total,"offset":offset,"limit":limit,"hasMore":offset+len(rows)<total}
    finally:con.close()


def pgn(game_id):
    """Export an accurate copy of the locally saved game score."""
    import chess.pgn
    con=db()
    try:
        ensure(con);row=_get(con,game_id)
        game=chess.pgn.Game()
        game.headers["Event"]="Chess Grind local training game"
        game.headers["Site"]="Chess Grind (local)"
        game.headers["Date"]=row["created_at"][:10].replace("-",".")
        game.headers["White"]=USER if row["user_color"]=="White" else "Chess Grind Stockfish"
        game.headers["Black"]=USER if row["user_color"]=="Black" else "Chess Grind Stockfish"
        board=chess.Board(row["start_fen"])
        if row["start_fen"]!=chess.STARTING_FEN:game.setup(board)
        node=game
        for uci in json.loads(row["uci_moves"]):
            move=chess.Move.from_uci(uci)
            if move not in board.legal_moves:raise RuntimeError("Saved score contains an illegal move")
            node=node.add_variation(move)
            board.push(move)
        outcome=row["outcome"] or ""
        if "White wins" in outcome:game.headers["Result"]="1-0"
        elif "Black wins" in outcome:game.headers["Result"]="0-1"
        elif "Draw " in outcome or outcome.startswith("Draw"):game.headers["Result"]="1/2-1/2"
        else:game.headers["Result"]="*"
        game.headers["Termination"]=outcome or "Unfinished"
        game.headers["Annotator"]="Chess Grind — saved local game score"
        return str(game)
    finally:con.close()

def move(game_id,uci):
    with GAME_LOCK:
        con=db()
        try:
            ensure(con);row=_get(con,game_id);board=_board(row)
            if row["state"]!="active":raise ValueError("This training game has already ended")
            turn="White" if board.turn else "Black"
            if turn!=row["user_color"]:raise ValueError("It's the opponent's turn")
            if not isinstance(uci,str) or not re.fullmatch("[a-h][1-8][a-h][1-8][qrbn]?",uci):
                raise ValueError("Choose a legal piece and destination")
            chosen=chess.Move.from_uci(uci)
            if chosen not in board.legal_moves:raise ValueError("That move is not legal")
            san=board.san(chosen)
            from live_coach import grade
            coaching=grade(board,chosen,game_id,len(json.loads(row["uci_moves"]))+1)
            before_fen=board.fen()
            history=json.loads(row["uci_moves"]);history.append(chosen.uci())
            board.push(chosen)
            row["uci_moves"]=json.dumps(history)
            _update_state(row,board)
            reply=None
            if row["state"]=="active":
                try:
                    response=_bot_move(board,row["difficulty"],row["style"])
                except Exception:
                    # Preserve the user's legal move even if the engine fails.
                    _persist(con,row)
                    raise
                reply=board.san(response)
                history.append(response.uci())
                board.push(response)
                row["uci_moves"]=json.dumps(history)
                _update_state(row,board)
            _persist(con,row)
            from conversational_chess import store_grade
            store_grade(game_id,len(history),coaching)
            if coaching:
                try:
                    from chess_knowledge import record_player_move
                    record_player_move(game_id,len(history)-int(bool(reply)),before_fen,
                                       chosen.uci(),coaching)
                except (OSError,ValueError,RuntimeError):
                    # Knowledge collection cannot invalidate a legal played move.
                    pass
            return _response(row,board,{"yourMove":san,"opponentMove":reply,"coaching":coaching})
        finally:con.close()

def continue_opponent(game_id):
    """Recover a saved game if the engine failed after a legal player move."""
    with GAME_LOCK:
        con=db()
        try:
            ensure(con);row=_get(con,game_id);board=_board(row)
            if row["state"]!="active":raise ValueError("Game has already finished")
            turn="White" if board.turn else "Black"
            if turn==row["user_color"]:raise ValueError("It is your turn; choose your own move")
            bot=_bot_move(board,row["difficulty"],row["style"])
            reply=board.san(bot)
            moves=json.loads(row["uci_moves"]);moves.append(bot.uci())
            board.push(bot);row["uci_moves"]=json.dumps(moves)
            _update_state(row,board);_persist(con,row)
            return _response(row,board,{"opponentMove":reply})
        finally:con.close()

def resign(game_id):
    with GAME_LOCK:
        con=db()
        try:
            ensure(con);row=_get(con,game_id);board=_board(row)
            if row["state"]!="active":raise ValueError("Game has already ended")
            row["state"]="finished"
            row["outcome"]=("White" if row["user_color"]=="Black" else "Black")+" wins by resignation"
            _persist(con,row)
            return _response(row,board)
        finally:con.close()

def claim_draw(game_id):
    """A player can claim a valid threefold or fifty-move draw on their turn."""
    with GAME_LOCK:
        con=db()
        try:
            ensure(con);row=_get(con,game_id);board=_board(row)
            if row["state"]!="active":raise ValueError("Game has already finished")
            if ("White" if board.turn else "Black")!=row["user_color"]:
                raise ValueError("You can only claim a draw on your turn")
            if not board.can_claim_draw():
                raise ValueError("There is no valid draw claim in this position")
            row["state"]="finished"
            row["outcome"]="Draw claimed by player (threefold repetition or fifty-move rule)"
            _persist(con,row)
            return _response(row,board)
        finally:con.close()

def review(game_id):
    """One local depth-limited assessment per saved human decision, cached by game."""
    with GAME_LOCK:
        con=db()
        try:
            ensure(con);row=_get(con,game_id)
            if row["state"]!="finished":raise ValueError("Finish or resign before requesting review")
            if row["review_json"]:return json.loads(row["review_json"])
            board=chess.Board(row["start_fen"])
            points=[];moves=json.loads(row["uci_moves"])
            human_white=row["user_color"]=="White"
            path=_engine()
            with chess.engine.SimpleEngine.popen_uci(path,timeout=60) as eng:
                eng.configure({"Threads":1,"Hash":64})
                budget=chess.engine.Limit(depth=9)
                for i,uci in enumerate(moves):
                    action=chess.Move.from_uci(uci)
                    own=(board.turn==chess.WHITE)==human_white
                    if own:
                        original=board.fen()
                        played_san=board.san(action)
                        best=eng.analyse(board,budget)
                        best_move=best["pv"][0] if best.get("pv") else action
                        best_san=board.san(best_move)
                        if best_move==action:
                            chosen_eval=best
                        else:
                            chosen_eval=eng.analyse(board,budget,root_moves=[action])
                        best_cp=best["score"].pov(board.turn).score(mate_score=20000)
                        chosen_cp=chosen_eval["score"].pov(board.turn).score(mate_score=20000)
                        gap=max(0,(best_cp or 0)-(chosen_cp or 0))
                        phase="Opening" if board.fullmove_number<=10 else (
                          "Endgame" if sum(p.piece_type not in (chess.PAWN,chess.KING) for p in board.piece_map().values())<=3 else "Middlegame")
                        label="Strong" if gap<=65 else ("Inaccuracy" if gap<120 else "Mistake" if gap<250 else "Blunder")
                        points.append({"ply":i+1,"fen":original,"playedUci":uci,
                           "playedSan":played_san,"bestUci":best_move.uci(),
                           "bestSan":best_san,"gapCp":gap,"phase":phase,
                           "label":label,"reasons":move_reasons(board,best_move)[:2]})
                    board.push(action)
            flagged=[p for p in points if p["gapCp"]>65]
            by_phase={name:{"attempts":sum(p["phase"]==name for p in points),
                              "flagged":sum(p["phase"]==name for p in flagged)}
                     for name in ("Opening","Middlegame","Endgame")}
            result={"gameId":game_id,"outcome":row["outcome"],"color":row["user_color"],
              "decisions":len(points),"strong":sum(p["gapCp"]<=65 for p in points),
              "flagged":len(flagged),"byPhase":by_phase,
              "moments":sorted(flagged,key=lambda p:-p["gapCp"])[:8],
              "allDecisions":points,
              "coachSummary":("Your most costly decisions occurred in "+
                max(by_phase,key=lambda key:by_phase[key]["flagged"])+
                ". Review the concrete alternatives below before your next game."
                if flagged else
                "No errors above the configured threshold were detected at this search depth. This does not prove perfect play."),
              "note":"Each human move was compared with local Stockfish at depth 9. Ratings and exact long-term improvement cannot be inferred from one practice game."}
            row["review_json"]=json.dumps(result)
            _persist(con,row)
            return result
        finally:con.close()
