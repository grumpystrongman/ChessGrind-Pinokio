"""Resumable-sized, bounded installer for exact 3-4-piece Syzygy endgames.

All 70 files (35 WDL/DTZ pairs) remain local under engine/syzygy and are
not distributed in the source repository. No remote chess services are used
during play. Larger 5-7-piece sets are deliberately not auto-installed.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
import urllib.request
from pathlib import Path
import chess
import chess.syzygy

MIRROR = "https://tablebase.lichess.ovh/tables/standard"
DEST = Path(__file__).resolve().parent / "engine" / "syzygy"
MAX_FILE = 30_000_000
MAX_TOTAL = 250_000_000

def names(piece_count=4):
    if piece_count not in (3,4):
        raise ValueError("Only the compact three- and four-piece set is supported.")
    return sorted(set(chess.syzygy.tablenames(piece_count=piece_count)))

def files_for(piece_count=4):
    return [{"name":n+ext,
             "url":MIRROR+"/"+("3-4-5-wdl" if ext==".rtbw" else "3-4-5-dtz")+"/"+n+ext}
            for n in names(piece_count) for ext in (".rtbw",".rtbz")]

def file_size(url):
    req=urllib.request.Request(url,method="HEAD",
       headers={"User-Agent":"ChessGrind-Syzygy/1.0"})
    with urllib.request.urlopen(req,timeout=18) as resp:
        n=int(resp.headers.get("Content-Length") or 0)
    if n<16 or n>MAX_FILE:
        raise ValueError("Unexpected Syzygy file length: "+url)
    return n

def checksum(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk=stream.read(1024*1024)
            if not chunk:break
            h.update(chunk)
    return h.hexdigest()

def fetch_file(item,expected,old_manifest):
    destination=DEST/item["name"]
    old=old_manifest.get(item["name"],{})
    if destination.is_file() and destination.stat().st_size==expected:
        digest=checksum(destination)
        if not old.get("sha256") or old.get("sha256")==digest:
            return {"name":item["name"],"bytes":expected,"sha256":digest,"state":"already-present"}
    part=destination.with_name(destination.name+".part")
    part.unlink(missing_ok=True)
    request=urllib.request.Request(item["url"],
            headers={"User-Agent":"ChessGrind-Syzygy/1.0"})
    try:
        with urllib.request.urlopen(request,timeout=45) as response,part.open("wb") as output:
            total=0
            while True:
                chunk=response.read(512*1024)
                if not chunk:break
                total+=len(chunk)
                if total>expected or total>MAX_FILE:
                    raise RuntimeError("File exceeds announced size: "+item["name"])
                output.write(chunk)
        if total!=expected:raise RuntimeError("Incomplete download: "+item["name"])
        os.replace(part,destination)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return {"name":item["name"],"bytes":expected,
            "sha256":checksum(destination),"state":"downloaded"}

def install(piece_count=4):
    entries=files_for(piece_count)
    DEST.mkdir(parents=True,exist_ok=True)
    manifest_file=DEST/"installed-manifest.json"
    try:old={x["name"]:x for x in json.loads(manifest_file.read_text("utf8")).get("files",[])}
    except (FileNotFoundError,ValueError,KeyError):old={}
    lengths={f["name"]:file_size(f["url"]) for f in entries}
    total=sum(lengths.values())
    if total>MAX_TOTAL:raise RuntimeError("Refusing unexpectedly large tablebase download.")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        tasks=[executor.submit(fetch_file,item,lengths[item["name"]],old) for item in entries]
        result=[future.result() for future in tasks]
    pairs=sum(all((DEST/(n+ext)).is_file() for ext in (".rtbw",".rtbz"))
              for n in names(piece_count))
    if pairs!=len(names(piece_count)):raise RuntimeError("Incomplete WDL/DTZ collection.")
    # Probe real known endgames. A file with a valid size alone is not proof
    # of correct Syzygy data.
    probes=[
       ("KQvK","7k/8/8/8/8/8/4K3/4Q3 w - - 0 1",2),
       ("KRvK","7k/8/8/8/8/8/4K3/4R3 w - - 0 1",2),
       ("KPvK","7k/8/8/8/8/8/4KP2/8 w - - 0 1",2),
    ]
    verified=[]
    with chess.syzygy.open_tablebase(str(DEST)) as tb:
        for kind,fen,expected_wdl in probes:
            board=chess.Board(fen)
            if not board.is_valid():raise RuntimeError("Installer probe FEN invalid")
            wdl=tb.probe_wdl(board)
            dtz=tb.probe_dtz(board)
            if wdl!=expected_wdl:raise RuntimeError("Unexpected tablebase result: "+kind)
            verified.append({"type":kind,"wdl":wdl,"dtz":dtz})
    receipt={"pieceLimit":piece_count,"pairs":pairs,"expectedPairs":len(names(piece_count)),
             "bytes":total,"source":MIRROR,"probeTests":verified,
             "files":sorted(result,key=lambda x:x["name"])}
    manifest_file.write_text(json.dumps(receipt,indent=2),encoding="utf8")
    return receipt

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--pieces",type=int,choices=(3,4),default=4)
    opts=parser.parse_args()
    out=install(opts.pieces)
    print("Installed "+str(out["pairs"])+" exact Syzygy WDL/DTZ pairs ("+
          str(out["bytes"])+" total bytes).")
