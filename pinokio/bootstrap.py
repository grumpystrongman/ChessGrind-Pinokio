"""Windows x64 Pinokio bootstrap. All installed user data is local to this folder."""
from __future__ import annotations
import argparse,io,os,sqlite3,subprocess,sys,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
HOME=ROOT/"userdata"
SEED=ROOT/"data"/"bootstrap_content.sqlite3"
ENGINE=ROOT/"engine"/"stockfish-windows-x86-64-universal.exe"
ENGINE_URL="https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip"
def env(port):
 result=os.environ.copy()
 result["CHESS_GRIND_HOME"]=str(HOME)
 result["CHESSGRIND_LOCAL_ONLY"]="1"
 result["CHESSGRIND_PORT"]=str(port)
 result["CHESSGRIND_SYNC_ON_START"]="0"
 result["CHESSGRIND_USERNAME"]=get_account() or "player"
 result["STOCKFISH_PATH"]=str(ENGINE)
 return result
def get_account():
 cfg=HOME/"chesscom_profile.json"
 if not cfg.is_file():return None
 try:
  import json,re
  value=json.loads(cfg.read_text(encoding="utf8")).get("username","")
  return value if isinstance(value,str) and re.fullmatch("[A-Za-z0-9_-]{3,25}",value) else None
 except (OSError,ValueError,TypeError,AttributeError):return None
def install_engine(skip_download=False):
 if ENGINE.is_file():return
 if sys.platform!="win32":raise RuntimeError("This Chess Grind beta is supported on Windows x64 only.")
 if skip_download:raise RuntimeError("Stockfish is not installed. Select Install to finish setup.")
 print("Downloading official Stockfish 19 universal Windows binary...",flush=True)
 request=urllib.request.Request(ENGINE_URL,headers={"User-Agent":"ChessGrind-Pinokio/0.1"})
 with urllib.request.urlopen(request,timeout=180) as response:
  archive=response.read(200*1024*1024+1)
 if len(archive)>200*1024*1024:raise RuntimeError("Stockfish download is unexpectedly large.")
 with zipfile.ZipFile(io.BytesIO(archive)) as z:
  items=[x for x in z.namelist() if x.lower().endswith("stockfish-windows-x86-64-universal.exe")]
  if len(items)!=1:raise RuntimeError("Unexpected Stockfish archive contents.")
  content=z.read(items[0])
  if len(content)<1000000:raise RuntimeError("Invalid Stockfish executable size.")
  ENGINE.parent.mkdir(exist_ok=True,parents=True)
  tmp=ENGINE.with_suffix(".part")
  tmp.write_bytes(content)
  tmp.replace(ENGINE)
  licenses=[x for x in z.namelist() if x.lower().endswith("copying.txt")]
  if licenses:(ENGINE.parent/"COPYING.txt").write_bytes(z.read(licenses[0]))
 print("Stockfish ready. Source and GPL-3.0: https://github.com/official-stockfish/Stockfish",flush=True)
def seed_data():
 if not SEED.is_file():raise RuntimeError("Missing packaged chess learning library.")
 HOME.mkdir(exist_ok=True,parents=True)
 os.environ.update(env(8765))
 from chess_grind import db
 from masters_library import ensure
 con=db();ensure(con)
 try:
  con.execute("ATTACH DATABASE ? AS seed",(str(SEED),))
  columns="id,white,black,event,site,date,year,result,eco,opening,plies,winner,era,source_player,source_url,featured,feature_reason,pgn"
  con.execute("INSERT OR IGNORE INTO master_games("+columns+") SELECT "+columns+" FROM seed.master_games")
  con.execute("""INSERT OR IGNORE INTO books(id,title,author,url,rights,status,format,year,source)
     SELECT id,title,author,url,rights,status,format,year,source FROM seed.books""")
  con.execute("""INSERT OR IGNORE INTO chunks(id,book_id,page,body)
     SELECT id,book_id,page,body FROM seed.chunks""")
  con.commit()
  print("Historical study games available:",
   con.execute("SELECT count(*) FROM master_games").fetchone()[0],flush=True)
 finally:
  con.close()
def doctor():
 print("Python:",sys.version.split()[0],flush=True)
 print("Private Chess Grind data:",str(HOME),flush=True)
 print("Stockfish:",ENGINE.is_file(),flush=True)
 print("Learning data:",SEED.is_file(),flush=True)
 import chess,requests,jwt
 if ENGINE.is_file():
  import chess.engine
  with chess.engine.SimpleEngine.popen_uci(str(ENGINE),timeout=25) as p:
   print("Engine validated:",p.id.get("name","UCI ready"),flush=True)
 os.environ.update(env(8765))
 from chess_grind import db
 con=db()
 try:
  print("History games:",con.execute("SELECT count(*) FROM master_games").fetchone()[0],flush=True)
 finally:con.close()
 from verified_chess import tablebase_status
 tb=tablebase_status()
 print("Exact Syzygy tablebases:",str(tb["pairs"])+" WDL/DTZ pairs; up to "+str(tb["maxCompletePieces"])+" pieces",flush=True)
 from local_ai_setup import readiness
 ai=readiness()
 print("Conversational AI:",ai["conversationalAIReady"],
       "("+str(ai["selectedChatModel"] or "no local model")+")",flush=True)
 print("Neural character voices:",ai["neuralVoicesReady"],flush=True)
 print("Personal Chess.com account:",get_account() or "Not yet connected",flush=True)
 print("External listening: OFF. Online invites: OFF.",flush=True)
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("action",choices=("setup","launch","doctor"))
 parser.add_argument("--port",type=int,default=8765)
 parser.add_argument("--skip-engine",action="store_true")
 opts=parser.parse_args()
 if not 1024<=opts.port<=65535:parser.error("Port must be between 1024 and 65535")
 os.environ.update(env(opts.port))
 if opts.action=="setup":
  install_engine(opts.skip_engine)
  seed_data()
  try:
   from install_syzygy import install
   result=install(4)
   print("Exact endgame tablebases: "+str(result["pairs"])+" of "+str(result["expectedPairs"])+" pairs; "+str(result["bytes"])+" bytes.",flush=True)
  except Exception as exc:
   # A network outage must not stop Stockfish / local game installation.
   print("Optional tablebase installation unavailable: "+str(exc)[:250],flush=True)
  try:
   from chess_knowledge import build
   summary=build(include_masters=True,max_master_games=150)
   print("Local chess knowledge graph prepared: "+str(summary["examples"])+" sourced examples.",flush=True)
   try:
    from chess_knowledge import vector_build
    vectors=vector_build()
    print("Chess example embeddings indexed: "+str(vectors["vectors"]),flush=True)
   except Exception as exc:
    print("Semantic vectors unavailable; exact and full-text study remain active: "+str(exc)[:180],flush=True)
  except Exception as exc:
   print("Knowledge graph setup warning: "+str(exc)[:250],flush=True)
  # Full Pinokio installation includes conversation AI and neural voices.
  # External installers and large models are explicitly announced in logs.
  # Failures remain visible with a one-click Repair action.
  from local_ai_setup import setup as setup_local_ai
  ready=setup_local_ai("all")
  if not ready["success"]:
   print("WARNING: ChessGrind setup is PLAYABLE, but conversational AI or neural voice was not fully installed.",flush=True)
   print("Use Pinokio > Repair local AI & character voices to complete the missing parts.",flush=True)
  doctor()
 elif opts.action=="doctor":doctor()
 else:
  if not (HOME/"chess.db").exists():seed_data()
  install_engine(skip_download=True)
  # Ollama's Windows background process may not be running after restart.
  # Starting a preinstalled local server does not download or modify models.
  try:
   from local_ai_setup import launch_server,executable
   if executable():launch_server()
  except (OSError,RuntimeError,ValueError) as exc:
   print("Local AI startup warning: "+str(exc)[:160],flush=True)
  print("Starting Chess Grind on http://127.0.0.1:"+str(opts.port),flush=True)
  sys.exit(subprocess.call([sys.executable,"chess_grind.py","serve"],cwd=ROOT,env=env(opts.port)))
if __name__=="__main__":main()
