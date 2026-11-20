"""Unattended Chess Grind: sync, engine, rights-aware books, vectors and lesson plan."""
from pathlib import Path
import datetime as dt
import json
import logging
import msvcrt
import sqlite3
import sys
from chess_grind import HOME,db,DB

HOME.mkdir(exist_ok=True,parents=True)
LOG=HOME/"daily-agent.log"
logging.basicConfig(filename=LOG,level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",encoding="utf-8")

def backup():
    if not DB.exists():return None
    directory=HOME/"backups"
    directory.mkdir(exist_ok=True,parents=True)
    dst=directory/(dt.date.today().isoformat()+".db")
    if not dst.exists():
        with sqlite3.connect(DB) as source,sqlite3.connect(dst) as target:
            source.backup(target)
    for old in sorted(directory.glob("*.db"))[:-14]:
        old.unlink(missing_ok=True)
    return str(dst)

def run():
    lock=HOME/"daily-agent.lock"
    with open(lock,"a+b") as handle:
        handle.seek(0)
        if not handle.read(1):handle.write(b"1")
        handle.flush();handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("Another chess analysis is running.")
            return {"skipped":"already running"}
        try:
            errors=[]
            from account_settings import current
            settings=current()
            username=settings["username"]
            result={"username":username or None}
            result["backup"]=backup()
            def stage(name,func):
                print("Chess Grind:",name,flush=True)
                try:
                    output=func()
                    result[name]=output
                    logging.info("%s: %s",name,str(output)[:400])
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
                    logging.exception("%s failed",name)
                    result[name]={"error":str(exc)[:300]}
                return result[name]
            from chesscom_api import sync
            from game_analysis import analyze
            from library_pipeline import inventory,index_permitted,search_pages
            from semantic_index import build
            from daily_coach import today
            if dt.date.today().weekday()==6:
                stage('catalog',lambda:search_pages(max_pages=12))
            stage("sync",lambda:sync(db(),username=username,max_rapid=100000,all_types=True)) if settings["syncEnabled"] and username else None
            stage("analysis",lambda:analyze(username,depth=11,max_games=200)) if settings["syncEnabled"] and username else None
            stage("inventory",lambda:inventory(limit=100,workers=6))
            stage("book_index",lambda:index_permitted(limit=20))
            stage("vectors",build)
            # Importing new games and analyses also refreshes the private
            # source-attributed chess graph. Embeddings are incremental and
            # run in small batches to keep daily jobs responsive.
            from chess_knowledge import build as build_chess_graph,vector_build as embed_chess_examples
            stage("chess_graph",lambda:build_chess_graph(include_masters=True,max_master_games=150))
            stage("chess_embeddings",lambda:embed_chess_examples(limit=250))
            plan=stage("daily_plan",today)
            if "error" not in plan:
                folder=HOME/"daily_plans"
                folder.mkdir(parents=True,exist_ok=True)
                path=folder/(dt.date.today().isoformat()+".json")
                path.write_text(json.dumps(plan,indent=2),encoding="utf-8")
                result["plan"]=str(path)
            result["warnings"]=errors
            logging.info("DAILY RESULT %s",json.dumps(result,default=str)[:1200])
            print(json.dumps(result,indent=2,default=str),flush=True)
            return result
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)

if __name__=="__main__":
    try:run()
    except Exception as exc:
        print("Daily agent failed:",str(exc),file=sys.stderr)
        raise
