#!/usr/bin/env python3
"""Chess Grind: source discovery, rights-aware library indexing, and adaptive daily lessons.
Python 3.10+, pip install -r requirements.txt. No API key needed for basic use.
"""
import argparse, datetime as dt, hashlib, json, os, random, re, sqlite3, sys, textwrap
from pathlib import Path
from urllib.parse import quote
import requests

HOME = Path(os.getenv('CHESS_GRIND_HOME', Path(__file__).resolve().parent/'userdata'))
DB = HOME/'chess.db'
SEED = [
 ('Chess Fundamentals','José Raúl Capablanca','https://www.gutenberg.org/ebooks/33870','https://www.gutenberg.org/ebooks/33870.txt.utf-8','public_domain_us'),
 ('Chess Strategy','Edward Lasker','https://www.gutenberg.org/ebooks/5614','https://www.gutenberg.org/ebooks/5614.txt.utf-8','public_domain_us'),
 ('Chess and Checkers: The Way to Mastership','Edward Lasker','https://www.gutenberg.org/ebooks/4913','https://www.gutenberg.org/ebooks/4913.txt.utf-8','public_domain_us'),
]
TOPICS = [
 ('blunder-check','Before every move: checks, captures, threats, and your opponent’s forcing reply.',800),
 ('hanging-pieces','Count attackers and defenders; identify pieces with no protection.',800),
 ('forks','Spot two or more targets attacked by one piece.',850),
 ('pins-and-skewers','Understand line-piece pressure and what sits behind the target.',950),
 ('mate-patterns','Recognize back-rank, ladder, and simple mating nets.',950),
 ('calculation','Calculate forcing moves without moving the pieces.',1100),
 ('pawn-endgames','Learn opposition, the square of the pawn, and king activity.',1150),
 ('rook-endgames','Practice active rooks, passed pawns, and basic rook endings.',1350),
 ('positional-play','Improve piece activity, weak squares, and pawn breaks.',1400),
 ('opening-plans','Understand development, center, king safety; avoid memorizing traps.',900),
 ('game-review','Analyze losses before looking at an engine.',800),
]
def db():
 HOME.mkdir(parents=True,exist_ok=True)
 con=sqlite3.connect(DB)
 con.row_factory=sqlite3.Row
 con.executescript('''CREATE TABLE IF NOT EXISTS books(id TEXT PRIMARY KEY,title TEXT,author TEXT,url TEXT,rights TEXT,status TEXT,format TEXT,year TEXT,source TEXT);
 CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,book_id TEXT,page INTEGER,body TEXT);
 CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(body,content='chunks',content_rowid='rowid');
 CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN INSERT INTO chunks_fts(rowid,body) VALUES(new.rowid,new.body); END;
 CREATE TABLE IF NOT EXISTS progress(topic TEXT PRIMARY KEY,seen INTEGER DEFAULT 0,correct INTEGER DEFAULT 0,last TEXT,interval_days INTEGER DEFAULT 1,next_due TEXT);
 CREATE TABLE IF NOT EXISTS sessions(day TEXT PRIMARY KEY,rating INTEGER,minutes INTEGER,notes TEXT);
 CREATE TABLE IF NOT EXISTS mistakes(day TEXT,topic TEXT,description TEXT);
 CREATE TABLE IF NOT EXISTS embeddings(chunk_id TEXT PRIMARY KEY,model TEXT,dimension INTEGER,vector BLOB);''')
 for title,author,url,download,rights in SEED:
  key=hashlib.sha256(url.encode()).hexdigest()[:20]
  con.execute('INSERT OR IGNORE INTO books VALUES(?,?,?,?,?,?,?,?,?)',(key,title,author,url,rights,'catalogued','txt',None,'gutenberg'))
 con.commit();return con

def clean(s): return re.sub(r'\s+',' ',s).strip()
def chunks(text,size=1200,overlap=180):
 text=clean(text)
 for start in range(0,len(text),size-overlap):
  part=text[start:start+size]
  if len(part)>100:yield part
  if start+size>=len(text):break

def index_document(con,book_id,text,page=0):
 n=0
 for j,part in enumerate(chunks(text)):
  id=hashlib.sha256((book_id+':'+str(page)+':'+str(j)).encode()).hexdigest()[:28]
  con.execute('INSERT OR IGNORE INTO chunks VALUES(?,?,?,?)',(id,book_id,page,part));n+=1
 return n

def ingest_file(args):
 p=Path(args.path)
 if not p.is_file():sys.exit('File not found')
 if not args.rights_confirmed:sys.exit('Supply --rights-confirmed only when you have verified permission to index this edition.')
 con=db();url=p.resolve().as_uri();book_id=hashlib.sha256(url.encode()).hexdigest()[:20]
 con.execute('INSERT OR REPLACE INTO books VALUES(?,?,?,?,?,?,?,?,?)',(book_id,args.title or p.stem,args.author or '',url,args.rights_label,'indexed',p.suffix.lower().strip('.'),None,'local'))
 total=0
 if p.suffix.lower()=='.pdf':
  import fitz
  doc=fitz.open(p)
  for i,page in enumerate(doc):
   txt=page.get_text('text')
   if len(txt.strip())>60:total+=index_document(con,book_id,txt,page=i+1)
 elif p.suffix.lower() in ('.txt','.md'):
  total=index_document(con,book_id,p.read_text(encoding='utf-8',errors='replace'))
 else:sys.exit('Use PDF, TXT or MD. Convert EPUB to TXT locally first.')
 con.commit();print(f'Indexed {total} passages from {p.name}. Image-only PDF pages require separate OCR.')

def gutenberg(args):
 con=db()
 for title,author,url,download,rights in SEED:
  print('Fetching:',title)
  r=requests.get(download,timeout=30,headers={'User-Agent':'ChessGrindResearch/0.1 (personal learning)'})
  if not r.ok:
   print('Skipped HTTP',r.status_code,'-- download this Gutenberg text manually if needed');continue
  id=hashlib.sha256(url.encode()).hexdigest()[:20]
  n=index_document(con,id,r.text)
  con.execute('UPDATE books SET status=? WHERE id=?',('indexed',id));con.commit()
  print(' ',n,'passages')

def discover(args):
 """DISCOVERY ONLY: Archive full-text availability is not permission to index."""
 con=db();query=args.query or '(title:chess OR subject:chess) AND mediatype:texts'
 endpoint='https://archive.org/advancedsearch.php'
 params={'q':query,'fl[]':['identifier','title','creator','year','rights','licenseurl'],'rows':min(args.limit,100),'page':1,'output':'json'}
 try:
  response=requests.get(endpoint,params=params,timeout=35,headers={'User-Agent':'ChessGrindResearch/0.1'});response.raise_for_status()
  data=response.json();docs=data.get('response',{}).get('docs',[])
 except Exception as ex:sys.exit('Archive search failed: '+str(ex))
 print('Search matches:',data.get('response',{}).get('numFound','?'),'| catalogued this call:',len(docs))
 for item in docs:
  ident=item.get('identifier'); title=item.get('title',ident);creator=item.get('creator','')
  if isinstance(creator,list):creator=', '.join(creator)
  if isinstance(title,list):title='; '.join(title)
  url='https://archive.org/details/'+quote(ident,safe='')
  rights='; '.join(str(item.get(k,'')) for k in ('rights','licenseurl')).strip('; ')
  id=hashlib.sha256(url.encode()).hexdigest()[:20]
  con.execute('INSERT OR IGNORE INTO books VALUES(?,?,?,?,?,?,?,?,?)',(id,title,creator,url,rights or 'unverified','discovered_rights_review_required','unknown',str(item.get('year','')),'internet_archive'))
  print('-',title[:90],'|',url)
 con.commit()
 print('IMPORTANT: Archive items remain discovery-only. Manually confirm edition-level rights and download access before indexing.')

def search(args):
 con=db();query=' '.join(re.findall(r'[\w]+',args.query))
 if not query:sys.exit('Enter search words')
 rows=con.execute('''SELECT books.title,books.author,books.url,chunks.page,chunks.body,bm25(chunks_fts) AS rank
 FROM chunks_fts JOIN chunks ON chunks.rowid=chunks_fts.rowid JOIN books ON books.id=chunks.book_id
 WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?''',(' OR '.join(query.split()),args.limit)).fetchall()
 for r in rows:
  print('\n###',r['title'],'| page',r['page'],'|',r['url'])
  print(textwrap.fill(r['body'][:500],width=95))
 if not rows:print('No indexed matching text. First run: python chess_grind.py gutenberg')

def vectors(args):
    """Local MiniLM ONNX semantic index and source-attributed similarity search."""
    from semantic_index import MODEL,build,search as dense_search,status
    if args.model not in (MODEL,'sentence-transformers/all-MiniLM-L6-v2'):
        sys.exit('This build supports local model '+MODEL)
    if args.action=='build':
        print(json.dumps(build(),indent=2))
    elif args.action=='search':
        if not args.query:sys.exit('Supply --query')
        for hit in dense_search(args.query,args.limit):
            print(f"\n{hit['similarity']:.3f} | {hit['title']} | {hit['url']}")
            print(textwrap.fill(hit['body'][:600],width=95))
    else:
        print(json.dumps(status(),indent=2))

def due(topic,rating,con,today):
 row=con.execute('SELECT * FROM progress WHERE topic=?',(topic,)).fetchone()
 if not row:return 20
 if row['next_due'] and row['next_due']<=today:return 30
 accuracy=row['correct']/max(1,row['seen'])
 return (1-accuracy)*15+max(0,5-row['seen'])*2

def daily(args):
 con=db();today=dt.date.today().isoformat()
 rating=args.rating
 if rating is None:
  logged=con.execute('SELECT rating FROM sessions ORDER BY day DESC LIMIT 1').fetchone()
  if logged:rating=logged['rating']
  else:
   from chesscom_api import status
   cached=status(con)
   rating=cached.get('rapid_rating') or 800
 items=sorted(TOPICS,key=lambda t:due(t[0],rating,con,today)+(5 if t[2]<=rating+250 else -10),reverse=True)
 plan=[t for t in items if t[2]<=rating+250][:3]
 print(f'CHESS GRIND | {today} | {rating} rated | 60-75 minutes')
 print('1. 10 min: review yesterday’s recurring blunder (write why it failed).')
 for i,(topic,desc,level) in enumerate(plan,2):
  print(f'{i}. 15 min: {topic.replace("-"," ").title()} — {desc}')
 print('5. 15-25 min: one 10+5 or 15+10 rated game; no blitz while rebuilding fundamentals.')
 print('6. 10 min: annotate each critical move BEFORE running engine analysis; record error category.')
 print('Checkpoints: blunders/game, tactical puzzle accuracy, and 30-game rolling rapid rating.')
 print('Log session: python chess_grind.py log --rating 820 --minutes 65 --topic forks --correct 7 --total 10 --notes "missed knight fork"')

def log(args):
 con=db();today=dt.date.today();date=today.isoformat()
 con.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)',(date,args.rating,args.minutes,args.notes))
 if args.topic:
  r=con.execute('SELECT * FROM progress WHERE topic=?',(args.topic,)).fetchone();seen=(r['seen'] if r else 0)+args.total;correct=(r['correct'] if r else 0)+args.correct
  old_interval=(r['interval_days'] if r else 1)
  interval=min(30,max(1,round(old_interval*(1.7 if args.total and args.correct/args.total>=.85 else .5))))
  con.execute('INSERT OR REPLACE INTO progress VALUES(?,?,?,?,?,?)',(args.topic,seen,correct,date,interval,(today+dt.timedelta(days=interval)).isoformat()))
  if args.notes:con.execute('INSERT INTO mistakes VALUES(?,?,?)',(date,args.topic,args.notes))
 con.commit();print('Saved',date,'rating',args.rating)

def catalog(args):
 con=db();rows=con.execute('SELECT title,year,source,status,url FROM books ORDER BY source,title LIMIT ?',(args.limit,)).fetchall()
 for r in rows:print(' | '.join(str(x) for x in r))
 print('Total catalogued:',con.execute('SELECT COUNT(*) FROM books').fetchone()[0]);print('Indexed passages:',con.execute('SELECT COUNT(*) FROM chunks').fetchone()[0])

def chesscom_command(args):
 from chesscom_api import ChessComClient, ChessComError, sync, status, export_pgn
 con=db()
 try:
  if args.action == 'sync':
   result=sync(con,username=args.username,max_rapid=args.max_games,all_types=not args.rapid_only)
  elif args.action == 'status':
   result=status(con,username=args.username)
  else:
   count=export_pgn(con,args.username,args.output)
   result={'exported_games':count,'path':args.output}
 except (ChessComError,requests.RequestException) as ex:
  sys.exit(str(ex))
 print(json.dumps(result,indent=2))

def analyze_command(args):
 from game_analysis import analyze
 print(json.dumps(analyze(args.username, args.depth, args.max_games),indent=2))

def serve_command(args):
 from web_app import serve
 serve()

def main():
 if hasattr(sys.stdout,'reconfigure'):
  sys.stdout.reconfigure(errors='replace')
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 a=sub.add_parser('discover',help='Catalog Internet Archive matches (rights review required)');a.add_argument('--query');a.add_argument('--limit',type=int,default=50);a.set_defaults(func=discover)
 a=sub.add_parser('gutenberg',help='Download and index curated Gutenberg classics');a.set_defaults(func=gutenberg)
 a=sub.add_parser('ingest',help='Index a rights-cleared PDF or text file');a.add_argument('path');a.add_argument('--title');a.add_argument('--author');a.add_argument('--rights-confirmed',action='store_true');a.add_argument('--rights-label',default='permission_verified_by_user');a.set_defaults(func=ingest_file)
 a=sub.add_parser('search',help='Search indexed passages');a.add_argument('query');a.add_argument('--limit',type=int,default=6);a.set_defaults(func=search)
 a=sub.add_parser('daily',help='Adaptive daily plan');a.add_argument('--rating',type=int);a.set_defaults(func=daily)
 a=sub.add_parser('log',help='Track training');a.add_argument('--rating',type=int,required=True);a.add_argument('--minutes',type=int,default=60);a.add_argument('--topic',choices=[x[0] for x in TOPICS]);a.add_argument('--correct',type=int,default=0);a.add_argument('--total',type=int,default=0);a.add_argument('--notes',default='');a.set_defaults(func=log)
 a=sub.add_parser('catalog');a.add_argument('--limit',type=int,default=100);a.set_defaults(func=catalog)
 a=sub.add_parser('chesscom',help='Sync all public Chess.com games; Rapid-only optional');a.add_argument('action',choices=['sync','status','export']);a.add_argument('--username',default='player');a.add_argument('--max-games',type=int,default=100000);a.add_argument('--rapid-only',action='store_true');a.add_argument('--output',default='all_chess_games.pgn');a.set_defaults(func=chesscom_command)
 a=sub.add_parser('analyze',help='Run local Stockfish game analysis');a.add_argument('--username',default='player');a.add_argument('--depth',type=int,default=10);a.add_argument('--max-games',type=int,default=30);a.set_defaults(func=analyze_command)
 a=sub.add_parser('serve',help='Open local web dashboard at http://127.0.0.1:8765');a.set_defaults(func=serve_command)
 a=sub.add_parser('vectors',help='Build/search optional true dense vector index');a.add_argument('action',choices=['build','search','status']);a.add_argument('--query');a.add_argument('--model',default='sentence-transformers/all-MiniLM-L6-v2');a.add_argument('--limit',type=int,default=6);a.set_defaults(func=vectors)
 args=p.parse_args();args.func(args)
if __name__=='__main__':main()
