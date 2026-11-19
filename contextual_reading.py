"""Position-grounded book retrieval with a small, auditable concept graph.

Unlike a global 'top chess book' carousel, this maps:
  VERIFIED BOARD / MOVE -> TEACHING CONCEPT -> MATCHING SOURCE SENTENCES
and refuses to show unrelated or unreadable excerpts. It is not a general
purpose knowledge graph extracted by a language model: graph edges are
deterministically supported by chess geometry and explicit text evidence.
"""
from __future__ import annotations
import re
import math
import hashlib
import sqlite3
from collections import defaultdict
import chess
from chess_grind import db
from motifs import classify
from book_quality import norm,work_key
from lesson_explainer import move_reasons
from visual_coach import attack_map

# Tight, inspectable concept vocabulary; match real text, not generic 'chess'.
# Terms are exact regexes; concept links store matched source evidence.
CONCEPTS = {
 "fork":(r"\bforks?\b",r"\bdouble attack\b"),
 "pin":(r"\bpinn(?:ed|ing|s)?\b",r"\babsolute pin\b",r"\brelative pin\b"),
 "skewer":(r"\bskewers?\b",r"\b(?:queen|king) (?:in front|before) of\b"),
 "discovered attack":(r"\bdiscover(?:ed|y) attack\b",r"\bopen(?:ing|ed)? (?:a )?line\b"),
 "checkmate":(r"\bcheckmate\b",r"\bmating net\b",r"\bmate in (?:one|two|three)\b"),
 "check":(r"\bcheck\b",r"\bforcing (?:move|reply|check)\b"),
 "material exchange":(r"\bcaptur(?:e|es|ing)\b",r"\bexchange of (?:pieces|pawns)\b",r"\bwin(?:ning)? (?:a |the )?(?:pawn|piece|queen|rook|bishop|knight)\b"),
 "hanging piece":(r"\bundefended\b",r"\bunprotected\b",r"\bhanging (?:piece|pawn|queen|rook|bishop|knight)\b"),
 "development":(r"\bdevelop(?:ed|ment|ing)?\b",r"\bbring out (?:the |your )?(?:pieces|knights|bishops)\b"),
 "central control":(r"\bcontrol (?:of )?(?:the )?(?:centre|center)\b",r"\b(?:central|centre|center) (?:square|pawn|control)\b"),
 "castling":(r"\bcastl(?:e|es|ing|ed)\b",r"\bking.?s safety\b"),
 "king safety":(r"\bking (?:safety|expos(?:ure|ed)|attack)\b",r"\b(?:un)?safe king\b"),
 "pawn structure":(r"\bpawn structure\b",r"\bpawn chain\b",r"\bdoubled pawns?\b"),
 "passed pawn":(r"\bpassed pawns?\b",r"\bpromotion\b",r"\badvance(?:d|ment)? (?:the |a )?pawn\b"),
 "opposition":(r"\bopposition\b",r"\bking and pawn end(?:ing|game)\b"),
 "knight activity":(r"\bknights?\b",r"\bkt\b",r"\boutpost\b"),
 "bishop activity":(r"\bbishops?\b",r"\bdiagonal\b"),
 "rook activity":(r"\brooks?\b",r"\bopen file\b"),
 "queen activity":(r"\bqueen\b",r"\bq\.\b"),
}
REGEX={k:[re.compile(pattern,re.I) for pattern in seq] for k,seq in CONCEPTS.items()}
BOOKSTOP=("digitized by google","google books","library of congress","university of california",
          "scanned by","the above works","frontispiece","published by","catalogue of books",
          "this edition","all rights reserved","price of this","to young players")
# Specific ideas dominate; a piece name without the idea isn't a lesson.
SPECIFIC={"fork","pin","skewer","discovered attack","checkmate","hanging piece",
 "king safety","castling","passed pawn","opposition","pawn structure","central control",
 "development","material exchange"}
MOTIF={"forks and double attacks":"fork","pins":"pin",
       "checkmate patterns":"checkmate","forcing checks":"check",
       "missed captures":"material exchange","piece safety":"hanging piece",
       "opening decisions":"development","endgame technique":"passed pawn"}
TOPIC_DEFAULTS={"opening decisions":["development","central control","castling"],
                "endgame technique":["passed pawn","opposition"],
                "forcing checks":["check","checkmate"],
                "missed captures":["material exchange","hanging piece"],
                "pins":["pin"],"forks and double attacks":["fork"],
                "checkmate patterns":["checkmate"],
                "piece safety":["hanging piece"]}
PIECE_CONCEPTS={chess.KNIGHT:"knight activity",chess.BISHOP:"bishop activity",
 chess.ROOK:"rook activity",chess.QUEEN:"queen activity"}

def concept_hits(text):
    return {concept for concept,patterns in REGEX.items()
            if any(pattern.search(text or "") for pattern in patterns)}

def ensure(con):
    con.executescript("""CREATE TABLE IF NOT EXISTS chess_concepts(
       key TEXT PRIMARY KEY,description TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS chess_passage_links(
       chunk_id TEXT NOT NULL,concept TEXT NOT NULL,
       PRIMARY KEY(chunk_id,concept)
    );
    CREATE INDEX IF NOT EXISTS chess_passage_links_concept
       ON chess_passage_links(concept);
    """)
    con.executemany("INSERT OR IGNORE INTO chess_concepts VALUES (?,?)",
           [(k,"Chess concept linked to verified text: "+k) for k in CONCEPTS])
    con.commit()

def graph_status(con=None):
    own=con is None;con=con or db();ensure(con)
    result={"concepts":con.execute("SELECT COUNT(*) FROM chess_concepts").fetchone()[0],
      "linkedPassages":con.execute("SELECT COUNT(DISTINCT chunk_id) FROM chess_passage_links").fetchone()[0],
      "edges":con.execute("SELECT COUNT(*) FROM chess_passage_links").fetchone()[0]}
    if own:con.close()
    return result

def index_graph(con=None):
    """Idempotent work-to-concept classification; do not import new copyrighted text."""
    own=con is None;con=con or db();ensure(con)
    rows=con.execute("""SELECT c.id,c.body FROM chunks c JOIN books b ON b.id=c.book_id
       WHERE b.status='indexed'""").fetchall()
    links=[]
    for r in rows:
        for concept in concept_hits(r["body"]):
            links.append((r["id"],concept))
    con.execute("DELETE FROM chess_passage_links")
    con.executemany("INSERT OR IGNORE INTO chess_passage_links VALUES (?,?)",links)
    con.commit()
    result=graph_status(con)
    if own:con.close()
    return result

def position_concepts(fen,best_san,chosen_san=None):
    board=chess.Board(fen)
    best=board.parse_san(best_san)
    played=board.parse_san(chosen_san) if chosen_san else None
    record={"fen":fen,"best":best_san,"move":chosen_san or best_san}
    topic=classify(record)["topic"]
    concepts=[];evidence=[]
    def add(concept,why):
        if concept in CONCEPTS and concept not in concepts:
            concepts.append(concept);evidence.append({"concept":concept,"why":why})
    if board.is_checkmate():add("checkmate","A checkmate is present.")
    if board.gives_check(best):add("check","The recommended move gives check.")
    if board.is_capture(best):
        victim=board.piece_at(best.to_square)
        if victim:add("material exchange","The recommended move captures a "+chess.piece_name(victim.piece_type)+".")
    if board.is_castling(best):add("castling","The recommended move castles.")
    if best.promotion:add("passed pawn","The recommended move promotes a pawn.")
    after=board.copy();after.push(best)
    if after.is_checkmate():add("checkmate","The recommended move gives checkmate.")
    _,targets,_,features=attack_map(board,best)
    for feature in features:
        if feature["type"] in ("fork","pin","skewer","discovered"):
            name={"discovered":"discovered attack"}.get(feature["type"],feature["type"])
            add(name,feature.get("label","Verified geometric tactic."))
        if feature["type"]=="loose":add("hanging piece",feature["label"])
    if played and played!=best:
        choice=board.copy();choice.push(played)
        mover=choice.piece_at(played.to_square)
        if (mover and mover.piece_type!=chess.KING and
            choice.is_attacked_by(not board.turn,played.to_square) and
            not choice.is_attacked_by(board.turn,played.to_square)):
            add("hanging piece","Your move leaves its destination attacked and undefended.")
    unit=board.piece_at(best.from_square)
    if unit:
        if unit.piece_type in PIECE_CONCEPTS:
            concept=PIECE_CONCEPTS[unit.piece_type]
            # Piece-specific knowledge is used only in combination with strategic evidence.
            if board.fullmove_number<=12 and unit.piece_type in (chess.KNIGHT,chess.BISHOP):
                back=0 if board.turn else 7
                if chess.square_rank(best.from_square)==back:
                    add("development","The recommended move develops a minor piece.")
                    add(concept,"The recommended move develops a "+chess.piece_name(unit.piece_type)+".")
        elif unit.piece_type==chess.PAWN:
            if chess.square_file(best.to_square) in (3,4) and chess.square_rank(best.to_square) in (3,4):
                add("central control","The best move advances a pawn to the central squares.")
    # No demonstrated concept => no book quote. Never invent a thematic link.
    return {"topic":topic,"concepts":concepts[:4],"evidence":evidence[:4],
      "best":best_san,"chosen":chosen_san}

def _source_quality(text):
    lower=(text or "").lower()
    if any(term in lower for term in BOOKSTOP):return False
    # Old OCR commonly mangles whole words. Conservative refusal avoids
    # presenting corrupt passages as instructional evidence.
    if re.search(r"\b(?:receivuig|generaiif|seoondlyt|lialf|develope|pky|deirign|behig|pflot|liie|certun|att<ack|iftay|retractions|natuie|juitly|ftupport|advcrsary|j3)\b",lower):return False
    if any(mark in text for mark in ("^","*^","«","»","¦","■","€","•","\u00ad","\ufffd","{","}","<",">")):return False
    if re.search(r"[A-Za-z][(\\|/][A-Za-z]|[A-Za-z]\?[A-Za-z]|[A-Za-z]\.[A-Za-z]",text):return False
    if re.search(r"\b(?:this|that|the) (?:variation|game|position|diagram|text move)\b",lower):return False
    if re.search(r"\b(?:white|black) (?:now|plays|played|replies|continued|wants)\b",lower):return False
    if re.search(r"\b(?:in this case|that game|the present move|the following game|this player|the adversary|move (?:number|no\.?))\b",lower):return False
    if re.search(r"\b[A-Za-z]{2,}-\s+[a-z]{2,}\b",text):return False
    if re.search(r"\b(?:conway|philidor|steinitz|staunton|lasker|adversary|surrender)\b",lower):return False
    if re.match(r"^(?:when this|in this|the present|these|that|it|he|his|but i|the text)\b",lower):return False
    if re.search(r"[A-Za-z]\(\?|\?\)[A-Za-z]|[A-Za-z][(][?][A-Za-z]",text):return False
    if re.search(r"\b(?:he|she|hers|him|bru(h|hl)|staunton|lasker)\b",lower):return False
    if re.search(r"\b(?:the sixties|the last century|chess club|our school|publication|edition|publisher|years ago)\b",lower):return False
    if re.search(r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth) (?:move|square)\b",lower):return False
    if re.search(r"\b(?:kt|k[.]|q[.]|r[.]|b[.]|p[.])\s*(?:[x-]|\d)",lower):return False
    if "\ufffd" in text or len(text)<42:return False
    # Historical notation and corrupted scans are typically not teachable prose.
    words=re.findall(r"\b[A-Za-z]{2,}\b",text)
    if len(words)<8:return False
    if sum(len(w)<=2 for w in words)/len(words)>.48:return False
    odd=sum(bool(re.search(r"(?:[a-z][A-Z]|[A-Z]{4,}[a-z])",w)) for w in words)
    if odd/len(words)>.07:return False
    if len(re.findall(r"\d",text))>4:return False
    if len(re.findall(r"\b(?:P|Q|K|R|B|Kt)\s*-\s*[A-Z]",text))>=1:return False
    if len(re.findall(r"\b(?:P|Q|K|R|B|Kt)\s*[xX]\s*(?:P|Q|K|R|B|Kt)\b",text))>=1:return False
    if any(term in lower for term in ("the text move","white plays","black replies",
          "at this move","in this game","commenting on white","the defence made",
          "you might, however","the players","he can","he would",
          "the preceding","the following","this move", "if he", "when he")):return False
    # General explanation rather than uncontextualized move annotation.
    didactic=("should","must","always","never","avoid","important","importance","principle",
              "necessar","in order to","advantage","help","useful","often",
              "usually","as a rule","whenever","the object","the purpose",
              "the reason","in general","generally","invariably","ought","it is better")
    if not any(x in lower for x in didactic):return False
    return True

def _sentence_segments(raw):
    """Return only interior, punctuation-terminated source sentences."""
    # Normalize Gutenberg editorial emphasis and internal page counters,
    # never reconstruct missing OCR words.
    s=re.sub(r"\{\d{1,4}\}"," ",raw or "")
    s=re.sub(r"(?<!\w)_([A-Za-z][^_]{4,200}?)_(?!\w)",r"\1",s)
    s=re.sub(r"\s+"," ",s).strip()
    # Find likely terminal boundaries and discard first/last uncertain fragments.
    ends=[m.end() for m in re.finditer(r"[A-Za-zÀ-ÿ][.!?][\"'”’]?(?=\s+[A-ZÀ-Þ“\"']|\s*$)",s)]
    if len(ends)<3:return []
    result=[]
    for i in range(1,len(ends)):
        sentence=s[ends[i-1]:ends[i]].strip()
        if len(sentence)>=40 and re.search(r"[.!?][\"'”’]?$",sentence):
            result.append(sentence)
    return result

def _focused_excerpt(raw,concepts):
    """Pick the SOURCE sentence that actually names the selected idea."""
    sentences=_sentence_segments(raw)
    ranked=[]
    for i,sentence in enumerate(sentences):
        if not _source_quality(sentence):continue
        found=concept_hits(sentence)
        # "Development" of a historical school or institution isn't piece development.
        if "development" in found and not re.search(
            r"\b(?:piece|knight|bishop|pawn|rook|queen|chessmen|men|force|opening|attack|play|centre|center)\b",
            sentence,re.I):
            found.discard("development")
        if "material exchange" in found and not re.search(
            r"\b(?:material|pawn|piece|bishop|knight|rook|queen|exchange|capture|winning|advantage)\b",
            sentence,re.I):
            found.discard("material exchange")
        matching=found.intersection(concepts)
        # A historical note about a single capture is not a general
        # explanation of why a material-winning tactic works.
        if "material exchange" in matching and not re.search(
            r"\b(?:advantage|material|exchange|worth|win|winning|lose|losing|valuable|value|defend|attack|guarded|unsafe)\b",
            sentence,re.I):
            matching.discard("material exchange")
        if matching:
            score=len(matching)*10+min(len(sentence),420)/300
            ranked.append((score,i,sentence,matching))
    if not ranked:return None
    ranked.sort(reverse=True)
    _,index,sentence,matching=ranked[0]
    result=sentence
    # Do not append unrelated following commentary or incomplete OCR.
    # A stand-alone, fully supported sentence is safer than a long fragment.
    if len(result)>560:return None
    return result,matching

def position_reading(fen,best_san,chosen_san=None,limit=2,exclude_books=None,con=None):
    """Optional source evidence. [] is preferable to unrelated quotes."""
    ctx=position_concepts(fen,best_san,chosen_san)
    if not ctx["concepts"]:return []
    own=con is None;con=con or db()
    try:
        ensure(con)
        if not con.execute("SELECT 1 FROM chess_passage_links LIMIT 1").fetchone():
            try:
                index_graph(con)
            except sqlite3.OperationalError as error:
                if "no such table" in str(error):return []
                raise
        concepts=ctx["concepts"]
        placeholders=",".join("?" for _ in concepts)
        try:
            candidates=con.execute(f"""SELECT c.id,c.body,c.page,b.title,b.author,b.url,
                 b.id AS book_id,l.concept
               FROM chess_passage_links l
               JOIN chunks c ON c.id=l.chunk_id
               JOIN books b ON b.id=c.book_id
               WHERE l.concept IN ({placeholders}) AND b.status='indexed'
               ORDER BY b.title,c.id""",concepts).fetchall()
        except sqlite3.OperationalError as error:
            if "no such table" in str(error):return []
            raise
        grouped=defaultdict(lambda:{"concepts":set()})
        for row in candidates:
            key=row["id"]
            grouped[key]["concepts"].add(row["concept"])
            grouped[key]["row"]=row
        if not grouped:return []
        # Semantic relevance to the specific position's demonstrable idea.
        terms=" ".join(concepts)
        query="Chess instruction: "+"; ".join(
            x["why"] for x in ctx["evidence"][:3]
        )+" Principle: "+terms
        try:
            from semantic_index import model,pack,unpack,MODEL
            qvec=list(model().query_embed(query))[0]
            values=list(float(x) for x in qvec)
            mag=math.sqrt(sum(x*x for x in values)) or 1.0
            norm_query=[x/mag for x in values]
            vecs={r["chunk_id"]:(r["dimensions"],r["payload"]) for r in con.execute(
                "SELECT chunk_id,dimensions,payload FROM semantic_vectors WHERE model=?",(MODEL,))}
        except (ImportError,RuntimeError,OSError,sqlite3.Error):
            norm_query=[];vecs={}
        seen_books=set(exclude_books or ())
        results=[]
        ranking=[]
        for key,obj in grouped.items():
            r=obj["row"]
            excerpt=_focused_excerpt(r["body"],set(concepts))
            if not excerpt:continue
            sentence,matched=excerpt
            if not _source_quality(sentence):continue
            comparable=vecs.get(key)
            cosine=0.0
            if comparable and len(norm_query)==comparable[0]:
                data=unpack(comparable[1],comparable[0])
                cosine=sum(x*y for x,y in zip(norm_query,data))
            # Never force a snippet solely based on a vague embedding.
            if norm_query and cosine<0.27:continue
            if not norm_query and len(matched)<1:continue
            specific=len(set(matched).intersection(SPECIFIC))
            if specific==0:continue
            work=work_key(dict(r))
            quote_hash="q:"+hashlib.sha256(norm(sentence).encode("utf8")).hexdigest()[:20]
            if work in seen_books or key in seen_books or quote_hash in seen_books:continue
            score=cosine+.08*len(matched)+.06*len(set(matched).intersection(concepts[:2]))
            ranking.append((score,dict(r),sentence,set(matched),work,cosine,quote_hash))
        ranking.sort(key=lambda x:x[0],reverse=True)
        for score,r,sentence,matched,work,similarity,quote_hash in ranking:
            if work in seen_books or r["id"] in seen_books or quote_hash in seen_books:continue
            seen_books.add(work)
            seen_books.add(quote_hash)
            results.append({"chunkId":r["id"],"quoteHash":quote_hash,"workKey":list(work),
                "title":r["title"],"author":r["author"],"url":r["url"],
                "page":r["page"],"body":sentence,
                "concepts":sorted(matched),"reason":next((x["why"] for x in ctx["evidence"] if x["concept"] in matched),
                    "This source explains a verified chess concept."),
                "similarity":round(similarity,3),
                "retrieval":"position -> verified concept -> source-backed sentence"})
            if len(results)>=max(0,min(limit,3)):break
        return results
    finally:
        if own:con.close()
