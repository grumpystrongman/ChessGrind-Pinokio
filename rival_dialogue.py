"""Character-first, context-aware utterances for all 22 fictional ChessGrind rivals.

This is game dialogue, not move selection. Real chess evaluations still come
only from Stockfish's existing grade() and sparring engine. Each rival has a
distinct dialogue bank, voice, cadence and rival-specific speech habits.
"""
from __future__ import annotations
import hashlib
from arena_personas import BOT_INDEX, CAST_INDEX, coaches

# Four kinds of utterances per rival, kept in named character order.
# intro | after player's accurate move | after player's mistake | general turn | opponent win
LINES = {
"milo":("I'm Milo. I still get butterflies when the clock starts.","Oh, you saw that! I'll remember the idea.","I think that left something hanging. It happens to me too.","Okay, my turn. Don't laugh if I miss something.","Wow. A whole game! Want another?"),
"pip":("Coffee's hot and my pieces are ready. Pip here.","Ooh, that's a pretty move. You earned that one.","You dropped a crumb there. Mind if I take it?","Let's make this game interesting.","I'll buy the next coffee. You choose the rematch."),
"nora":("I'm Nora. I like to think before I touch a piece.","Well calculated. I hadn't expected that.","One move deserves a second look. What changed?","I'll keep my position steady.","Thanks for the game. I'll be replaying that later."),
"theo":("I'm Theo! Ready to try something bold?","That was stronger than I expected. Nice.","Careful. Your move might give me a target.","I see a chance to push forward.","That was a ride! Can we play again?"),
"iris":("I'm Iris. Small advantages are my favorite kind.","Nicely coordinated. Your pieces work together.","That concession might be permanent. Watch the structure.","Let's improve one square at a time.","Those tiny edges added up. Good game."),
"remy":("Call me Remy. The initiative belongs to whoever dares.","Good. You found a forcing resource.","Ah, a tempo! I can't ignore an invitation like that.","I want activity, not a quiet handshake.","The initiative won today. Rematch?"),
"ada":("Ada here. I've played this board a hundred ways.","Strong choice. You saw beyond the obvious.","There was a sturdier way to handle that.","I'll make you work for every square.","You fought. That's what I respect."),
"basil":("I'm Basil. Let's see whether your attack can break my walls.","A resourceful move. You've opened a crack.","That looks loose. My defenses are still holding.","My pieces don't have to be flashy to be useful.","Fortress held. Want another attempt?"),
"sasha":("Sasha. If a piece hangs, I'm going to notice.","Sharp. You spotted a tactical detail.","Aha. Something just became vulnerable.","Checks, captures, threats. There is always a sequence.","One last tactic decided it. Again?"),
"felix":("I'm Felix. Good positions are built quietly.","Lovely restraint. That's a patient decision.","You gave up a square you may want later.","I think my worst piece can improve.","A little pressure can be enough."),
"kira":("Kira here. I play for the initiative.","I love that energy! You met the threat.","Careful: I can turn that tempo into an attack.","Let's raise the pressure.","What a fight. Ready for round two?"),
"omar":("Omar. I've survived worse positions than this.","Excellent practical choice. You kept your nerve.","That seems hasty. Take a look at the threats.","I'll stay patient and make you prove it.","Experience helped me today. Let's do it again."),
"lena":("Lena here. Every opening has a story.","Nice development. Your plan is taking shape.","That move may make the middlegame awkward.","Let's see which structure we'll get.","Our opening choices told quite a story."),
"dante":("Dante. I'm not giving away a single tactic.","Precise. I couldn't refute that.","You missed a resource. I won't miss the reply.","Calculate carefully. So will I.","Hard-earned. That's how I like my wins."),
"vera":("Vera. Count the tempi.","Accurate.","That costs time.","King activity matters.","The ending decided it."),
"rook":("Rook's the name. Keep your pieces close!","Ha! That's how you keep your material safe.","That piece looks lonely over there.","Let's see who left the back door open.","Ha! You gave me a fight."),
"elise":("I'm Elise. Every candidate needs a reason.","Excellent calculation. You checked the reply.","That line doesn't quite work.","I prefer the move that survives scrutiny.","The details mattered. Thanks for the game."),
"kenji":("Kenji. I prefer to counter rather than chase.","A thoughtful move. You didn't overextend.","That's ambitious. Can you defend what you advanced?","I'll wait for the right moment to respond.","Patience made the difference."),
"maeve":("I'm Maeve. An advantage only counts if you convert it.","Solid technique. That's how a lead grows.","You gave me counterplay you didn't need to.","Let's simplify what can be simplified.","A clean finish. Would you like a rematch?"),
"atlas":("Atlas. We'll test how deeply you calculate.","You met a serious challenge with precision.","That choice loosens your position.","I'll search for the most resilient continuation.","The board was unforgiving. Keep studying."),
"oracle":("Oracle. Speak to the position, not your hopes.","Your move answers the position's question.","The position disagrees with that idea.","There is a quiet resource here.","Every game leaves a lesson behind."),
"max":("MAX online. Full strength. No mercy, no shortcuts.","That was an excellent move. I had to calculate.","That is a serious error. I'll show you its cost.","I have found my continuation. Your response?","Game over. The engine won. Study the turning point and challenge me again."),
}
# Rotating character-specific remarks. Normal turns avoid exact repeated scripts.
# The engine grade is an input, not a fact inferred by the persona.
MORE={
"milo":("I'm trying to keep my pieces connected.","That was careful. I can learn from that.","Hmm, I might be able to use that square."),
"pip":("The coffee might be cold before this ends.","Now that's a move worth a refill.","A little sugar for my attack, perhaps?"),
"nora":("I'm checking my king before anything else.","Steady, steady. That was responsible play.","That seemed a bit rushed, didn't it?"),
"theo":("I wonder if I can make this tactical.","You're making me think hard!","That opening might be an invitation."),
"iris":("Notice the pawn chain pointing into your half.","That's exactly the kind of long-term idea I admire.","A weakened pawn can't always be repaired."),
"remy":("An initiative is worth fighting for.","You refused my invitation. Clever.","A tempo is all I need to start something."),
"ada":("I want a plan I can explain afterward.","Good. You spotted the practical answer.","The board is asking for a safer choice."),
"basil":("Quiet moves can hold a powerful position.","A patient move. I respect it.","That loose square may become an entrance."),
"sasha":("Every capture has a recapture. Count them.","Nice! You didn't fall for the obvious trick.","There's a tactical hook in there somewhere."),
"felix":("Let's improve the piece doing the least work.","That move gave you useful coordination.","A small structural concession is still a concession."),
"kira":("Forcing moves first. Then we can breathe.","You met the pressure beautifully.","The initiative is shifting toward me."),
"omar":("The next move matters more than the last one.","Your defense has real discipline.","That's a weakness I may be able to test."),
"lena":("What middlegame will this opening become?","Your setup makes sense to me.","That pawn move changed the opening's character."),
"dante":("Take a second look at forcing continuations.","You calculated deeply enough that time.","The tactical detail deserves another look."),
"vera":("No wasted tempos.","Good technique.","Unnecessary."),
"rook":("Every hanging piece has my name on it.","Nice! Nobody's dropping material today.","I can almost hear that rook asking for protection."),
"elise":("I'm comparing two moves, then a third.","You found the concrete line.","Your calculation stopped just one move early."),
"kenji":("I'll wait and see where you commit.","You didn't overextend. That's disciplined.","That commitment gives me a target."),
"maeve":("Every pawn counts when you're converting.","That kept your advantage under control.","Counterplay is the one thing you shouldn't donate."),
"atlas":("I can search all night. You get a moment.","That met a deep positional challenge.","My search sees a weakness to pressure."),
"oracle":("Look for the quiet move nobody expects.","You answered the real question.","The position demanded more care."),
"max":("Search complete. I see several plans.","You found the strongest line. Respect.","Evaluation swing detected. I will capitalize."),
}
VOICE=["af_sarah","am_echo","bf_emma","am_michael","bf_isabella","am_adam",
       "af_nicole","bm_george","af_bella","bm_lewis","af_sky","am_michael",
       "bf_emma","am_adam","bf_isabella","bm_george","af_heart","bm_lewis",
       "af_nicole","am_echo","bf_isabella","am_michael"]
RATES=[1.04,1.13,.93,1.15,.9,1.11,.97,.85,1.08,.88,1.16,.91,1.00,1.04,.81,
       1.17,.9,.92,.94,.87,.80,.89]
assert set(LINES)==set(BOT_INDEX)
assert len(VOICE)==len(RATES)==len(BOT_INDEX)==22
BOT_VOICES={key:{"voice":VOICE[i],"rate":RATES[i]} for i,key in enumerate(BOT_INDEX)}
COACH_LINES={
 "coach-mentor":("Welcome back. Show me how you see the whole board.","Nice awareness. You saw the danger.","That move created a threat for your opponent. Did you spot it?","Look at what changed for your opponent.","Your decisions are getting easier to read."),
 "coach-tactics":("Let's calculate. Two candidate moves, every turn.","Correct. You calculated the reply.","You missed a forcing sequence. Find the second candidate.","What is the strongest reply?","Good. Replay the tactical moment."),
 "coach-iris":("Let's discuss the position, not just the pieces.","The structure is healthier after that.","That pawn decision changes the long-term picture.","Which pawn break is actually possible?","The structure tells the story."),
 "coach-rook":("Grab a chair. Don't hang anything and we'll get along.","No loose pieces. I approve!","Whoa, that piece was practically waving goodbye.","What can your opponent take for free?","You survived the board. That's something."),
 "coach-vera":("Quiet board. Clear calculation.","Precise.","Tempo lost.","Count the king moves.","Learn the ending.")
}
def identity(difficulty):
    if difficulty.startswith("bot:"):
        key=difficulty[4:]
        if key in BOT_INDEX:
            return {"kind":"bot","id":key,"name":BOT_INDEX[key]["name"],"avatar":BOT_INDEX[key]["avatar"],**BOT_VOICES[key]}
    if difficulty.startswith("coach:"):
        key=difficulty[6:]
        coach=next((c for c in coaches() if c["id"]==key),None)
        if coach:
            return {"kind":"coach","id":key,"name":coach["name"],"avatar":"/icons/portraits/"+key+".png" if key in CAST_INDEX else "/icons/coaches/sage.svg",
                    "voice":coach.get("voice","af_sarah"),"rate":coach.get("rate",1.0)}
    if difficulty.startswith("master:"):
        from masters_library import PLAYERS
        key=difficulty[7:]
        if key in PLAYERS:
            return {"kind":"master","id":key,"name":PLAYERS[key][0],"avatar":"/icons/masters/"+key+".svg",
                    "voice":"bm_george","rate":.95}
    return {"kind":"stockfish","id":"stockfish","name":"Stockfish","avatar":"/icons/bots/atlas.svg","voice":"af_sarah","rate":1.0}

def dialogue(difficulty,phase,ply,grade=None,finished=False,played=None,replied=None):
    person=identity(difficulty)
    if person["kind"]=="bot":
        choices=LINES[person["id"]]
    elif person["kind"]=="coach":
        choices=COACH_LINES.get(person["id"],COACH_LINES["coach-mentor"])
    elif person["kind"]=="master":
        choices=(f"Welcome. Let's study a game inspired by {person['name']}.",
                 "That choice deserves careful attention.","That creates a practical problem.",
                 "Let's examine the plans in this position.","Compare the game with the historical scores.")
    else:
        choices=("Let's play.","A good move.","That's an error.","Your move.","Game over.")
    if finished:mode=4
    elif phase=="intro":mode=0
    elif grade in ("blunder","mistake"):mode=2
    elif grade in ("best","strong"):mode=1
    else:mode=3
    utterance=choices[mode]
    # Character-specific alternatives plus the actual played move reduce
    # repetition, with no fabricated evaluation or move motives.
    if person["kind"]=="bot" and mode in (1,2,3):
        alternatives=MORE[person["id"]]
        idx={1:1,2:2,3:0}[mode]
        sequence=(ply//2)%4
        if sequence==1:
            utterance=alternatives[idx]
        elif sequence==2:
            utterance=choices[mode]+" "+alternatives[0]
        elif sequence==3:
            utterance=alternatives[idx]+" "+alternatives[(idx+1)%3]
        if played and mode in (1,2):
            utterance=("You played "+str(played)+". ")+utterance
        if replied and str(replied).endswith("+"):
            utterance+=" Check. Your king needs attention."
    return {**person,"text":utterance,"event":phase,"grade":grade,
            "speaking":"optional","source":"Rival character dialogue, not a chess-engine finding unless the grade is supplied"}

def reply(game_id, message):
    """Board-aware, safe, deterministic conversation with the selected rival.

    This is a lightweight character conversation, not a freeform chess LLM.
    It declines to invent engine reasoning or leak the best move before play.
    """
    if not isinstance(message,str) or not 1<=len(message.strip())<=300:
        raise ValueError("Write a short message (1-300 characters)")
    from sparring import status
    import chess
    g=status(game_id)  # validates a saved local game / its owner
    person=identity(g["difficulty"])
    board=chess.Board(g["fen"])
    text=message.strip().lower()
    name=person["name"]
    key=person["id"]
    base=LINES[key] if person["kind"]=="bot" else (
         COACH_LINES.get(key,COACH_LINES["coach-mentor"]) if person["kind"]=="coach" else
         (f"Let's study together.", "Nice.","That's worth reviewing.","Keep playing.","Good game."))
    signature=MORE.get(key,("I'm watching the whole board.","You have a plan.","Don't overlook the next reply."))
    material=sum((1 if p.color==chess.WHITE else -1)*{1:1,2:3,3:3,4:5,5:9,6:0}[p.piece_type] for p in board.piece_map().values())
    yours=material if g["color"]=="White" else -material
    if any(word in text for word in ("hello","hi ","hey","who are you","tell me about you","your name")):
        msg=base[0]+" "+(BOT_INDEX[key]["bio"] if person["kind"]=="bot" else
                      next((x["biography"] for x in coaches() if x["id"]==key),"I love a good chess game.") if person["kind"]=="coach" else
                      "This match is inspired by archived game scores; Stockfish still chooses the moves.")
    elif any(word in text for word in ("blunder","mistake","best move","good move","how did i do","what did i miss")):
        try:
            moves=g["moves"]
            last=next((i for i in range(len(moves)-1,-1,-1) if moves[i]["by"]==g["color"]),None)
            if last is None:msg="You haven't played yet. Let's make the first decision."
            else:
                before=chess.Board(g["startFen"])
                for m in moves[:last]:before.push_uci(m["uci"])
                from live_coach import grade
                score=grade(before,chess.Move.from_uci(moves[last]["uci"]),game_id+"-question",last+1)
                if score:
                    label={"best":"a top engine choice","strong":"a sound move","inaccuracy":"a small inaccuracy",
                           "mistake":"a mistake","blunder":"a blunder"}.get(score["category"],"a legal move")
                    msg=("Your last move, "+score["yourSan"]+", was "+label+" at this shallow analysis depth. "+
                         ("The engine preferred "+score["bestSan"]+". " if score["category"] not in ("best","strong") else "")+
                         signature[last%3])
                else:msg="I can't verify the move right now. I won't guess; the post-game analysis can assess it."
        except Exception:msg="I can't confidently grade that move right now; check the post-game Stockfish review."
    elif any(word in text for word in ("material","ahead","winning","losing","advantage","who is better")):
        msg=(("You're "+str(abs(yours))+" pawn-equivalents ahead in material. " if yours>0 else
             "We're even on material. " if yours==0 else
             "You're "+str(abs(yours))+" pawn-equivalents behind in material. ")+
             "Material alone isn't a full evaluation. "+signature[len(g["moves"])%3])
    elif any(word in text for word in ("hint","help","what should","what do i","your plan","next move")):
        msg=(("You're in check. Look for legal escapes first. " if board.is_check() else
             "Before the next move, scan forcing checks, captures, and threats. ")+
             signature[len(g["moves"])%3]+
             " I won't reveal a hidden best move while we're competing.")
    elif any(word in text for word in ("how are","fun","nice","good luck","good game","thanks","haha","lol","beat")):
        msg=(base[4] if g["state"]=="finished" else signature[len(g["moves"])%3])+" "+base[0].split(".")[0]+"."
    elif any(word in text for word in ("why did you","why that move","why play","why move")):
        msg="Stockfish chose that legal move. I won't invent its calculation. We can compare candidate lines after the game. "+signature[len(g["moves"])%3]
    else:
        seed=int(hashlib.sha256((game_id+key+text).encode()).hexdigest()[:8],16)
        msg=signature[seed%3]+" "+("Tell me what you see on the board." if person["kind"]=="coach" else
           "Your move will tell me what you believe.")
    return {**person,"text":msg,"event":"reply","gameId":game_id,
            "note":"Replies use current board facts and scripted personas; not an open-ended AI conversation."}
