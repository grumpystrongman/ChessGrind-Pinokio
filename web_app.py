"""Local-only Chess Grind coaching dashboard and API."""
import datetime as dt
import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from game_analysis import dashboard_data
from coaching import training,submit_answer
from daily_coach import today,complete
from mobile_security import authorize, check_origin

ROOT=Path(__file__).resolve().parent
lock=threading.Lock()
job={"running":False,"stage":"idle","message":"Ready"}

def refresh_job():
    try:
        from daily_agent import run
        with lock:job.update(stage="sync",message="Synchronizing Rapid games, analyzing, and indexing library")
        result=run()
        with lock:
            if result.get("skipped"):
                job.update(stage="blocked",message="Another daily analysis is already running.")
            else:
                a=result.get('analysis',{});s=result.get('sync',{});v=result.get('vectors',{})
                warning=result.get('warnings',[])
                message=(f"Imported {s.get('new_games','?')} new games. "
                         f"Analyzed {a.get('analyzed','?')}. "
                         f"Embedded {v.get('stored','?')} passages.")
                if warning: message+=' Partial errors: '+str(warning[:2])
                job.update(stage='done' if not warning else 'warning',message=message)
    except Exception as exc:
        with lock:job.update(stage="error",message=str(exc)[:250])
    finally:
        with lock:job["running"]=False

def launch_refresh():
    with lock:
        if job["running"]:return False
        job.update(running=True,stage="starting",message="Starting chess coaching refresh")
    threading.Thread(target=refresh_job,daemon=True).start()
    return True

def stale():
    try:
        from chesscom_api import status
        from chess_grind import db
        from account_settings import username
        selected=username()
        if not selected:return False
        snapshot=status(db(),selected)
        if not snapshot.get("synced"):return True
        last=dt.datetime.fromisoformat(snapshot["synced_at"])
        return dt.datetime.now(dt.timezone.utc)-last>dt.timedelta(hours=24)
    except Exception:return True

class Handler(BaseHTTPRequestHandler):
    def require_auth(self):
        allowed,remote=authorize(self.headers.get('Host',''),self.headers)
        self._remote=remote
        if not allowed:
            self.send_bytes(b'{"error":"Access denied: a valid Cloudflare Access session is required."}',403)
            return False
        return True

    def send_bytes(self,data,status=200,mime="application/json; charset=utf-8"):
        compressed=(len(data)>1024 and 'gzip' in self.headers.get('Accept-Encoding','').lower()
                    and not mime.startswith('image/'))
        if compressed:
            data=gzip.compress(data,compresslevel=5)
        self.send_response(status)
        self.send_header('Vary','Accept-Encoding')
        if compressed:self.send_header('Content-Encoding','gzip')
        self.send_header("Content-Type",mime)
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy",
          "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def respond(self,obj,status=200):
        self.send_bytes(json.dumps(obj,ensure_ascii=False).encode("utf-8"),status)
    def do_GET(self):
        if not self.require_auth():return
        path=urlparse(self.path).path
        try:
            if path=='/favicon.ico':
                self.send_bytes((ROOT/'icons'/'icon-192.png').read_bytes(),mime='image/png')
                return
            if path=='/phone.css':
                self.send_bytes((ROOT/'phone.css').read_bytes(),mime='text/css; charset=utf-8')
                return
            if path=='/manifest.webmanifest':
                self.send_bytes((ROOT/'manifest.webmanifest').read_bytes(),mime='application/manifest+json')
                return
            if path=='/sw.js':
                self.send_bytes((ROOT/'sw.js').read_bytes(),mime='application/javascript; charset=utf-8')
                return
            if path in ('/icons/icon-192.png','/icons/icon-512.png'):
                self.send_bytes((ROOT/path.lstrip('/')).read_bytes(),mime='image/png')
                return
            if path=="/":
                self.send_bytes((ROOT/"dashboard.html").read_bytes(),mime="text/html; charset=utf-8")
            elif path=="/learn":
                self.send_bytes((ROOT/"learning_lab.html").read_bytes(),mime="text/html; charset=utf-8")
            elif path=="/academy":
                self.send_bytes((ROOT/"academy.html").read_bytes(),mime="text/html; charset=utf-8")
            elif path=="/workshop":
                self.send_bytes((ROOT/"workshop.html").read_bytes(),mime="text/html; charset=utf-8")
            elif path=="/strategy":
                self.send_bytes((ROOT/"strategy.html").read_bytes(),mime="text/html; charset=utf-8")
            elif path=="/opening-course":
                self.send_bytes((ROOT/"opening_course.html").read_bytes(),mime="text/html; charset=utf-8")
            elif path=="/arena":
                self.send_bytes((ROOT/"arena.html").read_bytes(),mime="text/html; charset=utf-8")
            elif path=="/masters":
                self.send_bytes((ROOT/"masters.html").read_bytes(),mime="text/html; charset=utf-8")
            elif path=="/api/dashboard":
                from account_settings import username
                self.respond(dashboard_data(username() or "player"))
            elif path=="/api/lab/chat/status":
                from board_chat import status
                self.respond(status())
            elif path=="/api/lab/chat/history":
                from board_chat import history
                from urllib.parse import parse_qs
                fen=parse_qs(urlparse(self.path).query).get("fen",[None])[0]
                thread_id=parse_qs(urlparse(self.path).query).get("threadId",[None])[0]
                self.respond(history(fen,thread_id=thread_id))
            elif path=="/api/masters":
                from masters_library import overview
                self.respond(overview())
            elif path=="/api/masters/spotlights":
                from masters_spotlights import spotlights
                self.respond(spotlights())
            elif path=="/api/masters/games":
                from masters_library import search
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(search(q.get("q",[""])[0],q.get("player",[""])[0],
                    q.get("era",[""])[0],q.get("winner",[""])[0],
                    int(q.get("limit",["28"])[0]),int(q.get("offset",["0"])[0])))
            elif path=="/api/masters/move-insight":
                from masters_move_coach import teach
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(teach(q.get("id",[""])[0],int(q.get("ply",["0"])[0])))
            elif path=="/api/masters/game":
                from masters_library import detail
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(detail(q.get("id",[""])[0]))
            elif path=="/api/masters/chat/history":
                from masters_tutor import history
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(history(q.get("id",[""])[0],q.get("thread",[""])[0]))
            elif path=="/api/skill-plan":
                from skill_plan import plan
                from urllib.parse import parse_qs
                minutes=parse_qs(urlparse(self.path).query).get("minutes",["20"])[0]
                self.respond(plan(minutes))
            elif path=="/api/sparring/recent":
                from sparring import recent
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(recent(offset=int(q.get("offset",["0"])[0]),
                    limit=int(q.get("limit",["20"])[0]),
                    state=q.get("state",["all"])[0],
                    color=q.get("color",["all"])[0]))
            elif path=="/api/sparring/pgn":
                from sparring import pgn
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                game_id=q.get("id",[""])[0]
                result=pgn(game_id)
                self.send_bytes(result.encode("utf-8"),mime="application/x-chess-pgn; charset=utf-8")
            elif path=="/api/sparring/game":
                from sparring import status
                from urllib.parse import parse_qs
                game_id=parse_qs(urlparse(self.path).query).get("id",[""])[0]
                self.respond(status(game_id))
            elif path=="/settings":
                self.send_bytes((ROOT/"account_settings.html").read_bytes(),mime="text/html; charset=utf-8")
            elif path=="/api/settings/chesscom":
                from account_settings import current
                self.respond(current())
            elif path=="/api/eco":
                import opening_mastery as m
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(m.catalog(q.get("color",["White"])[0],q.get("q",[""])[0],
                                       int(q.get("limit",["40"])[0])))
            elif path=="/api/eco/identify":
                import eco_catalog as e
                from urllib.parse import parse_qs
                fen=parse_qs(urlparse(self.path).query).get("fen",[None])[0]
                self.respond({"opening":e.classify(fen)})
            elif path=="/api/opening-course/my-openings":
                from opening_mastery import personal_openings
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(personal_openings(q.get("color",["White"])[0]))
            elif path=="/api/opening-course/dashboard":
                from opening_mastery import dashboard
                self.respond(dashboard())
            elif path=="/api/opening-course/lesson":
                from opening_mastery import lesson
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(lesson(int(q.get("id",["-1"])[0]),q.get("color",["White"])[0]))
            elif path=="/api/opening-course/concept":
                from opening_mastery import concept_question
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(concept_question(int(q.get("id",["-1"])[0]),q.get("color",["White"])[0]))
            elif path=="/api/opening-course/recall":
                from opening_mastery import review_question
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(review_question(int(q.get("id",["-1"])[0]),q.get("color",["White"])[0]))
            elif path=="/api/opening-course/transfer":
                from opening_mastery import transfer_question
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(transfer_question(int(q.get("id",["-1"])[0]),q.get("color",["White"])[0]))
            elif path=="/api/endgame/deep":
                from endgame_theory import teach
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(teach(q.get("id",[""])[0]))
            elif path=="/api/repertoire":
                from opening_repertoire import overview
                self.respond(overview())
            elif path=="/api/repertoire/lines":
                from opening_repertoire import lines
                from urllib.parse import parse_qs
                args=parse_qs(urlparse(self.path).query)
                self.respond(lines(args.get("color",["White"])[0]))
            elif path=="/api/repertoire/position":
                from opening_repertoire import position
                from urllib.parse import parse_qs
                args=parse_qs(urlparse(self.path).query)
                self.respond(position(args.get("fen",[""])[0]))
            elif path=="/api/repertoire/lesson":
                from opening_coach import lesson
                from urllib.parse import parse_qs
                q=parse_qs(urlparse(self.path).query)
                self.respond(lesson(q.get("fen",[""])[0],q.get("uci",[None])[0]))
            elif path=="/api/repertoire/review":
                from opening_repertoire import review
                self.respond(review())
            elif path=="/api/endgame":
                from endgame_lab import overview
                self.respond(overview())
            elif path=="/api/endgame/lesson":
                from endgame_lab import lesson
                from urllib.parse import parse_qs
                args=parse_qs(urlparse(self.path).query)
                self.respond(lesson(args.get("id",[""])[0]))
            elif path=="/api/workshop/profile":
                from calculation_workshop import profile
                self.respond(profile())
            elif path=="/api/workshop/positions":
                from calculation_workshop import positions
                from urllib.parse import parse_qs
                args=parse_qs(urlparse(self.path).query)
                self.respond(positions(args.get("topic",[None])[0],args.get("phase",[None])[0],
                                       int(args.get("limit",["14"])[0])))
            elif path=="/api/academy":
                from academy_curriculum import overview
                self.respond(overview())
            elif path=="/api/academy/lesson":
                from academy_curriculum import lesson
                from urllib.parse import parse_qs
                lesson_id=parse_qs(urlparse(self.path).query).get("id",[""])[0]
                self.respond(lesson(lesson_id))
            elif path=="/api/academy/challenge":
                from academy_curriculum import challenge
                from urllib.parse import parse_qs
                args=parse_qs(urlparse(self.path).query)
                self.respond(challenge(args.get("id",[""])[0],int(args.get("number",["0"])[0]),
                                       args.get("challengeId",[None])[0]))
            elif path=="/api/lab/profile":
                from learning_lab import skills
                self.respond(skills())
            elif path=="/api/lab/campaigns":
                from learning_lab import campaigns
                self.respond({"campaigns":campaigns()})
            elif path=="/api/lab/session":
                from urllib.parse import parse_qs
                from learning_lab import exercise
                sid=parse_qs(urlparse(self.path).query).get("id",[""])[0]
                self.respond(exercise(sid))
            elif path=="/api/coaching":
                self.respond(training())
            elif path=="/api/daily":
                self.respond(today())
            elif path=="/api/chat/history":
                from tutor import history
                self.respond({"items":history()})
            elif path=="/api/library":
                from chess_grind import db
                from library_pipeline import ensure
                con=db();ensure(con)
                rows=con.execute("""SELECT b.title,b.author,b.url,b.rights,b.status,b.format,b.year,b.source,
                     COALESCE(p.pdf_count,0) AS pdf_count,p.pdf_url,
                     a.decision AS rights_decision
                     FROM books b LEFT JOIN (
                       SELECT book_id,COUNT(*) AS pdf_count,MIN(url) AS pdf_url
                       FROM book_files WHERE format='pdf' GROUP BY book_id
                     ) p ON p.book_id=b.id
                     LEFT JOIN library_audit a ON a.book_id=b.id
                     ORDER BY CASE WHEN b.status='indexed' THEN 0 ELSE 1 END,b.title
                     LIMIT 10000""").fetchall()
                from book_quality import consolidate_catalog
                all_editions=[dict(r) for r in rows]
                books=consolidate_catalog(all_editions)
                self.respond({'books':books,'count':len(books),'editionCount':len(all_editions),
                              'pdfRecords':sum(b["pdf_count"]>0 for b in books),
                              'indexed':sum(b["status"]=="indexed" for b in books)})
            elif path=="/api/job":
                with lock:self.respond(dict(job))
            elif path=="/health":
                self.respond({"status":"ok"})
            else:self.send_error(404)
        except Exception as exc:self.respond({"error":str(exc)[:300]},500)
    def do_POST(self):
        if not self.require_auth():return
        path=urlparse(self.path).path
        if path not in ("/api/answer","/api/refresh","/api/task","/api/ask","/api/reveal","/api/visual-review","/api/lab/start","/api/lab/action","/api/lab/board","/api/lab/lesson","/api/lab/note","/api/lab/chat","/api/academy/answer","/api/workshop/preview","/api/workshop/submit",
                        "/api/repertoire/save","/api/repertoire/takeaway","/api/repertoire/grade","/api/endgame/play",
                        "/api/opening-course/submit","/api/opening-course/knowledge","/api/opening-course/concept-grade",
                        "/api/masters/analyze","/api/masters/predict","/api/masters/ask",
                        "/api/settings/chesscom","/api/sparring/start","/api/sparring/move","/api/sparring/resign","/api/sparring/review","/api/sparring/draw","/api/sparring/continue"):
            self.send_error(404);return
        host=self.headers.get('Host','').lower().strip()
        origin=self.headers.get('Origin','')
        if not check_origin(origin,host,self._remote):
            self.respond({'error':'Cross-origin request denied'},403)
            return
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size<0 or size>4096:raise ValueError("Request too large")
            payload=json.loads(self.rfile.read(size)) if size else {}
            if not isinstance(payload,dict):raise ValueError("Expected a JSON object")
            if path=="/api/settings/chesscom":
                from account_settings import save,disable_sync
                if payload.get("disableSync"):
                    self.respond(disable_sync())
                else:
                    if payload.get("syncEnabled") is not True:
                        raise ValueError("Confirm that you want Chess Grind to sync this account")
                    self.respond(save(payload.get("username",""),True))
            elif path=="/api/masters/analyze":
                from masters_library import analyze
                self.respond(analyze(payload.get("id","")))
            elif path=="/api/masters/predict":
                if payload.get("roundId"):
                    from masters_prediction_retry import predict
                    self.respond(predict(payload.get("id",""),payload.get("ply",-1),
                                         payload.get("uci",""),payload.get("roundId")))
                else:
                    from masters_library import predict
                    self.respond(predict(payload.get("id",""),payload.get("ply",-1),
                                         payload.get("uci","")))
            elif path=="/api/masters/ask":
                from masters_tutor import ask
                self.respond(ask(payload.get("id",""),payload.get("ply",-1),
                    payload.get("side","Both"),payload.get("question",""),
                    payload.get("thread","")))
            elif path=="/api/opening-course/submit":
                from opening_mastery import submit
                self.respond(submit(payload.get("id",-1),payload.get("color","White"),
                 payload.get("role",""),payload.get("fen",""),payload.get("uci",""),
                 payload.get("assisted",False),round_id=payload.get("roundId")))
            elif path=="/api/opening-course/concept-grade":
                from opening_mastery import concept_grade
                self.respond(concept_grade(payload.get("id",-1),payload.get("color","White"),
                    payload.get("choice",-1),payload.get("assisted",False),
                    round_id=payload.get("roundId")))
            elif path=="/api/opening-course/knowledge":
                from opening_mastery import knowledge
                self.respond(knowledge(payload.get("id",-1),payload.get("color","White"),
                                       payload.get("answer","")))
            elif path=="/api/repertoire/takeaway":
                from opening_repertoire import save_takeaway
                self.respond(save_takeaway(payload.get("fen",""),payload.get("note","")))
            elif path=="/api/sparring/start":
                from sparring import start
                self.respond(start(payload.get("color","White"),payload.get("difficulty","casual"),
                                   payload.get("style","balanced")))
            elif path=="/api/sparring/move":
                from sparring import move
                self.respond(move(payload.get("gameId",""),payload.get("uci","")))
            elif path=="/api/sparring/resign":
                from sparring import resign
                self.respond(resign(payload.get("gameId","")))
            elif path=="/api/sparring/draw":
                from sparring import claim_draw
                self.respond(claim_draw(payload.get("gameId","")))
            elif path=="/api/sparring/continue":
                from sparring import continue_opponent
                self.respond(continue_opponent(payload.get("gameId","")))
            elif path=="/api/sparring/review":
                from sparring import review
                self.respond(review(payload.get("gameId","")))
            elif path=="/api/repertoire/save":
                from opening_repertoire import save
                self.respond(save(payload.get("fen",""),payload.get("uci","")))
            elif path=="/api/repertoire/grade":
                from opening_repertoire import grade_review
                self.respond(grade_review(payload.get("fen",""),payload.get("uci",""),
                    payload.get("assisted",False),payload.get("seconds",0)))
            elif path=="/api/endgame/play":
                from endgame_lab import play
                self.respond(play(payload.get("id",""),payload.get("uci",""),
                    payload.get("assisted",False),payload.get("seconds",0),
                    round_id=payload.get("roundId")))
            elif path=="/api/workshop/preview":
                from calculation_workshop import preview
                self.respond(preview(payload.get("gameId",""),payload.get("ply",0),
                                    payload.get("chosenUci","")))
            elif path=="/api/workshop/submit":
                from calculation_workshop import submit
                self.respond(submit(payload.get("gameId",""),payload.get("ply",0),
                                   payload.get("chosenUci",""),payload.get("predictedReply",""),
                                   payload.get("assisted",False)))
            elif path=="/api/academy/answer":
                from academy_curriculum import answer
                self.respond(answer(payload.get("unitId",""),payload.get("challengeId",""),
                                   payload.get("answer",""),payload.get("assisted",False),
                                   payload.get("seconds",0)))
            elif path=="/api/lab/chat":
                from board_chat import chat
                self.respond(chat(payload))
            elif path=="/api/lab/start":
                from learning_lab import session_start
                self.respond(session_start(payload.get("topic"),payload.get("mode","guided"),payload.get("count",5)))
            elif path=="/api/lab/action":
                from learning_lab import act
                self.respond(act(payload.get("sessionId",""),payload.get("stage",""),payload))
            elif path=="/api/lab/board":
                from learning_lab import board_question,positional
                if payload.get("question"):
                    self.respond(board_question(payload.get("fen",""),payload["question"],payload.get("candidate")))
                else:
                    self.respond(positional(payload.get("fen","")))
            elif path=="/api/lab/lesson":
                from learning_lab import lesson
                self.respond(lesson(payload.get("topic","")))
            elif path=="/api/lab/note":
                from learning_lab import save_note
                self.respond(save_note(payload.get("sessionId",""),payload.get("note","")))
            elif path=="/api/answer":
                code,data=submit_answer(payload)
                self.respond(data,code)
            elif path=="/api/ask":
                from tutor import respond
                self.respond(respond(payload.get("question","")))
            elif path=="/api/reveal":
                from coaching import record_reveal
                code,data=record_reveal(payload)
                self.respond(data,code)
            elif path=="/api/visual-review":
                from visual_review import review
                code,data=review(payload)
                self.respond(data,code)
            elif path=="/api/task":
                key=payload.get("taskId")
                if not isinstance(key,str):raise ValueError("Missing task ID")
                self.respond(complete(key,bool(payload.get("completed"))))
            elif path=="/api/refresh":
                from account_settings import current
                profile=current()
                if not (profile["configured"] and profile["syncEnabled"]):
                    self.respond({"error":"Set your own Chess.com username in Settings before syncing."},400)
                    return
                started=launch_refresh()
                self.respond({"status":"started" if started else "already running"},202 if started else 409)
        except (ValueError,TypeError) as exc:self.respond({"error":str(exc)[:300]},400)
        except Exception as exc:self.respond({"error":str(exc)[:300]},500)
    def log_message(self,fmt,*args):print(fmt%args,flush=True)

def serve():
    server=ThreadingHTTPServer(("127.0.0.1",int(__import__("os").environ.get("CHESSGRIND_PORT","8765"))),Handler)
    print("Chess Grind: http://127.0.0.1:"+__import__("os").environ.get("CHESSGRIND_PORT","8765"),flush=True)
    from account_settings import current
    settings=current()
    if settings["configured"] and settings["syncEnabled"] and __import__("os").environ.get("CHESSGRIND_SYNC_ON_START","0")=="1" and stale():launch_refresh()
    server.serve_forever()

if __name__=="__main__":serve()
