/* Coach Arena: offline opponent roster and user-selected voice staff.
 * Browser TTS works without installs; optional local Kokoro uses EmberWriter assets.
 * No engine answer is spoken before it is graded/reviewed.
 */
(()=>{
const $=id=>document.getElementById(id);
const safe=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let bots=[],coaches=[],selectedCoach=null,voiceStatus={available:false};
let lastAudio=null;
window.ChessGrindSelectedBot=null;
window.ChessGrindSelectedCoachOpponent=null;
window.ChessGrindSelectedMaster=null;
async function request(path,data){
 const result=await fetch(path,data===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
 if(!result.ok){let obj;try{obj=await result.json()}catch(e){}throw Error(obj?.error||"Request failed");}
 return path==="/api/arena/voice/speak"?result.blob():result.json();
}
function detail(bot){
 $("bot-selected").innerHTML='<img src="'+bot.avatar+'" alt="" width="68" height="68"/><div><strong>'+safe(bot.name)+'</strong><span>'+safe(bot.role)+' · '+safe(bot.title)+'</span><p>'+safe(bot.bio)+'</p></div>';
}
function showBots(){
 $("bot-gallery").innerHTML=bots.map(b=>'<button type="button" class="rival-card'+(window.ChessGrindSelectedBot===b.id?" chosen":"")+'" data-rival="'+safe(b.id)+'" aria-pressed="'+(window.ChessGrindSelectedBot===b.id)+'"><img loading="lazy" src="'+b.avatar+'" alt="Illustration of '+safe(b.name)+'"/><span><strong>'+safe(b.name)+'</strong><small>'+safe(b.title)+'</small></span></button>').join("");
 $("bot-gallery").querySelectorAll("[data-rival]").forEach(button=>button.onclick=()=>{
   const bot=bots.find(x=>x.id===button.dataset.rival);
   window.ChessGrindSelectedCoachOpponent=null;
   window.ChessGrindSelectedMaster=null;
   window.ChessGrindSelectedBot=bot.id;
   $("game-style").value=bot.style;
   detail(bot);showBots();
 });
 if(window.ChessGrindSelectedBot)detail(bots.find(x=>x.id===window.ChessGrindSelectedBot));
 else $("bot-selected").innerHTML='<p>Using the manual Stockfish difficulty above.</p>';
}
function showPlayableCoaches(){
 const choice=window.ChessGrindSelectedCoachOpponent;
 $("coach-opponents").innerHTML=coaches.map((c,i)=>
  '<button type="button" class="coach-card'+(choice===c.id?" chosen":"")+
  '" data-play-coach="'+safe(c.id)+'" aria-pressed="'+(choice===c.id)+'">'+
  '<img src="/icons/coaches/'+["sage","plum","copper","arctic","gold"][i%5]+'.svg" alt=""/>'+
  '<span><strong>'+safe(c.name)+'</strong><small>'+safe(c.specialty)+' · Skill '+c.skill+'/20</small></span></button>'
 ).join("")||'<p class="muted small">No coaches saved. Create one below.</p>';
 $("coach-opponents").querySelectorAll("[data-play-coach]").forEach(el=>el.onclick=()=>{
  const c=coaches.find(c=>c.id===el.dataset.playCoach);
  window.ChessGrindSelectedCoachOpponent=c.id;
  window.ChessGrindSelectedMaster=null;
  window.ChessGrindSelectedBot=null;
  selectCoach(c.id);
  showBots();showPlayableCoaches();
  $("coach-match-selection").textContent="Ready to play against "+c.name+" at Stockfish skill "+c.skill+"/20. Select Start a new game.";
 });
 if(choice&&!coaches.some(c=>c.id===choice))window.ChessGrindSelectedCoachOpponent=null;
 if(!window.ChessGrindSelectedCoachOpponent)
  $("coach-match-selection").textContent="Select one of your coaches to play, or choose a rival from the roster.";
}
function showCoaches(){
 $("coach-count").textContent=coaches.length+" / 5 coaches";
 $("coach-gallery").innerHTML=coaches.map((c,i)=>'<button type="button" class="coach-card'+(selectedCoach===c.id?" chosen":"")+'" data-coach="'+safe(c.id)+'"><img src="/icons/coaches/'+["sage","plum","copper","arctic","gold"][i%5]+'.svg" alt="" width="58" height="58"/><span><strong>'+safe(c.name)+'</strong><small>'+safe(c.specialty)+'</small></span></button>').join("");
 $("coach-gallery").querySelectorAll("[data-coach]").forEach(b=>b.onclick=selectCoach.bind(null,b.dataset.coach));
 $("new-coach").disabled=coaches.length>=5;
 showPlayableCoaches();
 if(!selectedCoach||!coaches.some(c=>c.id===selectedCoach)){
   selectedCoach=coaches[0]?.id||null;
 }
 if(selectedCoach)fill(coaches.find(c=>c.id===selectedCoach));
 const actor=coaches.find(c=>c.id===selectedCoach);
 if(actor){
   $("active-coach-name").textContent=actor.name;
   $("active-coach-specialty").textContent=actor.specialty;
 }
}
function fill(coach){
 if(!coach)return;
 $("coach-editor").dataset.id=coach.id;
 $("coach-name").value=coach.name;
 $("coach-specialty").value=coach.specialty;
 $("coach-bio").value=coach.biography||"";
 $("coach-tone").value=coach.tone||"supportive";
 $("coach-voice").value=coach.voice||"af_sarah";
 $("coach-rate").value=coach.rate||1;
 $("coach-skill").value=String(coach.skill??8);
 $("coach-style").value=coach.style||"balanced";
 $("coach-quirk").value=coach.quirk||"threats";
 $("coach-rate-value").textContent=Number(coach.rate||1).toFixed(2)+"x";
 $("delete-coach").disabled=false;
}
function selectCoach(id){
 selectedCoach=id;
 request("/api/arena/coach/activate",{id}).catch(e=>{$("coach-status").textContent=e.message});
 $("coach-editor").dataset.id=id;
 showCoaches();
}
function clearCoachEditor(){
 $("coach-editor").dataset.id="";
 $("coach-name").value="";
 $("coach-specialty").value="";
 $("coach-bio").value="";
 $("coach-tone").value="supportive";
 $("coach-voice").value="af_sarah";
 $("coach-rate").value="1";
 $("coach-skill").value="8";
 $("coach-style").value="balanced";
 $("coach-quirk").value="threats";
 $("coach-rate-value").textContent="1.00x";
 $("delete-coach").disabled=true;
}
$("new-coach").onclick=()=>{
 if(coaches.length>=5)return;
 selectedCoach=null;clearCoachEditor();showCoaches();
 // showCoaches selects current; blank fields are an explicit new coach draft
 selectedCoach=null;clearCoachEditor();
 $("coach-name").focus();
 $("coach-status").textContent="New custom coach. Fill in a name and specialty, then Save.";
};
$("coach-rate").oninput=()=>$("coach-rate-value").textContent=Number($("coach-rate").value).toFixed(2)+"x";
$("save-coach").onclick=async()=>{
 try{
   const data={
     name:$("coach-name").value,specialty:$("coach-specialty").value,biography:$("coach-bio").value,
     tone:$("coach-tone").value,voice:$("coach-voice").value,rate:Number($("coach-rate").value),skill:Number($("coach-skill").value),style:$("coach-style").value,quirk:$("coach-quirk").value
   };
   const id=$("coach-editor").dataset.id;
   if(id)data.id=id;
   const result=await request("/api/arena/coach/save",data);
   coaches=result.coaches;
   selectedCoach=id||coaches[coaches.length-1].id;
   await request("/api/arena/coach/activate",{id:selectedCoach});
   showCoaches();
   $("coach-status").textContent="Coach saved locally. Your other coaches and training history are unchanged.";
 }catch(e){$("coach-status").textContent=e.message;}
};
$("delete-coach").onclick=async()=>{
 const id=$("coach-editor").dataset.id;
 if(!id||!confirm("Delete this coach profile? Saved games and scores remain untouched."))return;
 try{const result=await request("/api/arena/coach/delete",{id});
  coaches=result.coaches;selectedCoach=null;window.ChessGrindSelectedCoachOpponent=null;showCoaches();
  if(!coaches.length)clearCoachEditor();
  $("coach-status").textContent="Coach removed.";
 }catch(e){$("coach-status").textContent=e.message;}
};
function stopTalking(){
 if(window.speechSynthesis)window.speechSynthesis.cancel();
 if(lastAudio){lastAudio.pause();URL.revokeObjectURL(lastAudio.src);lastAudio=null;}
}
async function say(text){
 const coach=coaches.find(c=>c.id===selectedCoach);
 if(!coach){$("coach-status").textContent="Select or create a coach first.";return;}
 text=String(text||"").trim().slice(0,450);
 if(!text)return;
 stopTalking();
 if(voiceStatus.available){
   try{
    const blob=await request("/api/arena/voice/speak",{text,voice:coach.voice,rate:coach.rate});
    lastAudio=new Audio(URL.createObjectURL(blob));
    lastAudio.onended=()=>{if(lastAudio){URL.revokeObjectURL(lastAudio.src);lastAudio=null;}};
    await lastAudio.play();$("coach-status").textContent="Using private neural Kokoro voice.";return;
   }catch(e){$("coach-status").textContent="Neural voice issue; switching to system speech: "+e.message;}
 }
 if("speechSynthesis" in window){
   const utterance=new SpeechSynthesisUtterance(text);
   utterance.lang=coach.voice.startsWith("b")?"en-GB":"en-US";
   utterance.rate=Math.max(.7,Math.min(1.4,coach.rate));
   const options=speechSynthesis.getVoices().filter(v=>v.lang.toLowerCase().startsWith(utterance.lang.slice(0,2).toLowerCase()));
   if(options.length)utterance.voice=options[coaches.indexOf(coach)%options.length];
   speechSynthesis.speak(utterance);
   $("coach-status").textContent="Using your system's offline-capable browser voice. Optional Kokoro voices can be installed separately.";
 }else $("coach-status").textContent="Voice playback isn't supported by this browser.";
}
$("coach-preview").onclick=()=>say("I'm your chess coach. Before you move, consider your opponent's threats, look for forcing moves, and explain the plan you choose.");
$("coach-speak").onclick=()=>say($("coach-live").textContent);
$("coach-stop").onclick=stopTalking;
window.ChessGrindCoachFormat=message=>message; // No repetitive introductions.

window.ChessGrindCoachAuto=(message)=>{
 if($("coach-autospeak").checked)say(message);
};
$("game-difficulty").addEventListener("change",()=>{
 window.ChessGrindSelectedBot=null;
window.ChessGrindSelectedCoachOpponent=null;showBots();
});
let masterList=[];
function masterEvidence(m){
 const e=m.recordedStyle||{};
 const games=e.recordedGames||m.recordedGames;
 const opening=e.commonOpenings?.[0]?.[0];
 return "Historical sample: "+games+" games. "+
   (opening?"A frequently recorded opening: "+opening+". ":"")+
   (e.sampleMoves?"Captures in sampled moves: "+e.captureRate+"%. ":"")+
   "Archive statistics are descriptive, not proof of intent.";
}

function showMasters(search=""){
 const text=search.toLocaleLowerCase();
 const matches=masterList.filter(m=>(m.name+" "+m.era+" "+m.knownFor).toLocaleLowerCase().includes(text));
 $("masters-gallery").innerHTML=matches.map(m=>
   '<button type="button" class="coach-card'+(window.ChessGrindSelectedMaster===m.id?" chosen":"")+
   '" data-master="'+safe(m.id)+'"><img src="'+safe(m.avatar)+'" alt="Illustrated chess insignia">'+
   '<span><strong>'+safe(m.name)+'</strong><small>'+safe(m.era)+' · '+m.recordedGames+' games</small></span></button>').join("")||
   '<div class="muted small">No master matched your search.</div>';
 $("masters-gallery").querySelectorAll("[data-master]").forEach(node=>node.onclick=()=>{
   const m=masterList.find(x=>x.id===node.dataset.master);
   window.ChessGrindSelectedMaster=m.id;
   window.ChessGrindSelectedBot=null;window.ChessGrindSelectedCoachOpponent=null;
   showBots();showPlayableCoaches();showMasters($("masters-search").value);
   $("master-selected").innerHTML='<img src="'+safe(m.avatar)+'" alt="Illustrated insignia"><div><strong>'+safe(m.name)+
    '</strong><span>'+safe(m.era)+' · Master-inspired Stockfish skill '+m.skill+'/20</span><p>'+
    safe(m.knownFor)+'. '+safe(masterEvidence(m))+'</p></div>';
 });
}
$("masters-search").oninput=()=>showMasters($("masters-search").value);
async function initialize(){
 try{
  const masterResponse=await request("/api/arena/masters");
  masterList=masterResponse.masters;
  showMasters();
  const roster=await request("/api/arena/roster");
  bots=roster.bots;coaches=roster.coaches;selectedCoach=roster.activeCoach;
  $("coach-voice").innerHTML=roster.voices.map(v=>'<option value="'+safe(v)+'">'+safe(v)+'</option>').join("");
  window.ChessGrindSelectedBot=null;
  const masterRequested=new URLSearchParams(location.search).get("master");
  if(masterList.some(m=>m.id===masterRequested)){
    const m=masterList.find(x=>x.id===masterRequested);
    window.ChessGrindSelectedMaster=m.id;
    showMasters();
    $("master-selected").innerHTML='<img src="'+safe(m.avatar)+'" alt=""><div><strong>'+
    safe(m.name)+'</strong><span>'+safe(m.era)+' · Stockfish skill '+m.skill+'/20</span><p>'+
    safe(m.knownFor)+'. '+safe(masterEvidence(m))+'</p></div>';
  }
  const requested=new URLSearchParams(location.search).get("coach");
  window.ChessGrindSelectedCoachOpponent=coaches.some(c=>c.id===requested)?requested:null;
  if(window.ChessGrindSelectedCoachOpponent)selectedCoach=window.ChessGrindSelectedCoachOpponent;
  showBots();showCoaches();
  if(window.ChessGrindSelectedCoachOpponent){
   const chosen=coaches.find(c=>c.id===window.ChessGrindSelectedCoachOpponent);
   $("coach-match-selection").textContent="Ready to play "+chosen.name+" at Stockfish skill "+chosen.skill+"/20. Choose your color and Start a new game.";
  }
  voiceStatus=await request("/api/arena/voice/status");
  $("voice-backend").textContent=voiceStatus.available?"Local neural Kokoro ready":"Browser voice available · Install optional Kokoro for neural speech";
 }catch(error){
  $("bot-selected").textContent="Could not load the opponent roster: "+error.message;
  $("coach-status").textContent=error.message;
 }
}
initialize();
})();
