"""Bibliographic deduplication and sentence-complete, source-faithful excerpts.

Never manufacture text to complete a clipped scan. A quote is shown only
when we can find whole sentences inside the actual stored passage.
"""
import re
import unicodedata
from collections import defaultdict

def norm(value):
    raw=unicodedata.normalize("NFKD",str(value or "")).lower()
    raw="".join(c for c in raw if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+",raw))

def work_key(item):
    title=norm(item.get("title"))
    author=norm(item.get("author"))
    if not title:return ("unidentified",item.get("url",""))
    # Distinct books entitled "Chess" and "Chess Openings" must not merge.
    if len(title)<14 and not author:return ("short",title,item.get("url",""))
    if not author:return ("title",title)
    # Catalogs may put names in lastname-first or firstname-first form.
    return ("title_author",title,author)

def excerpt(raw,min_chars=75,max_chars=560):
    """Return only complete, readable sentences that actually exist in the source.

    OCR scans and 1,200-character source chunks may begin or end mid-sentence.
    We intentionally discard doubtful text rather than fabricating continuity.
    """
    text=re.sub(r"\s+"," ",str(raw or "")).strip()
    if len(text)<min_chars:return ""
    low=text.lower()
    if "\ufffd" in text or "digitized by google" in low or "google books" in low:
        return ""
    # Extremely noisy passages from scanned editions should not be quoted.
    if len(re.findall(r"[A-Za-zÀ-ÿ]",text))<len(text)*0.52:
        return ""
    # An actual ending punctuation mark must follow a word (not page '32.').
    # Also reject page headings and overabundant digits.
    candidates=[]
    for match in re.finditer(r"[A-Za-zÀ-ÿ][.!?][\"'”’]?(?=\s+[A-ZÀ-Þ“\"']|\s*$)",text):
        pos=match.end()
        candidates.append(pos)
    if len(candidates)<2:return ""
    # Drop leading fragment up to the first terminator; this is safe even
    # when a source chunk happened to start at a true sentence boundary.
    text=text[candidates[0]:].strip()
    if not text:return ""
    endings=[m.end() for m in re.finditer(
        r"[A-Za-zÀ-ÿ][.!?][\"'”’]?(?=\s+[A-ZÀ-Þ“\"']|\s*$)",text)]
    chosen=""
    for stop in endings:
        if stop>max_chars:break
        candidate=text[:stop].strip()
        if len(candidate)>=min_chars:chosen=candidate
    if not chosen:return ""
    if re.search(r"\b(?:fig|plate|page|example|volume|chapter)\s*\d+\b",chosen,re.I):
        # Page markers mixed into one continuous quote are hard to read.
        return ""
    if chosen.count("\n")>2:return ""
    # Old OCR chess notation fragments (K., Q., B., etc.) are not
    # reader-friendly sentences; exclude them from quotations.
    if len(re.findall(r"\b(?:K|Q|B|R|Kt|P)\.",chosen))>=3:return ""
    if any(term in chosen.lower() for term in ("first edition was published","above works","price io5","of messrs.","our catalogue")):
        return ""
    # Reject OCR headers with scrambled all-capital words.
    first=chosen[:65]
    words=re.findall(r"[A-Za-z]{2,}",first)
    if len(words)>=5 and sum(w.isupper() for w in words)/len(words)>.70:return ""
    return chosen

def dedup_passages(hits,limit):
    out=[]
    seen=set()
    for hit in hits:
        text=excerpt(hit.get("body"))
        if not text:continue
        key=work_key(hit)
        if key in seen:continue
        seen.add(key)
        item=dict(hit)
        item["body"]=text
        item["excerpt_complete"]=True
        out.append(item)
        if len(out)>=limit:break
    return out

def consolidate_catalog(books):
    """A display grouping; never deletes original edition records."""
    groups={}
    for book in books:
        key=work_key(book)
        group=groups.get(key)
        if group is None:
            item=dict(book)
            item["editions"]=[{"title":book.get("title"),"url":book.get("url"),
                 "year":book.get("year"),"source":book.get("source"),
                 "status":book.get("status"),"pdf_url":book.get("pdf_url")}]
            groups[key]=item
        else:
            group["editions"].append({"title":book.get("title"),"url":book.get("url"),
                 "year":book.get("year"),"source":book.get("source"),
                 "status":book.get("status"),"pdf_url":book.get("pdf_url")})
            if book.get("status")=="indexed" and group.get("status")!="indexed":
                kept=group["editions"]
                group.update(book)
                group["editions"]=kept
            elif (not group.get("pdf_url")) and book.get("pdf_url"):
                group["pdf_url"]=book["pdf_url"]
            group["pdf_count"]=int(group.get("pdf_count") or 0)+int(book.get("pdf_count") or 0)
    return list(groups.values())
