"""Index explicitly public-domain Internet Archive chess text files.

Rights are checked for each Archive ITEM (not assumed from the ability to download it).
Only imports plain-text source files; PDFs need edition-level rights review/OCR.
"""
import argparse
import hashlib
from urllib.parse import quote
import requests
from chess_grind import db,index_document

ITEMS=("chessfundamental33870gut",)
USER_AGENT="ChessGrindAgent/0.4 (personal chess study)"
def import_item(identifier):
    if identifier not in ITEMS:
        raise ValueError("This importer only accepts reviewed, explicitly public-domain items.")
    session=requests.Session()
    session.headers["User-Agent"]=USER_AGENT
    resp=session.get("https://archive.org/metadata/"+quote(identifier),timeout=35)
    resp.raise_for_status()
    meta=resp.json()
    info=meta.get("metadata",{})
    if "public domain" not in str(info.get("rights","")).lower():
        raise ValueError("The Archive item does not explicitly declare public-domain rights.")
    files=meta.get("files",[])
    choices=[f for f in files if f.get("name","").lower().endswith(".txt")
             and "meta" not in f.get("name","").lower()
             and int(f.get("size") or 0)>50000]
    if not choices:raise ValueError("No plain-text chess book file found")
    choices.sort(key=lambda f:(len(f["name"]),f["name"]))
    chosen=choices[0]["name"]
    url="https://archive.org/download/"+quote(identifier)+"/"+quote(chosen)
    result=session.get(url,timeout=60)
    result.raise_for_status()
    if len(result.content)<50000:raise ValueError("Downloaded text is unexpectedly small")
    page="https://archive.org/details/"+quote(identifier)
    book_id=hashlib.sha256(page.encode()).hexdigest()[:20]
    con=db()
    con.execute("INSERT OR REPLACE INTO books VALUES(?,?,?,?,?,?,?,?,?)",
        (book_id,info.get("title",identifier),info.get("creator",""),page,
         "public_domain_us_verified_archive_metadata","indexed","txt",None,"internet_archive"))
    n=index_document(con,book_id,result.content.decode("utf-8","replace"))
    con.commit()
    print(f"Indexed {n} passages from {info.get('title')} ({chosen}); source: {page}")
    return n
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("identifier",nargs="?",default=ITEMS[0])
    a=p.parse_args()
    import_item(a.identifier)
