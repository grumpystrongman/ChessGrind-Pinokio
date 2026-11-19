"""Local dense semantic retrieval for rights-cleared chess texts.

Uses a downloaded ONNX sentence embedding model.  Passages and vectors stay
on this computer; source URLs are preserved for attribution.
"""
import argparse
import json
import math
import sqlite3
import struct
from chess_grind import db

MODEL="sentence-transformers/all-MiniLM-L6-v2"
_model=None

def model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model=TextEmbedding(model_name=MODEL,cache_dir=str(__import__('chess_grind').HOME/'models'))
    return _model

def ensure(con):
    con.execute("""CREATE TABLE IF NOT EXISTS semantic_vectors(
      chunk_id TEXT NOT NULL, model TEXT NOT NULL,
      dimensions INTEGER NOT NULL, payload BLOB NOT NULL,
      PRIMARY KEY (chunk_id,model))""")
    con.commit()

def pack(v):
    numbers=[float(x) for x in v]
    magnitude=math.sqrt(sum(x*x for x in numbers)) or 1
    return struct.pack('<'+str(len(numbers))+'f',*(x/magnitude for x in numbers))

def unpack(blob,dimensions):
    return struct.unpack('<'+str(dimensions)+'f',blob)

def build(batch_size=32):
    con=db();ensure(con)
    rows=con.execute("""SELECT c.id,c.body FROM chunks c LEFT JOIN semantic_vectors v
      ON v.chunk_id=c.id AND v.model=? WHERE v.chunk_id IS NULL ORDER BY c.id""",(MODEL,)).fetchall()
    print("Generating dense embeddings for",len(rows),"passages",flush=True)
    embedding=model()
    total=0
    for i in range(0,len(rows),batch_size):
        group=rows[i:i+batch_size]
        embeddings=list(embedding.embed([r["body"] for r in group],batch_size=batch_size))
        for row,v in zip(group,embeddings):
            p=pack(v)
            con.execute("INSERT OR REPLACE INTO semantic_vectors VALUES(?,?,?,?)",
                 (row["id"],MODEL,len(p)//4,p))
            total+=1
        con.commit()
        print(f"Vectorized {min(i+batch_size,len(rows))}/{len(rows)}",flush=True)
    return {"created":total,"stored":con.execute("SELECT count(*) FROM semantic_vectors WHERE model=?",(MODEL,)).fetchone()[0],"model":MODEL}

def search(query,limit=5):
    con=db();ensure(con)
    question=pack(next(iter(model().query_embed(query))))
    a=unpack(question,len(question)//4)
    all_rows=con.execute("SELECT chunk_id,dimensions,payload FROM semantic_vectors WHERE model=?",(MODEL,)).fetchall()
    matches=[]
    for row in all_rows:
        if row["dimensions"]!=len(a):continue
        b=unpack(row["payload"],row["dimensions"])
        cosine=sum(x*y for x,y in zip(a,b))
        matches.append((cosine,row["chunk_id"]))
    from book_quality import dedup_passages
    candidates=[]
    # Rerank a wider semantic shortlist for actual teaching quality. Archive
    # OCR often includes library stamps and garbled front matter.
    for similarity,ident in sorted(matches,reverse=True)[:max(100,limit*24)]:
        r=con.execute("""SELECT b.title,b.author,b.url,c.page,c.body
           FROM chunks c JOIN books b ON b.id=c.book_id WHERE c.id=?""",(ident,)).fetchone()
        if not r:continue
        hit=dict(r);body=hit['body'];title=hit['title'].lower()
        lower=body.lower()
        bonus=0.065 if 'chess fundamentals' in title else 0.0
        bonus+=0.025 if 'introduction' in title else 0.0
        if any(x in lower[:300] for x in ('research libraries','nypl research','presented to the new york','project gutenberg ebook')):
            bonus-=0.16
        if body.count('\ufffd')>=4:bonus-=0.13
        # Readable paragraphs have ordinary chess vocabulary, not just OCR noise.
        common=sum(lower.count(' '+w+' ') for w in ('the','and','move','pawn','piece','king','white','black'))
        if common<=1:bonus-=0.055
        hit['similarity']=round(similarity,3)
        candidates.append((similarity+bonus,hit))
    ordered=[h for _,h in sorted(candidates,key=lambda x:x[0],reverse=True)]
    return dedup_passages(ordered,limit)

def status():
    con=db();ensure(con)
    return {"model":MODEL,
            "embedded":con.execute("SELECT COUNT(*) FROM semantic_vectors WHERE model=?",(MODEL,)).fetchone()[0],
            "passages":con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("build","search","status"))
    parser.add_argument("--query",default="How do I stop hanging pieces?")
    args=parser.parse_args()
    if args.action=="build":print(json.dumps(build()))
    elif args.action=="search":print(json.dumps(search(args.query),indent=2))
    else:print(json.dumps(status()))
