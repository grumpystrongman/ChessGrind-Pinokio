"""Internet Archive chess-library inventory and rights-checked text/PDF ingestion."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from html import unescape
import io
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import quote

import requests
from chess_grind import db,index_document

BASE="https://archive.org"
HEADERS={"User-Agent":"ChessGrindResearch/0.6 (personal chess education; public profile player)"}
SEARCH='(title:chess OR subject:chess) AND mediatype:texts'

def book_id(url):return hashlib.sha256(url.encode()).hexdigest()[:20]

def scrub(v):
    if isinstance(v,list):return ", ".join(str(x) for x in v)
    return str(v or "")

def ensure(con):
    con.execute("""CREATE TABLE IF NOT EXISTS book_files(
      book_id TEXT NOT NULL, file_name TEXT NOT NULL, format TEXT NOT NULL,
      size INTEGER NOT NULL, url TEXT NOT NULL,
      PRIMARY KEY(book_id,file_name))""")
    con.execute("""CREATE TABLE IF NOT EXISTS library_audit(
      book_id TEXT PRIMARY KEY, decision TEXT, notes TEXT, reviewed_at TEXT)""")
    con.commit()

def search_pages(max_pages=10,rows=500):
    con=db();ensure(con)
    total_seen=0;created=0
    for page in range(1,max_pages+1):
        response=requests.get(BASE+'/advancedsearch.php',
              params={'q':SEARCH,'fl[]':['identifier','title','creator','year','rights','licenseurl'],
                      'rows':rows,'page':page,'output':'json','sort[]':'titleSorter asc'},
              headers=HEADERS,timeout=40)
        response.raise_for_status()
        docs=response.json().get("response",{}).get("docs",[])
        if not docs:break
        for item in docs:
            identifier=item.get("identifier")
            if not identifier:continue
            page_url=BASE+'/details/'+quote(identifier,safe="")
            key=book_id(page_url)
            rights=scrub(item.get("rights")) or "unverified"
            cur=con.execute("""INSERT OR IGNORE INTO books
              (id,title,author,url,rights,status,format,year,source)
              VALUES(?,?,?,?,?,?,?,?,?)""",
              (key,scrub(item.get('title')) or identifier,scrub(item.get('creator')),
              page_url,rights,'discovered_rights_review_required','unknown',
              scrub(item.get('year')),'internet_archive'))
            created+=max(0,cur.rowcount)
            total_seen+=1
        con.commit()
        print(f"Catalog page {page}: {len(docs)} records; {created} new",flush=True)
    return {"seen":total_seen,"new":created,"catalog":con.execute("SELECT count(*) FROM books").fetchone()[0]}

def right_to_index(meta):
    info=meta.get("metadata",{})
    if str(info.get("is_restricted","")).lower() in ("true","1","yes"):return False,"restricted"
    claims=(scrub(info.get("rights"))+" "+scrub(info.get("licenseurl"))).lower()
    if any(x in claims for x in ('copyright status unknown','may be protected','all rights reserved',
            'not in the public domain','in copyright','rights reserved')):
        return False,"copyright or unknown status"
    explicit=('public domain in the usa' in claims or 'public domain in the united states' in claims
       or 'public domain mark' in claims or 'creativecommons.org/publicdomain/mark' in claims
       or 'creativecommons.org/publicdomain/zero' in claims
       or 'creativecommons.org/licenses/by/' in claims
       or 'creativecommons.org/licenses/by-sa/' in claims)
    if not explicit:return False,"no explicit reuse permission"
    # Archive metadata can be supplied by any uploader. Do not automatically copy
    # contemporary commercially published books based on an uploader's license tag.
    title=scrub(info.get('title')).lower()
    if any(term in title for term in ('newspaper','constitution','magazine','comic','daily news','catalogue','catalog','bookseller','bibliography','history of chess','literatur des schachspiels','game of the chesse')):
        return False,'non-instructional periodical or catalog requires manual review'
    if not any(term in title for term in ('chess','schach','draught','checkers','chaturanga','échecs','echecs','scacchi','ajedrez','gambit','checkmate','tactics','openings','endgames')):
        return False,'title does not establish that this is a chess instructional work'
    year_text=scrub(info.get('year') or info.get('date'))
    found=re.search(r'(?<!\d)(1[789]\d{2}|20\d{2})(?!\d)',year_text)
    year=int(found.group(1)) if found else None
    if year is None or year>1930:
        return False,'publication year not independently verified as pre-1931; manual rights review required'
    return True,claims[:400]

def _file_info(f):
    name=f.get('name') or ''
    extension=name.lower().rsplit('.',1)[-1]
    if extension not in ('pdf','txt','epub','djvu'):return None
    if '_meta.' in name.lower() or name.startswith('__'):return None
    return name,extension,int(f.get('size') or 0)

def inspect(identifier):
    response=requests.get(BASE+'/metadata/'+quote(identifier,safe=""),headers=HEADERS,timeout=40)
    response.raise_for_status()
    return response.json()

def inventory(limit=300,workers=6):
    """Inspect Archive item metadata concurrently, retaining a safe rights audit."""
    con=db();ensure(con)
    rows=con.execute("""SELECT id,url FROM books WHERE source='internet_archive'
      AND id NOT IN (SELECT book_id FROM library_audit)
      ORDER BY CASE WHEN url LIKE '%gut' THEN 0
                    WHEN lower(rights) LIKE '%public domain%' THEN 1 ELSE 2 END,
               title LIMIT ?""",(limit,)).fetchall()
    counts={"inspected":0,"pdfs":0,"clear":0,"restricted":0,"failed":0}
    def fetch(row):
        identifier=row["url"].split("/details/")[-1]
        for attempt in range(3):
            try:
                return row,inspect(identifier),None
            except requests.RequestException as ex:
                if attempt==2:return row,None,str(ex)
                time.sleep(min(3*(attempt+1),6))
        return row,None,"retry failure"
    with ThreadPoolExecutor(max_workers=max(1,min(workers,8))) as pool:
        futures=[pool.submit(fetch,row) for row in rows]
        for future in as_completed(futures):
            row,meta,error=future.result()
            if error:
                counts["failed"]+=1
                continue
            try:
                eligible,reason=right_to_index(meta)
                counts["clear" if eligible else "restricted"]+=1
                for entry in meta.get("files",[]):
                    f=_file_info(entry)
                    if not f:continue
                    name,kind,size=f
                    identifier=row["url"].split("/details/")[-1]
                    url=BASE+"/download/"+quote(identifier,safe="")+"/"+quote(name)
                    con.execute("""INSERT OR REPLACE INTO book_files VALUES(?,?,?,?,?)""",
                         (row["id"],name,kind,size,url))
                    if kind=="pdf":counts["pdfs"]+=1
                con.execute("""INSERT OR REPLACE INTO library_audit
                    VALUES(?,?,?,datetime('now'))""",
                    (row["id"],"index_permitted" if eligible else "discovery_only",reason))
                con.commit()
                counts["inspected"]+=1
            except (ValueError,KeyError,sqlite3.Error) as ex:
                counts["failed"]+=1
                print("Metadata handling error:",str(ex)[:100],flush=True)
            if (counts["inspected"]+counts["failed"])%50==0:
                print("Inventory progress",counts,flush=True)
    return counts

def text_candidates(meta):
    available=[]
    for f in meta.get("files",[]):
        entry=_file_info(f)
        if not entry:continue
        name,kind,size=entry
        if size<30000 or size>25_000_000:continue
        low=name.lower()
        if kind=='txt' and ('meta' not in low):
            # Prefer Gutenberg text, Archive OCR text (djvu text), then others.
            priority=0 if ('pg' in low or re.search(r'^\d+\.txt$',low)) else 1 if '_djvu.txt' in low else 2
            available.append((priority,size,name,'txt'))
        elif kind=='pdf':
            available.append((4,size,name,'pdf'))
    return sorted(available)

def index_permitted(limit=12,max_bytes=12_000_000):
    import pymupdf as fitz
    con=db();ensure(con)
    rows=con.execute("""SELECT b.id,b.url,b.status FROM books b
       JOIN library_audit a ON a.book_id=b.id
       WHERE a.decision='index_permitted' AND b.status!='indexed'
       ORDER BY b.title LIMIT ?""",(limit,)).fetchall()
    outcome={"indexed_books":0,"new_passages":0,"skipped":0}
    for row in rows:
        identifier=row["url"].split("/details/")[-1]
        try:
            metadata=inspect(identifier)
            eligible,why=right_to_index(metadata)
            if not eligible:
                con.execute("UPDATE library_audit SET decision='manual_rights_review',notes=? WHERE book_id=?",(why,row['id']))
                con.commit()
                outcome['skipped']+=1;continue
            choices=text_candidates(metadata)
            if not choices:
                con.execute("UPDATE library_audit SET decision='no_extractable_text',notes='No accessible text or PDF discovered' WHERE book_id=?",(row['id'],))
                con.commit()
                outcome['skipped']+=1;continue
            for _,size,name,kind in choices:
                if size>max_bytes:continue
                url=BASE+'/download/'+quote(identifier,safe="")+'/'+quote(name)
                r=requests.get(url,headers=HEADERS,timeout=80)
                if not r.ok or len(r.content)<20000:continue
                if kind=='txt':
                    text=r.content.decode('utf-8','replace')
                    if text.count('\ufffd')>len(text)*.02:
                        text=r.content.decode('cp1252','replace')
                    if len(text.strip())<20000:continue
                    n=index_document(con,row["id"],text)
                else:
                    try:
                        doc=fitz.open(stream=r.content,filetype="pdf")
                        if doc.needs_pass:continue
                        n=0
                        for i,page in enumerate(doc):
                            text=page.get_text("text")
                            if len(text.strip())>=80:n+=index_document(con,row["id"],text,page=i+1)
                    except Exception:
                        continue
                    if n<5:continue
                con.execute("""UPDATE books SET status='indexed',format=?,rights=? WHERE id=?""",
                    (kind,why[:300],row['id']))
                con.commit()
                outcome["indexed_books"]+=1;outcome["new_passages"]+=n
                print("Indexed",n,kind,"passages from",identifier,flush=True)
                break
            else:outcome["skipped"]+=1
        except Exception as ex:
            outcome["skipped"]+=1
            print("Index skipped",identifier,str(ex)[:120],flush=True)
    return outcome

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=['catalog','inventory','index','all'])
    p.add_argument("--pages",type=int,default=10)
    p.add_argument("--limit",type=int,default=250)
    args=p.parse_args()
    if args.action in ("catalog","all"):print(json.dumps(search_pages(args.pages)))
    if args.action in ("inventory","all"):print(json.dumps(inventory(args.limit)))
    if args.action in ("index","all"):print(json.dumps(index_permitted(args.limit)))
