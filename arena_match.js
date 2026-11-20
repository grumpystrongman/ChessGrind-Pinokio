/* Full-viewport ChessGrind match: rival talk, readable bubbles, optional voice. */
(()=>{
"use strict";
const $=id=>document.getElementById(id), panel=$("game-board-panel");
if(!panel)return;
const top=panel.firstElementChild;top.classList.add("match-top");
const board=document.createElement("section");board.id="match-board-zone";
const chat=document.createElement("aside");chat.id="match-conversation";chat.setAttribute("aria-label","Conversation with your chess rival");
const original=[];for(let el=top.nextElementSibling;el;el=el.nextElementSibling)original.push(el);
for(const el of original)board.appendChild(el);
panel.appendChild(board);panel.appendChild(chat);
// The legacy post-game report lived OUTSIDE the fixed match overlay. Bring it
// into the same viewport, alongside the board, so it cannot be hidden.
const report=$("review-panel");
chat.insertAdjacentElement("afterend",report);
report.classList.add("match-review-pane");
const backToChat=document.createElement("button");
backToChat.type="button";backToChat.className="btn alt";
backToChat.id="match-review-back";backToChat.textContent="Return to conversation";
report.insertAdjacentElement("afterbegin",backToChat);
const reviewTop=document.createElement("button");
reviewTop.type="button";reviewTop.className="btn";
reviewTop.id="match-review-top";reviewTop.textContent="Review this game";
reviewTop.classList.add("hidden");

const topButtons=document.createElement("div");topButtons.className="match-top-actions";
topButtons.innerHTML='<button class="btn alt" id="match-native-fullscreen" type="button">Fullscreen</button><button class="btn alt" id="match-close" type="button">Back to arena</button>';
top.appendChild(topButtons);topButtons.insertAdjacentElement("afterbegin",reviewTop);
const resume=document.createElement("button");resume.id="match-resume";resume.className="btn alt hidden";resume.type="button";resume.textContent="Resume current match";$("start-game").insertAdjacentElement("afterend",resume);
chat.innerHTML=[
 '<div class="match-rival-head"><img id="match-face" alt="Opponent portrait"><div><span class="kicker">Across the board</span><h2 id="match-rival-name">Your rival</h2><p id="match-rival-role">Ready to play</p></div></div>',
 '<div class="match-convo-title"><strong>Conversation</strong><span id="match-convo-title-mode">Local AI dialogue</span><span id="match-voice-mode">Read only</span></div>',
 '<div id="match-chat-log" role="log" aria-live="polite" aria-relevant="additions"></div>',
 '<form id="match-chat-form" class="match-send"><input id="match-chat-input" maxlength="300" aria-label="Message your chess rival" placeholder="Ask about the game or say something..." required><button class="btn" type="submit" id="match-chat-submit">Send</button></form>',
 '<div class="match-voice-controls"><button class="btn" id="match-voice-toggle" type="button">Enable voice</button><button class="btn alt" id="match-hear" type="button">Hear last line</button><button class="btn alt" id="match-stop" type="button">Stop</button></div>',
 '<p class="small muted" id="match-audio-status">Every speech bubble is readable. Voice playback is optional.</p>',
 '<div class="match-eval"><span class="kicker">Board evaluation</span><p id="match-eval-text">Your moves will be reviewed at a limited engine depth.</p></div>'
].join("");
let gameId=null,lines=[],lastRival=null,enabled=false,currentAudio=null,speechToken=0;
try{enabled=localStorage.getItem("chessgrind.rivalSpeech")==="on";}catch(e){}
const safe=s=>String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function stop(){
 speechToken++;
 if(currentAudio){currentAudio.pause();URL.revokeObjectURL(currentAudio.src);currentAudio=null;}
 if(window.speechSynthesis)window.speechSynthesis.cancel();
}
async function talk(line){
 if(!line)return;stop();const token=speechToken;
 const message=String(line.text),voice=line.voice||"af_sarah",rate=Number(line.rate)||1;
 const chunks=[];
 let remaining=message;
 while(remaining.length>440){
  const section=remaining.slice(0,440);
  const boundary=Math.max(section.lastIndexOf(". "),section.lastIndexOf("? "),section.lastIndexOf("! "),section.lastIndexOf(" "));
  const at=boundary>180?boundary+1:440;
  chunks.push(remaining.slice(0,at).trim());
  remaining=remaining.slice(at).trim();
 }
 if(remaining)chunks.push(remaining);
 try{
  const status=await fetch("/api/arena/voice/status").then(x=>x.json());
  if(token!==speechToken)return;
  if(status.available){
   for(const part of chunks){
    if(token!==speechToken)return;
    const r=await fetch("/api/arena/voice/speak",{method:"POST",headers:{"Content-Type":"application/json"},
         body:JSON.stringify({text:part,voice,rate})});
    if(!r.ok)throw Error("Local neural voice unavailable");
    const blob=await r.blob();if(token!==speechToken)return;
    currentAudio=new Audio(URL.createObjectURL(blob));
    await new Promise((resolve,reject)=>{
      currentAudio.onended=resolve;
      currentAudio.onpause=resolve;
      currentAudio.onerror=()=>reject(Error("Could not play voice segment"));
      currentAudio.play().catch(reject);
    });
    if(currentAudio){URL.revokeObjectURL(currentAudio.src);currentAudio=null;}
   }
   $("match-audio-status").textContent="Finished speaking the full response.";
   return;
  }
 }catch(e){if(token!==speechToken)return;$("match-audio-status").textContent="Using the browser voice instead.";}
 if(!("speechSynthesis" in window)||token!==speechToken){$("match-audio-status").textContent="Speech isn't supported here. Every bubble remains readable.";return;}
 const utterance=new SpeechSynthesisUtterance(message);utterance.lang=voice.startsWith("b")?"en-GB":"en-US";utterance.rate=Math.min(1.4,Math.max(.7,rate));
 const options=speechSynthesis.getVoices().filter(v=>v.lang.toLowerCase().startsWith("en"));
 if(options.length){const seed=[...String(line.personaId||"")].reduce((a,c)=>a+c.charCodeAt(0),0);utterance.voice=options[seed%options.length];}
 speechSynthesis.speak(utterance);$("match-audio-status").textContent="Browser voice speaking.";
}
function store(){
 try{localStorage.setItem("chessgrind.rivalChat."+gameId,JSON.stringify(lines.slice(-40)));}catch(e){}
}
function load(id){
 try{return JSON.parse(localStorage.getItem("chessgrind.rivalChat."+id)||"[]").filter(x=>x&&typeof x.key==="string"&&typeof x.text==="string").slice(-40);}catch(e){return[];}
}
function draw(){
 const log=$("match-chat-log");log.textContent="";
 for(const line of lines){
  const item=document.createElement("article");item.className="match-bubble "+(line.type==="analysis"?"analysis":line.type==="user"?"user":"rival");
  const who=document.createElement("strong");who.textContent=line.name;
  const msg=document.createElement("p");msg.textContent=line.text;
  item.append(who,msg);
  if(line.type==="rival"){
   const listen=document.createElement("button");listen.type="button";listen.className="match-inline-hear";listen.textContent="Hear this";
   listen.onclick=()=>talk(line);item.appendChild(listen);
  }
  log.appendChild(item);
 }
 log.scrollTop=log.scrollHeight;
}
function add(line){
 if(lines.some(x=>x.key===line.key))return false;
 lines.push(line);lines=lines.slice(-40);if(line.type==="rival")lastRival=line;
 store();draw();return true;
}
function viewReport(){
 chat.classList.add("hidden");
 report.classList.remove("hidden");
 report.classList.add("match-review-visible");
 report.scrollTop=0;
}
function viewConversation(){
 report.classList.remove("match-review-visible");
 report.classList.add("hidden");
 chat.classList.remove("hidden");
}
backToChat.onclick=viewConversation;
reviewTop.onclick=()=>{
 viewReport();
 if(!$("review-panel").dataset.reviewGame||$("review-panel").dataset.reviewGame!==gameId){
  $("review-title").textContent="Analyzing your game...";
  $("review-summary").textContent="Stockfish is checking every decision. The analysis remains in this match window.";
  $("review-game").click();
 }
};

function contextualHistory(){
 return lines.filter(x=>x.type==="rival"||x.type==="user").slice(-10)
  .map(x=>({role:x.type==="user"?"user":"assistant",content:x.text.slice(0,300)}));
}
function replaceText(key,text){
 const target=lines.find(x=>x.key===key);
 if(!target)return null;
 target.text=text;store();draw();return target;
}
const inFlight=new Set();
async function characterResponds(game,event){
 const count=game.moves?.length||0;
 const key=game.id+":rival:"+count+":"+(game.state==="finished"?"end":"turn");
 if(lines.some(x=>x.key===key)||inFlight.has(key))return;
 inFlight.add(key);
 const who=game.rivalDialogue;
 add({key,type:"rival",name:who.name,personaId:who.id,
      text:"Thinking about this position...",voice:who.voice,rate:who.rate});
 try{
  const history=contextualHistory().slice(0,-1);
  const response=await fetch("/api/sparring/dialogue",{
   method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({gameId:game.id,event,history})
  });
  const data=await response.json();
  if(!response.ok)throw Error(data.error||"Local conversation unavailable");
  if(gameId!==game.id)return;
  const line=replaceText(key,data.text);
  if(line){
   line.voice=data.voice;line.rate=data.rate;
   lastRival=line;store();
   if(enabled)talk(line);
  }
  $("match-convo-title-mode").textContent=data.mode==="local-ai"?"Local conversational AI":"Offline character response";
 }catch(error){
  if(gameId===game.id){
   replaceText(key,who.text||"I am thinking about what this position requires.");
   $("match-convo-title-mode").textContent="Offline character response";
  }
 }finally{inFlight.delete(key);}
}
function voiceButtons(){
 $("match-voice-mode").textContent=enabled?"Voice on":"Read only";
 $("match-voice-toggle").textContent=enabled?"Read only / mute":"Turn voice on";
 $("match-voice-toggle").setAttribute("aria-pressed",String(enabled));
}
function open(){panel.classList.add("match-room");panel.classList.remove("hidden");document.body.classList.add("match-running");resume.classList.remove("hidden");}
function leave(){
 viewConversation();stop();document.body.classList.remove("match-running");panel.classList.remove("match-room");panel.classList.add("hidden");
 if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});
}
$("match-close").onclick=leave;resume.onclick=open;
$("match-voice-toggle").onclick=()=>{
 enabled=!enabled;try{localStorage.setItem("chessgrind.rivalSpeech",enabled?"on":"off");}catch(e){}
 if(!enabled)stop();voiceButtons();$("match-audio-status").textContent=enabled?"New opponent bubbles will speak automatically.":"Silent reading. Use Hear whenever you want.";
};
$("match-chat-form").onsubmit=async event=>{
 event.preventDefault();
 if(!gameId)return;
 const input=$("match-chat-input"),send=$("match-chat-submit");
 const message=input.value.trim().slice(0,300);
 if(!message)return;
 input.value="";send.disabled=true;
 const prior=contextualHistory();
 const timestamp=Date.now();
 add({key:gameId+":human:"+timestamp,type:"user",name:"You",text:message});
 try{
  const response=await fetch("/api/sparring/chat",{method:"POST",
   headers:{"Content-Type":"application/json"},body:JSON.stringify({gameId,message,history:prior})});
  const data=await response.json();
  if(!response.ok)throw Error(data.error||"Couldn't reach your rival");
  const line={key:gameId+":reply:"+timestamp,type:"rival",name:data.name,personaId:data.id,
    text:data.text,voice:data.voice,rate:data.rate};
  if(add(line)&&enabled)talk(line);
 }catch(error){
  add({key:gameId+":system:"+timestamp,type:"analysis",name:"Connection",text:error.message});
 }finally{send.disabled=false;input.focus();}
};
$("match-hear").onclick=()=>talk(lastRival);
$("match-stop").onclick=stop;
$("match-native-fullscreen").onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await panel.requestFullscreen();}catch(e){$("match-audio-status").textContent="The match already fills the browser viewport.";}}; 
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&document.body.classList.contains("match-running")&&!document.fullscreenElement)leave();});
window.ChessGrindMatch={
 render(game){
  if(game.id!==gameId){gameId=game.id;lines=load(gameId);lastRival=[...lines].reverse().find(x=>x.type==="rival")||null;draw();}
  const d=game.rivalDialogue;
  if(d){
   $("match-face").src=d.avatar;$("match-rival-name").textContent=d.name;
   $("match-rival-role").textContent=game.bot?.role||game.coachOpponent?.specialty||(game.masterOpponent?"Master-inspired rival":"Stockfish");
  }
  open();voiceButtons();
  const finished=game.state!=="active";
  reviewTop.classList.toggle("hidden",!finished);
  if(!finished)viewConversation();

  if(d){
   const event=game.state!=="active"?"end":
      (!game.moves?.length||game.moves.length===1&&game.color==="Black"?"intro":"turn");
   characterResponds(game,event);
  }
  const c=game.detail?.coaching;
  if(c?.struggling&&c.message){
   add({key:game.id+":reminder:"+game.moves.length,type:"analysis",
     name:"Board-vision reminder",text:c.message});
  }
  if(c){
   const label={best:"Best move",strong:"Strong move",inaccuracy:"Inaccuracy",mistake:"Mistake",blunder:"Blunder"}[c.category];
   $("match-eval-text").textContent=label+" · "+c.yourSan+" · approximate depth "+c.depth+" assessment";
   if(["best","mistake","blunder"].includes(c.category)){
    const text=c.category==="best"?"Best move. The engine chose "+c.yourSan+" too.":
     c.category==="blunder"?"Blunder detected after "+c.yourSan+". "+c.bestSan+" was significantly stronger.":
     "Mistake after "+c.yourSan+". Compare "+c.bestSan+" when reviewing the position.";
    add({key:game.id+":analysis:"+game.moves.length,type:"analysis",name:"Move analysis",text});
   }
  }
 },
 open,leave
};
voiceButtons();
})();