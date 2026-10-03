from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, zipfile, tempfile, shutil, py_compile

ROOT=Path(__file__).resolve().parents[2]
VERSION="1.12.1"
PREV="1.9.9"
PKG_NAME="LONGFORM_FACTORY_CONTINUITY_STATUS_PIN_FIX_1_12_1.lfupdate.zip"
PREV_PKG=ROOT/"packages"/"LONGFORM_FACTORY_REMOTE_UI_FIX_1_9_9.lfupdate.zip"
OUT=ROOT/"packages"/PKG_NAME
TMP=Path(tempfile.mkdtemp(prefix="lf1121_"))

def w(rel,text):
    p=TMP/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text,encoding="utf-8")
    return p

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

BASE_ADAPTER='''from __future__ import annotations
from pathlib import Path
import json

STAGES=["DISCOVERY","GREENLIGHT","RESEARCH","FACT_LOCK","SCRIPT","SCRIPT_QC","VISUAL_PLAN","VISUAL_BUILD","VISUAL_QC","VOICE","TIMING","SUBTITLES","EDIT_PLAN","RENDER","AUTO_QC","PREVIEW_REVIEW","FINAL","THUMBNAIL","TITLE","DESCRIPTION","TAGS","PUBLISHING_QC","PUBLISHING_REVIEW","UPLOAD_READY"]

class DeclarativeCapabilityAdapter:
    ADAPTER_ID=""
    CHANNEL_ID=""
    PROFILE_ID=""
    DISPLAY_NAME=""
    REQUIRED_RULES=[]
    CAPABILITIES={}
    def __init__(self,root:Path): self.root=Path(root)
    def _media_binding(self):
        p=self.root/"factory"/"state"/"cross_channel_media_smoke.json"
        try:
            d=json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            ch=d.get("channels",{}).get(self.CHANNEL_ID,{})
            if ch.get("status")=="PASS":
                return "ACTIVE_MEDIA_SMOKE"
        except Exception:
            pass
        return "PENDING_MEDIA_SMOKE"
    def describe(self,context):
        media=self._media_binding()
        return {"adapter_contract":"1.0","adapter_id":self.ADAPTER_ID,"adapter_version":"1.1","channel_id":self.CHANNEL_ID,"profile_id":self.PROFILE_ID,"display_name":self.DISPLAY_NAME,"integration_status":"ACTIVE_MEDIA_SMOKE" if media=="ACTIVE_MEDIA_SMOKE" else "ACTIVE_CAPABILITY","media_binding":media,"supported_stages":list(STAGES),"required_rules":list(self.REQUIRED_RULES),"capabilities":self.CAPABILITIES,"requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":self.PROFILE_ID}}
    def inspect(self,ep,manifest):
        media=self._media_binding()
        return {"active":True,"adapter_id":self.ADAPTER_ID,"stage":manifest.get("lifecycle",{}).get("current_stage","DISCOVERY"),"state":"MEDIA_SMOKE_PASS" if media=="ACTIVE_MEDIA_SMOKE" else "CAPABILITY_INTEGRATED","buttons":[],"integration_status":"ACTIVE_MEDIA_SMOKE" if media=="ACTIVE_MEDIA_SMOKE" else "ACTIVE_CAPABILITY","media_binding":media,"message":"Representative media smoke passed." if media=="ACTIVE_MEDIA_SMOKE" else "Channel capability contract is integrated. Representative media smoke is still required."}
    def preflight(self,stage,context):
        m=context["manifest"]
        checks=[
          {"name":"Manifest schema","pass":str(m.get("schema_version"))=="1.2","detail":str(m.get("schema_version"))},
          {"name":"Channel","pass":m.get("channel_id")==self.CHANNEL_ID,"detail":str(m.get("channel_id"))},
          {"name":"Profile","pass":m.get("profile")==self.PROFILE_ID,"detail":str(m.get("profile"))},
        ]
        return {"pass":all(x["pass"] for x in checks),"checks":checks,"resource_class":"LIGHT"}
    def job_spec(self,job_name,context): return None
    def artifacts(self,stage,context): return []
    def retry_policy(self,stage,failure,context): return {"retryable":False,"resume_point":None,"cache_reuse":False,"max_safe_retries":0,"human_intervention":True}
    def invoke_action(self,action,context,body):
        raise RuntimeError(f"{self.CHANNEL_ID} action '{action}' is not exposed through the capability adapter. Use the registered media runner/job path.")
'''

CHANNELS={
"en_story":{
 "class":"ENStoryReferenceAdapter","aid":"EN_STORY_REFERENCE_ADAPTER_v1_0","cid":"EN_STORY","profile":"EN_DRAMA_v1","name":"English Story Longform","rules":["STORY_LONGFORM_EDITING_CANONICAL_RULES_v1_0"],
 "caps":{"voice":{"provider":"KOKORO","mode":"TWO_VOICE_DIALOGUE","casting":"DECLARATIVE_PER_EPISODE","smoke_fixture_voices":["af_heart","am_liam"],"timeline_authority":"ACTUAL_GENERATED_WAV"},"editing":{"mode":"DIALOGUE_STORY_BEAT","static_first":True,"speaker_focus":True,"motion_scope":"VISUAL_RUN"},"subtitles":{"mode":"EXTERNAL_SRT","timing_authority":"ACTUAL_NARRATION_WAV"},"publishing":{"package_required":True},"visual":{"mode":"STORY_STILLS","speaker_focus_supported":True}}
},
"en_bts":{
 "class":"ENBTSReferenceAdapter","aid":"EN_BTS_REFERENCE_ADAPTER_v1_0","cid":"EN_BTS","profile":"EN_TECH_v1","name":"Between the Steps","rules":["BTS_CANONICAL_VISUAL_TEMPLATE_v1_1"],
 "caps":{"voice":{"provider":"KOKORO","mode":"SINGLE_DEFAULT","default_voice":"af_heart","timeline_authority":"ACTUAL_GENERATED_WAV"},"editing":{"mode":"INFORMATION_FIRST","visual_runs":"STRUCTURED_SHORTER"},"subtitles":{"mode":"EXTERNAL_SRT","timing_authority":"ACTUAL_NARRATION_WAV"},"publishing":{"package_required":True,"front_end_gate":"REVENUE_FIRST"},"visual":{"canonical":"BTS_CANONICAL_VISUAL_TEMPLATE_v1_1","containerless_default":True,"arrows_default":False,"subtitle_safe_y":[820,1080]}}
},
"jp_bts":{
 "class":"JPBTSReferenceAdapter","aid":"JP_BTS_REFERENCE_ADAPTER_v1_0","cid":"JP_BTS","profile":"JP_TECH_v1","name":"Japanese Between the Steps","rules":["LONGFORM_FACTORY_JP_VOICE_CASTING_POLICY_v1_0"],
 "caps":{"voice":{"provider":"VOICEVOX","mode":"MULTI_VOICE","allowed_pairings":["male/female","male/male","female/female"],"style_resolution":"DYNAMIC_BY_SPEAKER_AND_STYLE_NAME","timeline_authority":"ACTUAL_GENERATED_WAV"},"editing":{"mode":"INFORMATION_FIRST","role_mapping":"DETERMINISTIC_WITHIN_EPISODE"},"subtitles":{"mode":"EXTERNAL_SRT","language":"ja","timing_authority":"ACTUAL_GENERATED_WAV"},"publishing":{"package_required":True},"visual":{"mode":"STRUCTURED_TECH","subtitle_safe_required":True}}
}
}

REG={
 "registry_version":"1.6","contract":"LONGFORM_FACTORY_ADAPTER_CONTRACT_v1_0",
 "adapters":{
  "JP_STORY_REFERENCE_ADAPTER_v1_0":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_0","module":"adapters.channels.jp_story.reference_adapter","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_REFERENCE_ADAPTER_v1_1":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_1","module":"adapters.channels.jp_story.reference_adapter_v11","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_REFERENCE_ADAPTER_v1_2":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_2","module":"adapters.channels.jp_story.reference_adapter_v12","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_LEGACY_MEDIA_ADAPTER_v1_0":{"adapter_id":"JP_STORY_LEGACY_MEDIA_ADAPTER_v1_0","module":"adapters.channels.jp_story.legacy_media_adapter","class":"JPStoryLegacyMediaAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.0,<1.2","profile":"JP_STORY_v1"}},
  "JP_STORY_REFERENCE_ADAPTER_v1_3":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_3","module":"adapters.channels.jp_story.reference_adapter_v13","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_LEGACY_MEDIA_ADAPTER_v1_1":{"adapter_id":"JP_STORY_LEGACY_MEDIA_ADAPTER_v1_1","module":"adapters.channels.jp_story.legacy_media_adapter_v11","class":"JPStoryLegacyMediaAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.0,<1.2","profile":"JP_STORY_v1"}},
  "JP_STORY_REFERENCE_ADAPTER_v1_4":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_4","module":"adapters.channels.jp_story.reference_adapter_v14","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"ACTIVE_REFERENCE","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_LEGACY_MEDIA_ADAPTER_v1_2":{"adapter_id":"JP_STORY_LEGACY_MEDIA_ADAPTER_v1_2","module":"adapters.channels.jp_story.legacy_media_adapter_v12","class":"JPStoryLegacyMediaAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_RUNTIME_COMPAT","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.0,<1.2","profile":"JP_STORY_v1"}}
 },
 "channels":{"JP_STORY":{"default_adapter":"JP_STORY_REFERENCE_ADAPTER_v1_4","profile":"JP_STORY_v1","status":"ACTIVE_REFERENCE","legacy_default_adapter":"JP_STORY_LEGACY_MEDIA_ADAPTER_v1_2","integration_status":"ACTIVE_MEDIA_REFERENCE"}}
}
for mod,c in CHANNELS.items():
    REG["adapters"][c["aid"]]={"adapter_id":c["aid"],"module":f"adapters.channels.{mod}.reference_adapter_v10","class":c["class"],"channel_id":c["cid"],"profile":c["profile"],"status":"ACTIVE_CAPABILITY","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":c["profile"]}}
    REG["channels"][c["cid"]]={"default_adapter":c["aid"],"profile":c["profile"],"status":"ACTIVE_CAPABILITY","media_binding":"PENDING_MEDIA_SMOKE"}

QA='''from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
from shared_core.adapter_runtime import AdapterManager, AdapterError

EXPECTED={
 "JP_STORY":("JP_STORY_v1","JP_STORY_REFERENCE_ADAPTER_v1_4"),
 "EN_STORY":("EN_DRAMA_v1","EN_STORY_REFERENCE_ADAPTER_v1_0"),
 "EN_BTS":("EN_TECH_v1","EN_BTS_REFERENCE_ADAPTER_v1_0"),
 "JP_BTS":("JP_TECH_v1","JP_BTS_REFERENCE_ADAPTER_v1_0"),
}
def _m(cid,p):
 return {"schema_version":"1.2","channel_id":cid,"profile":p,"episode_id":cid+"_EP999","authority":{},"lifecycle":{"current_stage":"DISCOVERY"}}

def _media_report(root):
 p=Path(root)/"factory"/"state"/"cross_channel_media_smoke.json"
 try: return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
 except Exception: return {}

def run_cross_channel_qa(root:Path):
 a=AdapterManager(Path(root)); checks=[]; matrix={}
 def add(n,ok,d=""): checks.append({"name":n,"status":"PASS" if ok else "FAIL","detail":str(d)})
 reg=a.registry()
 add("Registry version",reg.get("registry_version")=="1.6",reg.get("registry_version"))
 for cid,(p,aid) in EXPECTED.items():
  m=_m(cid,p)
  try:
   resolved=a.adapter_id_for_manifest(m)
   desc=a.describe(m)
   add(cid+" default dispatch",resolved==aid and desc.get("channel_id")==cid and desc.get("profile_id")==p,f"{resolved} · {desc.get('integration_status','ACTIVE_REFERENCE')}")
   matrix[cid]=desc
  except Exception as e:
   add(cid+" default dispatch",False,e)
   continue
  bad=_m(cid,"WRONG_PROFILE_v0"); rejected=False
  try: a.describe(bad)
  except AdapterError: rejected=True
  add(cid+" profile isolation",rejected,"wrong profile rejected" if rejected else "wrong profile accepted")

 bad=_m("EN_STORY","EN_DRAMA_v1")
 bad["authority"]["channel_adapter"]="JP_BTS_REFERENCE_ADAPTER_v1_0"; rejected=False
 try: a.describe(bad)
 except AdapterError: rejected=True
 add("Pinned adapter/channel isolation",rejected,"cross-channel pin rejected" if rejected else "cross-channel pin accepted")

 jp=reg.get("channels",{}).get("JP_STORY",{})
 add("JP legacy compatibility preserved",jp.get("legacy_default_adapter")=="JP_STORY_LEGACY_MEDIA_ADAPTER_v1_2",jp.get("legacy_default_adapter"))

 report=_media_report(root)
 false_claims=[]; stale_pending=[]
 for cid in ("EN_STORY","EN_BTS","JP_BTS"):
  evidence=report.get("channels",{}).get(cid,{}).get("status")=="PASS"
  binding=matrix.get(cid,{}).get("media_binding")
  if binding=="ACTIVE_MEDIA_SMOKE" and not evidence: false_claims.append(cid)
  if evidence and binding!="ACTIVE_MEDIA_SMOKE": stale_pending.append(cid)
 add("No false media-complete claims",not false_claims,"none" if not false_claims else ",".join(false_claims))
 add("Media smoke binding consistency",not stale_pending,"consistent" if not stale_pending else "stale:"+",".join(stale_pending))

 out={"schema":"LONGFORM_FACTORY_CROSS_CHANNEL_QA_v1_2","created_at":datetime.now(timezone.utc).isoformat(),"state":"PASS" if all(x["status"]=="PASS" for x in checks) else "FAIL","checks":checks,"matrix":matrix,"media_smoke":report.get("channels",{}),"next_media_smoke_order":["EN_STORY","EN_BTS","JP_BTS"]}
 p=Path(root)/"factory"/"state"/"cross_channel_qa.json"; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
 return out
'''

MEDIA_SMOKE='''from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json, math, os, shutil, subprocess, traceback, urllib.parse, urllib.request, wave

CHANNELS=("EN_STORY","EN_BTS","JP_BTS")
STATE_REL=Path("factory/state/cross_channel_media_smoke.json")
QA_REL=Path("factory/_qa/cross_channel_media")

def _now(): return datetime.now(timezone.utc).isoformat()
def _slug_now(): return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
def _load(path):
 try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
 except Exception: return {}
def _save(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
def _check(name,ok,detail=""): return {"name":name,"status":"PASS" if ok else "FAIL","detail":str(detail)}
def _run(cmd,timeout=180):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
 if p.returncode!=0: raise RuntimeError("command failed: "+" ".join(map(str,cmd))+"\\n"+p.stderr[-1600:])
 return p.stdout
def _wav_info(path):
 with wave.open(str(path),"rb") as w:
  frames=w.getnframes(); sr=w.getframerate(); ch=w.getnchannels(); sw=w.getsampwidth()
 return {"frames":frames,"sample_rate":sr,"channels":ch,"sample_width":sw,"duration":frames/sr if sr else 0}
def _write_pcm16(path,audio,sr):
 import numpy as np
 a=np.asarray(audio,dtype=np.float32).reshape(-1)
 a=np.clip(a,-1,1); pcm=(a*32767.0).astype("<i2")
 path.parent.mkdir(parents=True,exist_ok=True)
 with wave.open(str(path),"wb") as w:
  w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(sr)); w.writeframes(pcm.tobytes())
def _concat_wavs(parts,out,gap_ms=220):
 infos=[_wav_info(p) for p in parts]
 if not infos: raise RuntimeError("no wav parts")
 sr=infos[0]["sample_rate"]; ch=infos[0]["channels"]; sw=infos[0]["sample_width"]
 if any((x["sample_rate"],x["channels"],x["sample_width"])!=(sr,ch,sw) for x in infos): raise RuntimeError("wav format mismatch")
 gap=b"\\x00"*(int(sr*gap_ms/1000)*ch*sw)
 with wave.open(str(out),"wb") as dst:
  dst.setnchannels(ch); dst.setsampwidth(sw); dst.setframerate(sr)
  for i,p in enumerate(parts):
   with wave.open(str(p),"rb") as src: dst.writeframes(src.readframes(src.getnframes()))
   if i<len(parts)-1: dst.writeframes(gap)
 return _wav_info(out)
def _srt_time(sec):
 ms=max(0,int(round(sec*1000))); h=ms//3600000; ms%=3600000; m=ms//60000; ms%=60000; s=ms//1000; ms%=1000
 return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
def _write_srt(lines,durations,out,gap=0.22):
 t=0.0; blocks=[]
 for i,(txt,d) in enumerate(zip(lines,durations),1):
  blocks.append(f"{i}\\n{_srt_time(t)} --> {_srt_time(t+d)}\\n{txt}\\n")
  t+=d+(gap if i<len(lines) else 0)
 out.write_text("\\n".join(blocks),encoding="utf-8")
 return t
def _font(size):
 from PIL import ImageFont
 for p in ["/System/Library/Fonts/Supplemental/Arial.ttf","/System/Library/Fonts/Supplemental/Arial Bold.ttf","/Library/Fonts/Arial.ttf"]:
  if Path(p).exists():
   try:return ImageFont.truetype(p,size)
   except Exception: pass
 return ImageFont.load_default()
def _make_story_frames(outdir,count):
 from PIL import Image,ImageDraw
 out=[]
 for i in range(count):
  active=i%2
  im=Image.new("RGB",(1920,1080),(222,224,228)); d=ImageDraw.Draw(im)
  d.rectangle((0,0,959,820),fill=(205,208,214)); d.rectangle((960,0,1919,820),fill=(195,198,205))
  d.text((110,90),"EN_STORY MEDIA SMOKE",fill=(20,20,24),font=_font(52))
  d.text((250,360),"SPEAKER A",fill=(20,20,24),font=_font(70)); d.text((1210,360),"SPEAKER B",fill=(20,20,24),font=_font(70))
  overlay=Image.new("RGBA",im.size,(0,0,0,0)); od=ImageDraw.Draw(overlay)
  if active==0: od.rectangle((960,0,1919,820),fill=(0,0,0,153))
  else: od.rectangle((0,0,959,820),fill=(0,0,0,153))
  im=Image.alpha_composite(im.convert("RGBA"),overlay).convert("RGB"); d=ImageDraw.Draw(im)
  d.text((110,745),"Fixed frame · inactive side dimmed",fill=(30,30,34),font=_font(30))
  p=outdir/f"focus_{i+1:02d}.png"; im.save(p); out.append(p)
 return out
def _make_info_frames(outdir,label,count):
 from PIL import Image,ImageDraw
 out=[]
 for i in range(count):
  im=Image.new("RGB",(1920,1080),(244,245,247)); d=ImageDraw.Draw(im)
  d.text((120,95),label,fill=(20,22,28),font=_font(54))
  d.text((120,270),f"VISUAL RUN {i+1}",fill=(20,22,28),font=_font(92))
  d.text((120,455),"Actual generated audio controls this run.",fill=(45,48,55),font=_font(42))
  d.line((120,650,1700,650),fill=(100,105,115),width=3)
  d.text((120,700),"Subtitle-safe region begins below y=820",fill=(70,74,82),font=_font(30))
  # Keep y>=820 visually empty by design.
  p=outdir/f"run_{i+1:02d}.png"; im.save(p); out.append(p)
 return out
def _render(images,durations,audio,outdir):
 ffmpeg=shutil.which("ffmpeg"); ffprobe=shutil.which("ffprobe")
 if not ffmpeg or not ffprobe: raise RuntimeError("ffmpeg/ffprobe not found")
 concat=outdir/"visuals.ffconcat"
 rows=["ffconcat version 1.0"]
 for p,d in zip(images,durations):
  rows += [f"file '{str(p).replace(chr(39),chr(39)+chr(92)+chr(39)+chr(39))}'",f"duration {max(0.05,d):.6f}"]
 rows.append(f"file '{str(images[-1]).replace(chr(39),chr(39)+chr(92)+chr(39)+chr(39))}'")
 concat.write_text("\\n".join(rows)+"\\n",encoding="utf-8")
 silent=outdir/"silent.mp4"; final=outdir/"media_smoke.mp4"
 _run([ffmpeg,"-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",str(concat),"-vf","fps=30,format=yuv420p","-c:v","libx264","-preset","veryfast","-movflags","+faststart",str(silent)],240)
 _run([ffmpeg,"-y","-hide_banner","-loglevel","error","-i",str(silent),"-i",str(audio),"-c:v","copy","-c:a","aac","-b:a","160k","-shortest","-movflags","+faststart",str(final)],240)
 probe=json.loads(_run([ffprobe,"-v","error","-show_entries","format=duration:stream=width,height,codec_type","-of","json",str(final)],60))
 return final,probe
def _kokoro_lines(lines,voices,speeds,outdir):
 try:
  from kokoro import KPipeline
 except Exception as e: raise RuntimeError("Kokoro import failed: "+repr(e))
 import numpy as np
 pipe=KPipeline(lang_code="a"); parts=[]; durations=[]
 for i,(txt,voice,speed) in enumerate(zip(lines,voices,speeds),1):
  chunks=[]
  for item in pipe(txt,voice=voice,speed=float(speed)):
   audio=item[-1]
   chunks.append(np.asarray(audio,dtype=np.float32).reshape(-1))
  if not chunks: raise RuntimeError(f"Kokoro produced no audio for line {i}")
  p=outdir/f"line_{i:02d}_{voice}.wav"; _write_pcm16(p,np.concatenate(chunks),24000); parts.append(p); durations.append(_wav_info(p)["duration"])
 return parts,durations
def _http_json(url,method="GET",body=None,timeout=8):
 req=urllib.request.Request(url,data=body,method=method)
 if body is not None: req.add_header("Content-Type","application/json")
 with urllib.request.urlopen(req,timeout=timeout) as r: return json.loads(r.read().decode("utf-8"))
def _voicevox_alive(base):
 try:
  with urllib.request.urlopen(base+"/version",timeout=2) as r: return bool(r.read())
 except Exception: return False
def _try_voicevox_bootstrap(root,base):
 if _voicevox_alive(base): return "already_running"
 try:
  from adapters.voice import voicevox_bootstrap as vb
  for name in ("ensure_voicevox_engine","ensure_voicevox","ensure_engine","bootstrap_voicevox","start_voicevox"):
   fn=getattr(vb,name,None)
   if callable(fn):
    try:
     import inspect
     if len([p for p in inspect.signature(fn).parameters.values() if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY,p.POSITIONAL_OR_KEYWORD)])==0:
      fn()
      import time
      for _ in range(30):
       if _voicevox_alive(base): return name
       time.sleep(0.3)
    except Exception:
     pass
 except Exception:
  pass
 return "not_started"
def _vv_style(speakers,speaker_names,style_names=("ノーマル","Normal")):
 for wanted in speaker_names:
  for sp in speakers:
   if sp.get("name")==wanted:
    styles=sp.get("styles",[])
    for sn in style_names:
     for st in styles:
      if st.get("name")==sn: return {"speaker":wanted,"style_name":st.get("name"),"style_id":st.get("id")}
    if styles: return {"speaker":wanted,"style_name":styles[0].get("name"),"style_id":styles[0].get("id")}
 return None
def _voicevox_lines(root,lines,outdir):
 base=os.environ.get("VOICEVOX_BASE_URL","http://127.0.0.1:50021").rstrip("/")
 boot=_try_voicevox_bootstrap(root,base)
 if not _voicevox_alive(base): raise RuntimeError("VOICEVOX engine unavailable at "+base+"; bootstrap="+boot)
 speakers=_http_json(base+"/speakers")
 a=_vv_style(speakers,["青山龍星"])
 b=_vv_style(speakers,["四国めたん","春日部つむぎ","冥鳴ひまり"])
 if not a or not b: raise RuntimeError("required VOICEVOX named speakers unavailable")
 selected=[a,b,a,b]; parts=[]; durations=[]
 for i,(txt,sel) in enumerate(zip(lines,selected),1):
  qurl=base+"/audio_query?"+urllib.parse.urlencode({"text":txt,"speaker":sel["style_id"]})
  q=_http_json(qurl,method="POST",body=b"{}")
  raw=json.dumps(q,ensure_ascii=False).encode("utf-8")
  surl=base+"/synthesis?"+urllib.parse.urlencode({"speaker":sel["style_id"]})
  req=urllib.request.Request(surl,data=raw,method="POST"); req.add_header("Content-Type","application/json")
  with urllib.request.urlopen(req,timeout=45) as r: wav=r.read()
  p=outdir/f"line_{i:02d}_{sel['speaker']}.wav"; p.write_bytes(wav); parts.append(p); durations.append(_wav_info(p)["duration"])
 return parts,durations,{"base_url":base,"bootstrap":boot,"role_map":{"A":a,"B":b}}
def _run_channel(root,cid):
 root=Path(root); outdir=root/QA_REL/cid/_slug_now(); outdir.mkdir(parents=True,exist_ok=False)
 checks=[]; evidence={}
 try:
  checks.append(_check("QA output isolation",str(outdir).startswith(str(root/"factory"/"_qa")) and cid in CHANNELS,str(outdir)))
  checks.append(_check("ffmpeg",bool(shutil.which("ffmpeg")),shutil.which("ffmpeg") or "missing"))
  checks.append(_check("ffprobe",bool(shutil.which("ffprobe")),shutil.which("ffprobe") or "missing"))
  try:
   import PIL
   checks.append(_check("Pillow",True,getattr(PIL,"__version__","available")))
  except Exception as e:
   checks.append(_check("Pillow",False,e))
  if not all(x["status"]=="PASS" for x in checks): raise RuntimeError("media prerequisites failed")

  gap=0.22
  if cid=="EN_STORY":
   lines=["I thought we agreed to meet here.","We did. I came because the evidence changed.","Then say what changed.","The timeline finally matches the recording."]
   voices=["af_heart","am_liam","af_heart","am_liam"]; speeds=[0.96,1.0,0.96,1.0]
   parts,durs=_kokoro_lines(lines,voices,speeds,outdir)
   images=_make_story_frames(outdir,len(lines))
   evidence["voice_roles"]={"A":"af_heart","B":"am_liam"}; evidence["speaker_focus"]="FIXED_FRAME_DIM_REST"
  elif cid=="EN_BTS":
   lines=["A queue number is not always the same thing as your final position.","The system can apply several gates before inventory is assigned.","That is why joining early does not guarantee the first offer."]
   voices=["af_heart"]*len(lines); speeds=[0.96]*len(lines)
   parts,durs=_kokoro_lines(lines,voices,speeds,outdir)
   images=_make_info_frames(outdir,"EN_BTS MEDIA SMOKE",len(lines))
   evidence["voice_roles"]={"narrator":"af_heart"}; evidence["visual_canonical"]="CONTAINERLESS_SUBTITLE_SAFE"
  elif cid=="JP_BTS":
   lines=["これはメディア統合の確認です。","役割ごとに音声を固定します。","実際の音声時間を基準にします。","字幕と映像も同じ時間軸で確認します。"]
   parts,durs,vm=_voicevox_lines(root,lines,outdir)
   images=_make_info_frames(outdir,"JP_BTS MEDIA SMOKE",len(lines))
   evidence["voice_roles"]=vm["role_map"]; evidence["style_resolution"]="DYNAMIC_BY_SPEAKER_AND_STYLE_NAME"; evidence["voicevox"]=vm
  else: raise RuntimeError("unsupported channel "+cid)

  master=outdir/"master.wav"; minfo=_concat_wavs(parts,master,int(gap*1000))
  srt=outdir/"upload.srt"; expected=_write_srt(lines,durs,srt,gap)
  visual_durs=[d+(gap if i<len(durs)-1 else 0) for i,d in enumerate(durs)]
  mp4,probe=_render(images,visual_durs,master,outdir)
  vdur=float(probe.get("format",{}).get("duration",0) or 0); adur=minfo["duration"]
  streams=probe.get("streams",[]); video=next((s for s in streams if s.get("codec_type")=="video"),{})
  checks += [
   _check("Generated WAV exists",master.exists() and master.stat().st_size>1000,master.stat().st_size if master.exists() else 0),
   _check("Actual-WAV timeline authority",abs(adur-expected)<0.08,f"wav={adur:.3f}s srt_timeline={expected:.3f}s"),
   _check("External SRT exists",srt.exists() and srt.stat().st_size>30,str(srt)),
   _check("1920x1080 render",video.get("width")==1920 and video.get("height")==1080,f"{video.get('width')}x{video.get('height')}"),
   _check("A/V duration sync",abs(vdur-adur)<0.20,f"video={vdur:.3f}s audio={adur:.3f}s"),
   _check("Rendered MP4 exists",mp4.exists() and mp4.stat().st_size>10000,mp4.stat().st_size if mp4.exists() else 0),
  ]
  status="PASS" if all(x["status"]=="PASS" for x in checks) else "FAIL"
  return {"channel_id":cid,"status":status,"started_and_finished_at":_now(),"checks":checks,"evidence":evidence,"outputs":{"root":str(outdir.relative_to(root)),"audio":str(master.relative_to(root)),"srt":str(srt.relative_to(root)),"video":str(mp4.relative_to(root))},"metrics":{"audio_duration":adur,"video_duration":vdur,"line_durations":durs}}
 except Exception as e:
  return {"channel_id":cid,"status":"FAIL","started_and_finished_at":_now(),"checks":checks+[_check("Smoke execution",False,str(e))],"evidence":evidence,"error":str(e),"traceback":"\\n".join(traceback.format_exc().splitlines()[-12:]),"outputs":{"root":str(outdir.relative_to(root))}}

def media_smoke_status(root):
 p=Path(root)/STATE_REL
 d=_load(p)
 if not d: d={"schema":"LONGFORM_FACTORY_CROSS_CHANNEL_MEDIA_SMOKE_v1","updated_at":None,"state":"NOT_RUN","channels":{}}
 return d

def run_media_smoke(root,channel_id):
 root=Path(root); cid=(channel_id or "").strip().upper()
 if cid not in CHANNELS: raise ValueError("channel_id must be one of "+", ".join(CHANNELS))
 state=media_smoke_status(root); state.setdefault("channels",{})
 result=_run_channel(root,cid); state["channels"][cid]=result; state["updated_at"]=_now()
 vals=[state["channels"].get(x,{}).get("status") for x in CHANNELS]
 state["state"]="PASS" if all(x=="PASS" for x in vals) else ("FAIL" if any(x=="FAIL" for x in vals) else "PARTIAL")
 _save(root/STATE_REL,state)
 return state
'''

CONTINUITY='''from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json, re

CHANNELS={
 "EN_STORY":{"profile":"EN_DRAMA_v1","adapter":"EN_STORY_REFERENCE_ADAPTER_v1_0","rules":["STORY_LONGFORM_EDITING_CANONICAL_RULES_v1_0"]},
 "EN_BTS":{"profile":"EN_TECH_v1","adapter":"EN_BTS_REFERENCE_ADAPTER_v1_0","rules":["BTS_CANONICAL_VISUAL_TEMPLATE_v1_1"]},
 "JP_STORY":{"profile":"JP_STORY_v1","adapter":"JP_STORY_REFERENCE_ADAPTER_v1_4","rules":["JP_STORY_SUPERVISED_FACTORY"]},
 "JP_BTS":{"profile":"JP_TECH_v1","adapter":"JP_BTS_REFERENCE_ADAPTER_v1_0","rules":["LONGFORM_FACTORY_JP_VOICE_CASTING_POLICY_v1_0"]},
}
REGISTRY_REL=Path("factory/handoff/registry.json")
EP_RE=re.compile(r"_(?:EP)(\\d{3})$")

def _now(): return datetime.now(timezone.utc).isoformat()
def _read(path,default=None):
 try:return json.loads(path.read_text(encoding="utf-8")) if path.exists() else ({} if default is None else default)
 except Exception:return {} if default is None else default
def _write_json(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
def _write_text(path,text):
 path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text.rstrip()+"\\n",encoding="utf-8")
def _episode_num(name):
 m=EP_RE.search(name); return int(m.group(1)) if m else -1
def _manifest_candidates(root,cid):
 ep_root=Path(root)/"projects"/cid/"episodes"
 if not ep_root.exists(): return []
 rows=[]
 for d in ep_root.iterdir():
  if not d.is_dir(): continue
  p=d/"episode_manifest.json"
  if p.exists(): rows.append((d,p,_read(p,{})))
 return sorted(rows,key=lambda x:(_episode_num(x[0].name),x[0].name))
def _locked_assets(m):
 out=[]
 auth=m.get("authority",{}) if isinstance(m.get("authority",{}),dict) else {}
 for k,v in auth.items():
  if isinstance(v,str) and v: out.append({"role":k,"value":v})
 return out[:40]
def _stage(m): return (m.get("lifecycle") or {}).get("current_stage") or "UNKNOWN"
def _episode_status(m): return (m.get("lifecycle") or {}).get("status") or m.get("status") or "UNKNOWN"
def _safe_episode_handoff(m):
 try:return float(str(m.get("schema_version","0")))>=1.2
 except Exception:return False

def _episode_state(root,cid,d,m):
 eid=m.get("episode_id") or d.name
 stage=_stage(m); status=_episode_status(m)
 return {
  "schema":"LONGFORM_FACTORY_EPISODE_STATE_v1",
  "generated_at":_now(),
  "channel_id":cid,
  "episode_id":eid,
  "AUTHORITY":{"manifest":str((d/"episode_manifest.json").relative_to(root)),"schema_version":str(m.get("schema_version",""))},
  "CURRENT_STAGE":stage,
  "LOCKED_ASSETS":_locked_assets(m),
  "ACTIVE_RULES":CHANNELS[cid]["rules"],
  "OPEN_DECISIONS":[],
  "KNOWN_FAILURES":[],
  "NEXT_ACTION":"Continue from Factory manifest current stage: "+stage,
  "DO_NOT_REOPEN":["LOCK/FINAL_LOCK assets unless a concrete production failure requires it","completed earlier stages without an explicit authority change"],
  "status":status,
 }
def _episode_md(s):
 return f"""# {s['episode_id']} — Chat Handoff
AUTHORITY: {s['AUTHORITY']['manifest']}
CURRENT_STAGE: {s['CURRENT_STAGE']}
STATUS: {s['status']}
ACTIVE_RULES: {', '.join(s['ACTIVE_RULES']) or 'none'}
NEXT_ACTION: {s['NEXT_ACTION']}

DO_NOT_REOPEN:
"""+"\\n".join("- "+x for x in s["DO_NOT_REOPEN"])

def generate_continuity_snapshot(root):
 root=Path(root)
 media=_read(root/"factory"/"state"/"cross_channel_media_smoke.json",{})
 qa=_read(root/"factory"/"state"/"cross_channel_qa.json",{})
 old=_read(root/REGISTRY_REL,{})
 result={"schema":"LONGFORM_FACTORY_HANDOFF_REGISTRY_v1","generated_at":_now(),"factory_version":"1.12.1","channels":{}}
 for cid,cfg in CHANNELS.items():
  eps=_manifest_candidates(root,cid)
  latest=eps[-1] if eps else None
  old_ch=(old.get("channels",{}).get(cid,{}) or {})
  active_hint=old_ch.get("active_workstream_hint")
  next_hint=old_ch.get("next_action_hint")
  inferred_episode=(latest[2].get("episode_id") or latest[0].name) if latest else None
  active_episode=active_hint or inferred_episode
  active_stage=("PINNED_EXTERNAL_WORKSTREAM" if active_hint and active_hint!=inferred_episode else (_stage(latest[2]) if latest else "NO_FACTORY_MANAGED_EPISODE"))
  ch_media=(media.get("channels",{}).get(cid,{}) or {}).get("status")
  state={
   "schema":"LONGFORM_FACTORY_CHANNEL_STATE_v1","generated_at":_now(),"channel_id":cid,
   "AUTHORITY":{"profile":cfg["profile"],"adapter":cfg["adapter"],"registry":str(REGISTRY_REL)},
   "CURRENT_STAGE":active_stage,
   "LOCKED_ASSETS":[],
   "ACTIVE_RULES":cfg["rules"],
   "OPEN_DECISIONS":[],
   "KNOWN_FAILURES":[],
   "NEXT_ACTION":next_hint or ("Resume "+active_episode+" from "+active_stage if active_episode else "Declare or create the next Factory-managed workstream."),
   "DO_NOT_REOPEN":["legacy completed episodes","LOCK/FINAL_LOCK assets without concrete failure evidence","superseded production paths"],
   "active_episode":active_episode,
   "active_workstream_hint":active_hint,
   "media_smoke":ch_media or ("ACTIVE_REFERENCE" if cid=="JP_STORY" else "NOT_RUN"),
   "cross_channel_qa":qa.get("state","NOT_RUN"),
  }
  hp=root/"projects"/cid/"handoff"; _write_json(hp/"CHANNEL_STATE.json",state)
  md=f"""# {cid} — Channel Handoff
AUTHORITY: {cfg['profile']} / {cfg['adapter']}
CURRENT_STAGE: {active_stage}
ACTIVE_EPISODE: {active_episode or 'none detected'}
ACTIVE_WORKSTREAM_HINT: {active_hint or 'none'}
MEDIA: {state['media_smoke']}
NEXT_ACTION: {state['NEXT_ACTION']}

ACTIVE_RULES:
"""+"\\n".join("- "+x for x in cfg["rules"])+"""\\n
DO_NOT_REOPEN:
"""+"\\n".join("- "+x for x in state["DO_NOT_REOPEN"])
  _write_text(hp/"CHANNEL_HANDOFF.md",md)
  episode_pointer=None
  if latest and _safe_episode_handoff(latest[2]):
   es=_episode_state(root,cid,latest[0],latest[2]); eh=latest[0]/"handoff"
   _write_json(eh/"EPISODE_STATE.json",es); _write_text(eh/"CHAT_HANDOFF.md",_episode_md(es))
   episode_pointer=str((eh/"EPISODE_STATE.json").relative_to(root))
  result["channels"][cid]={
   "channel_state":str((hp/"CHANNEL_STATE.json").relative_to(root)),
   "channel_handoff":str((hp/"CHANNEL_HANDOFF.md").relative_to(root)),
   "active_episode":active_episode,
   "active_episode_state":episode_pointer,
   "active_workstream_hint":active_hint,
   "current_stage":active_stage,
  }
 _write_json(root/REGISTRY_REL,result)
 return result

def continuity_status(root):
 root=Path(root); p=root/REGISTRY_REL
 if not p.exists(): return {"state":"NOT_GENERATED","registry":str(REGISTRY_REL),"channels":{}}
 d=_read(p,{})
 return {"state":"READY","registry":str(REGISTRY_REL),"generated_at":d.get("generated_at"),"channels":d.get("channels",{})}

def set_active_workstream_hint(root,channel_id,episode_id,next_action=None):
 root=Path(root); cid=(channel_id or "").upper().strip()
 if cid not in CHANNELS: raise ValueError("unknown channel")
 if episode_id and not re.fullmatch(r"[A-Z_]+_EP\\d{3}",episode_id): raise ValueError("episode_id must use CHANNEL_EP###")
 reg=_read(root/REGISTRY_REL,{})
 reg.setdefault("schema","LONGFORM_FACTORY_HANDOFF_REGISTRY_v1"); reg.setdefault("channels",{})
 reg["channels"].setdefault(cid,{})["active_workstream_hint"]=episode_id or None
 if next_action: reg["channels"][cid]["next_action_hint"]=str(next_action)
 reg["generated_at"]=_now(); _write_json(root/REGISTRY_REL,reg)
 return generate_continuity_snapshot(root)
'''

REASONING='''from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json, re, uuid

TASK_ROOT=Path("factory/state/reasoning/tasks")
PROVIDER_ID="manual_handoff"

RESULT_SCHEMA={
 "type":"object",
 "required":["status","summary"],
 "properties":{
  "status":{"type":"string","enum":["PASS","REVIEW_REQUIRED","FAIL"]},
  "summary":{"type":"string"},
  "findings":{"type":"array","items":{"type":"object"}},
  "decisions":{"type":"array","items":{"type":"object"}},
  "next_action":{"type":["string","null"]},
 }
}

def _now(): return datetime.now(timezone.utc).isoformat()
def _write(path,obj): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
def _read(path):
 try:return json.loads(path.read_text(encoding="utf-8"))
 except Exception:return {}
def describe():
 return {"provider_id":PROVIDER_ID,"provider_type":"MANUAL_HANDOFF","contract":"LONGFORM_FACTORY_REASONING_PROVIDER_v1","description":"Provider-neutral manual bridge. Factory prepares a task packet; a human can run it in ChatGPT or another reasoning system and paste structured JSON back.","network_calls":False,"api_key_required":False}
def available(): return True
def supports_web(): return False
def result_schema(): return RESULT_SCHEMA
def _validate_result(x):
 if not isinstance(x,dict): raise ValueError("result must be a JSON object")
 if x.get("status") not in ("PASS","REVIEW_REQUIRED","FAIL"): raise ValueError("result.status invalid")
 if not isinstance(x.get("summary"),str) or not x.get("summary").strip(): raise ValueError("result.summary required")
 return True
def execute_task(root,task=None,result=None,task_id=None):
 root=Path(root)
 if result is None:
  if not isinstance(task,dict): raise ValueError("task object required")
  instruction=str(task.get("instruction") or "").strip()
  if not instruction: raise ValueError("task.instruction required")
  tid="RH_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:6]
  packet={
   "schema":"LONGFORM_FACTORY_REASONING_TASK_v1","task_id":tid,"created_at":_now(),
   "provider_id":PROVIDER_ID,"status":"AWAITING_MANUAL_RESULT",
   "task_type":str(task.get("task_type") or "GENERAL"),
   "channel_id":task.get("channel_id"),"episode_id":task.get("episode_id"),
   "instruction":instruction,"context":task.get("context") or {},
   "result_schema":RESULT_SCHEMA,
   "manual_prompt":"Return JSON only matching result_schema. Task: "+instruction,
  }
  _write(root/TASK_ROOT/(tid+".json"),packet); return packet
 tid=str(task_id or "").strip()
 if not re.fullmatch(r"RH_[A-Za-z0-9_]+",tid): raise ValueError("valid task_id required")
 p=root/TASK_ROOT/(tid+".json")
 packet=_read(p)
 if not packet: raise FileNotFoundError("reasoning task not found")
 _validate_result(result)
 packet["status"]="COMPLETE"; packet["completed_at"]=_now(); packet["result"]=result
 _write(p,packet); return packet
def status(root):
 root=Path(root); d=root/TASK_ROOT
 rows=[]
 if d.exists():
  for p in sorted(d.glob("RH_*.json"),reverse=True)[:20]:
   x=_read(p); rows.append({"task_id":x.get("task_id"),"status":x.get("status"),"task_type":x.get("task_type"),"channel_id":x.get("channel_id"),"episode_id":x.get("episode_id"),"created_at":x.get("created_at")})
 return {"provider":describe(),"available":available(),"supports_web":supports_web(),"result_schema":result_schema(),"recent_tasks":rows}
'''

CONT_PAGE='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Continuity</title>
<style>body{margin:0;background:#f5f6f8;color:#15171a;font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:1100px;margin:auto;padding:28px}.card{background:#fff;border:1px solid #e1e5ea;border-radius:14px;padding:18px;margin:14px 0}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.spacer{flex:1}.btn{border:1px solid #d1d5db;background:#fff;border-radius:8px;padding:9px 12px;cursor:pointer}.primary{background:#111827;color:#fff}.muted{color:#667085}.ok{color:#067647}.err{color:#b42318}textarea,input,select{width:100%;box-sizing:border-box;border:1px solid #d0d5dd;border-radius:8px;padding:9px;font:inherit}textarea{min-height:110px}pre{white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:8px;max-height:420px;overflow:auto}</style></head>
<body><div class="wrap"><div class="row"><div><h1 style="margin:0">Continuity & Reasoning</h1><div class="muted">Factory authority handoff, not chat memory.</div></div><div class="spacer"></div><button class="btn" onclick="location.href='/'">Dashboard</button></div>
<div class="card"><div class="row"><b>Continuity Snapshot</b><div class="spacer"></div><button class="btn primary" onclick="snapshot()">Generate / Refresh Snapshot</button></div><div id="cStatus" class="muted" style="margin-top:8px"></div><div id="channels" style="margin-top:12px"></div></div>
<div class="card"><b>Active Workstream Pin</b><div class="muted" style="margin:8px 0">Use this when the current chat/workstream exists before a Factory episode manifest.</div><div class="row"><div style="flex:1"><label>Channel</label><select id="pinChannel"><option>EN_STORY</option><option>EN_BTS</option><option>JP_STORY</option><option>JP_BTS</option></select></div><div style="flex:2"><label>Episode ID</label><input id="pinEpisode" placeholder="EN_BTS_EP005"></div></div><label style="display:block;margin-top:10px">Next action</label><input id="pinNext" placeholder="e.g. Continue Ticketmaster EP05 visual mapping"><button class="btn" style="margin-top:10px" onclick="pinActive()">Pin Active Workstream</button><div id="pinStatus" style="margin-top:8px"></div></div>
<div class="card"><b>Reasoning Provider Bridge</b><div id="rStatus" class="muted" style="margin:8px 0"></div><label>Task type</label><input id="taskType" value="GENERAL"><label style="display:block;margin-top:10px">Instruction</label><textarea id="instruction" placeholder="Describe the reasoning task to hand off."></textarea><button class="btn primary" style="margin-top:10px" onclick="prepare()">Prepare Manual Handoff</button><pre id="packet"></pre></div>
<div class="card"><b>Complete Manual Handoff</b><label>Task ID</label><input id="taskId" placeholder="RH_..."><label style="display:block;margin-top:10px">Result JSON</label><textarea id="resultJson" placeholder='{"status":"PASS","summary":"...","findings":[],"decisions":[],"next_action":null}'></textarea><button class="btn" style="margin-top:10px" onclick="completeTask()">Save Result</button><div id="completeStatus" style="margin-top:8px"></div></div>
</div><script>
async function jf(u,o){const r=await fetch(u,o||{});const t=await r.text();let x={};try{x=t?JSON.parse(t):{}}catch(e){throw new Error(t.slice(0,300))}if(!r.ok||x.ok===false)throw new Error(x.error||('HTTP '+r.status));return x}
function renderC(x){document.getElementById('cStatus').textContent=(x.state||'UNKNOWN')+(x.generated_at?' · '+x.generated_at:'');document.getElementById('channels').innerHTML=Object.entries(x.channels||{}).map(([k,v])=>'<div><b>'+k+'</b> · '+(v.active_episode||v.active_workstream_hint||'no active episode')+' · '+(v.current_stage||'')+'</div>').join('')}
async function load(){try{renderC(await jf('/api/continuity/status'))}catch(e){}try{const x=await jf('/api/reasoning/status');document.getElementById('rStatus').textContent=x.provider.provider_id+' · available='+x.available+' · API key required='+x.provider.api_key_required}catch(e){}}
async function snapshot(){try{renderC(await jf('/api/continuity/snapshot',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}))}catch(e){document.getElementById('cStatus').textContent=e.message}}
async function pinActive(){try{const x=await jf('/api/continuity/active',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:document.getElementById('pinChannel').value,episode_id:document.getElementById('pinEpisode').value,next_action:document.getElementById('pinNext').value})});renderC(x);document.getElementById('pinStatus').className='ok';document.getElementById('pinStatus').textContent='Pinned.'}catch(e){document.getElementById('pinStatus').className='err';document.getElementById('pinStatus').textContent=e.message}}
async function prepare(){try{const x=await jf('/api/reasoning/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_type:document.getElementById('taskType').value,instruction:document.getElementById('instruction').value})});document.getElementById('packet').textContent=JSON.stringify(x,null,2);document.getElementById('taskId').value=x.task_id}catch(e){document.getElementById('packet').textContent=e.message}}
async function completeTask(){try{const result=JSON.parse(document.getElementById('resultJson').value);const x=await jf('/api/reasoning/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_id:document.getElementById('taskId').value,result})});document.getElementById('completeStatus').className='ok';document.getElementById('completeStatus').textContent='Saved '+x.task_id+' · '+x.status}catch(e){document.getElementById('completeStatus').className='err';document.getElementById('completeStatus').textContent=e.message}}
load();
</script></body></html>'''

PAGE='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Channel Integration</title>
<style>
body{margin:0;background:#f5f6f8;color:#15171a;font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1120px;margin:auto;padding:28px}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.spacer{flex:1}
.card{background:#fff;border:1px solid #e1e5ea;border-radius:14px;padding:18px;margin:14px 0}
.btn{border:1px solid #d1d5db;background:#fff;border-radius:8px;padding:9px 12px;cursor:pointer}.btn:disabled{opacity:.5;cursor:wait}
.primary{background:#111827;color:white;border-color:#111827}.muted{color:#667085}.pass{color:#067647}.fail{color:#b42318}.running{color:#175cd3}
#mediaButtons{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:16px}
.media-btn{display:flex;flex-direction:column;align-items:flex-start;gap:6px;border:0;border-radius:12px;padding:16px 18px;background:#175cd3;color:#fff;cursor:pointer;min-height:78px;text-align:left;box-shadow:0 1px 2px rgba(16,24,40,.08)}
.media-btn:hover{filter:brightness(.96)}.media-btn:disabled{opacity:.55;cursor:wait}.media-btn .channel{font-size:16px;font-weight:700}.media-btn .action{font-size:12px;opacity:.9}
.media-btn[data-status="PASS"]{background:#067647}.media-btn[data-status="FAIL"]{background:#b42318}
#error,#mediaError{margin-top:10px;white-space:pre-wrap}.hidden{display:none}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:9px;border-top:1px solid #eee;vertical-align:top}
@media(max-width:780px){#mediaButtons{grid-template-columns:1fr}}
</style></head>
<body><div class="wrap"><div class="row"><div><h1 style="margin:0">Cross-Channel Integration</h1><div class="muted">Registry isolation + representative media smoke</div></div><div class="spacer"></div><button class="btn" onclick="location.href='/'">Dashboard</button></div>
<div class="card"><div class="row"><div><b>Core / Adapter QA</b> · <b id="state">NOT RUN</b></div><div class="spacer"></div><button id="runBtn" class="btn primary" onclick="runqa()">Run Cross-Channel QA</button></div><div id="progress" class="muted" style="margin-top:8px"></div><div id="error" class="fail hidden"></div><div id="checks" style="margin-top:12px"></div></div>

<div class="card">
  <div class="row"><div><b>Representative Media Smoke</b><div class="muted">Run in order. Test outputs are isolated under factory/_qa/cross_channel_media.</div></div><div class="spacer"></div></div>
  <div id="mediaButtons">
    <button id="mediaBtn_EN_STORY" type="button" class="media-btn" data-status="NOT_RUN" onclick="runMedia('EN_STORY')"><span class="channel">EN_STORY</span><span class="action">RUN MEDIA SMOKE · NOT RUN</span></button>
    <button id="mediaBtn_EN_BTS" type="button" class="media-btn" data-status="NOT_RUN" onclick="runMedia('EN_BTS')"><span class="channel">EN_BTS</span><span class="action">RUN MEDIA SMOKE · NOT RUN</span></button>
    <button id="mediaBtn_JP_BTS" type="button" class="media-btn" data-status="NOT_RUN" onclick="runMedia('JP_BTS')"><span class="channel">JP_BTS</span><span class="action">RUN MEDIA SMOKE · NOT RUN</span></button>
  </div>
  <div id="mediaProgress" class="muted" style="margin-top:10px"></div><div id="mediaError" class="fail hidden"></div><div id="mediaResults" style="margin-top:12px"></div>
</div>

<div class="card"><b>Channel Matrix</b><div id="matrix" style="margin-top:12px"></div></div>
<div class="card"><b>Next gate</b><div class="muted" style="margin-top:8px">Run media smoke in order: EN_STORY → EN_BTS → JP_BTS. Existing episodes remain pinned and are never used as smoke output targets.</div></div>
</div><script>
const MEDIA=['EN_STORY','EN_BTS','JP_BTS'];
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function jsonFetch(u,opt){const r=await fetch(u,opt||{});const raw=await r.text();let x={};try{x=raw?JSON.parse(raw):{}}catch(e){throw new Error('Invalid JSON response ('+r.status+'): '+raw.slice(0,300))}if(!r.ok||x.ok===false)throw new Error(x.error||x.message||('Request failed: '+r.status));return x}
function setErr(id,msg){const e=document.getElementById(id);if(msg){e.textContent=msg;e.classList.remove('hidden')}else{e.textContent='';e.classList.add('hidden')}}
function renderCore(x){const state=document.getElementById('state');state.className=x.state==='PASS'?'pass':'fail';state.textContent=x.state||'UNKNOWN';document.getElementById('progress').textContent=x.created_at?('Last run: '+x.created_at):'';document.getElementById('checks').innerHTML=(x.checks||[]).map(c=>'<div class="'+(c.status==='PASS'?'pass':'fail')+'">'+(c.status==='PASS'?'✓':'✕')+' <b>'+esc(c.name)+'</b> <span class="muted">'+esc(c.detail||'')+'</span></div>').join('');const rows=Object.entries(x.matrix||{}).map(([cid,d])=>'<tr><td><b>'+esc(cid)+'</b></td><td>'+esc(d.profile_id)+'</td><td>'+esc(d.adapter_id)+'</td><td>'+esc(d.capabilities?.voice?.provider)+'</td><td>'+esc(d.capabilities?.voice?.mode)+'</td><td>'+esc(d.media_binding||'ACTIVE')+'</td></tr>').join('');document.getElementById('matrix').innerHTML='<table><tr><th>Channel</th><th>Profile</th><th>Adapter</th><th>Voice</th><th>Mode</th><th>Media</th></tr>'+rows+'</table>'}
function renderMedia(x){const ch=x.channels||{};MEDIA.forEach(cid=>{const s=ch[cid]?.status||'NOT_RUN';const b=document.getElementById('mediaBtn_'+cid);if(b){b.dataset.status=s;b.querySelector('.action').textContent='RUN MEDIA SMOKE · '+s}});document.getElementById('mediaResults').innerHTML=MEDIA.map(cid=>{const r=ch[cid];if(!r)return '<div class="muted"><b>'+cid+'</b> — NOT RUN</div>';const cls=r.status==='PASS'?'pass':'fail';const checks=(r.checks||[]).map(q=>(q.status==='PASS'?'✓ ':'✕ ')+esc(q.name)+' '+esc(q.detail||'')).join('<br>');return '<div style="margin:12px 0"><b class="'+cls+'">'+cid+' — '+r.status+'</b><div class="muted">'+checks+'</div>'+(r.error?'<div class="fail">'+esc(r.error)+'</div>':'')+'</div>'}).join('')}
async function load(){try{renderCore(await jsonFetch('/api/channel-integration/status',{cache:'no-store'}));setErr('error','')}catch(e){setErr('error','Status load failed: '+e.message)}try{renderMedia(await jsonFetch('/api/channel-media-smoke/status',{cache:'no-store'}));setErr('mediaError','')}catch(e){setErr('mediaError','Media status load failed: '+e.message)}}
async function runqa(){const b=document.getElementById('runBtn'),s=document.getElementById('state');b.disabled=true;s.className='running';s.textContent='RUNNING…';document.getElementById('progress').textContent='Running adapter registry, dispatch and isolation checks…';setErr('error','');try{renderCore(await jsonFetch('/api/channel-integration/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',cache:'no-store'}))}catch(e){s.className='fail';s.textContent='ERROR';setErr('error',e.message)}finally{b.disabled=false}}
async function runMedia(cid){document.getElementById('mediaProgress').textContent='RUNNING '+cid+'…';setErr('mediaError','');document.querySelectorAll('.media-btn').forEach(b=>b.disabled=true);try{const x=await jsonFetch('/api/channel-media-smoke/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:cid}),cache:'no-store'});renderMedia(x);document.getElementById('mediaProgress').textContent='Finished '+cid+'.';renderCore(await jsonFetch('/api/channel-integration/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',cache:'no-store'}))}catch(e){document.getElementById('mediaProgress').textContent='Media smoke failed.';setErr('mediaError',e.message)}finally{document.querySelectorAll('.media-btn').forEach(b=>b.disabled=false)}}
load();
</script></body></html>'''

PROFILE={"schema":"LONGFORM_FACTORY_CHANNEL_PROFILE_MATRIX_v1","version":"1.0","status":"FINAL_LOCK","principles":{"core_must_not_branch_on_channel_for_production_semantics":True,"actual_generated_audio_is_timeline_authority":True,"external_subtitles_default":True,"publishing_package_required":True,"existing_episode_auto_migration":False},"profiles":{"JP_STORY_v1":{"channel_id":"JP_STORY","story_mode":"NARRATION_DRIVEN","voice_provider":"VOICEVOX","voice_cardinality":"SINGLE","casting":"MALE_OR_FEMALE_BY_EPISODE","editing":"STATIC_FIRST_STORY_BEAT","media_status":"ACTIVE_REFERENCE"},"EN_DRAMA_v1":{"channel_id":"EN_STORY","story_mode":"DIALOGUE_DRIVEN","voice_provider":"KOKORO","voice_cardinality":"TWO","casting":"DECLARATIVE_PER_EPISODE; representative smoke fixture uses af_heart + am_liam","editing":"STATIC_FIRST_STORY_BEAT_WITH_SPEAKER_FOCUS","media_status":"PENDING_SMOKE"},"EN_TECH_v1":{"channel_id":"EN_BTS","story_mode":"INFORMATION_FIRST","voice_provider":"KOKORO","voice_cardinality":"SINGLE_DEFAULT","visual_canonical":"BTS_CANONICAL_VISUAL_TEMPLATE_v1_1","editing":"STRUCTURED_VISUAL_RUNS","media_status":"PENDING_SMOKE"},"JP_TECH_v1":{"channel_id":"JP_BTS","story_mode":"INFORMATION_FIRST","voice_provider":"VOICEVOX","voice_cardinality":"TWO_CAPABLE","casting_pairings":["male/female","male/male","female/female"],"editing":"STRUCTURED_VISUAL_RUNS","media_status":"PENDING_SMOKE"}}}

SPEC='''# Longform Factory Cross-Channel Integration Spec v1.0

**Status:** FINAL LOCK
**Authority ID:** `LONGFORM_FACTORY_CROSS_CHANNEL_INTEGRATION_SPEC_v1_0`

Before Core v1 COMPLETE, EN_STORY, EN_BTS, JP_STORY and JP_BTS must operate as isolated channel profiles over one shared Core.

Phase 1:
- All four channels resolve through AdapterManager.
- Channel/profile mismatches fail.
- Core reads declared capabilities instead of embedding channel-specific production semantics.
- Existing Episode manifests are never auto-migrated.
- JP_STORY remains active media reference.
- EN_STORY / EN_BTS / JP_BTS are ACTIVE_CAPABILITY until representative media smoke passes.

Phase 2 media smoke order:
1. EN_STORY — Kokoro two-voice + Speaker Focus + actual-WAV subtitle timing.
2. EN_BTS — Kokoro information-first + BTS visual canonical + actual-WAV subtitle timing.
3. JP_BTS — VOICEVOX multi-voice role mapping + allowed gender pairings + actual-WAV subtitle timing.

No adapter may claim media readiness before its smoke test passes.
'''

MEDIA_SPEC='''# Longform Factory Representative Media Smoke Spec v1.0

Status: ACTIVE CORE GATE

Scope:
- EN_STORY, EN_BTS, JP_BTS representative media integration.
- Never migrates or modifies existing episode manifests or LOCK/FINAL assets.
- All generated fixtures live under factory/_qa/cross_channel_media/.
- Runtime evidence lives under factory/state/cross_channel_media_smoke.json.

PASS requirements:
- Actual configured TTS provider generates WAV.
- Generated WAV duration is timeline authority.
- External SRT is built from actual line WAV durations.
- ffmpeg produces 1920x1080 MP4 and ffprobe verifies A/V duration tolerance.
- EN_STORY validates two Kokoro voices and fixed-frame Speaker Focus semantics.
- EN_BTS validates Kokoro information-first structured visual runs and subtitle-safe layout.
- JP_BTS resolves VOICEVOX speaker/style by names, not hard-coded style IDs, and validates deterministic two-role mapping.

Media readiness is evidence-driven. No channel may report ACTIVE_MEDIA_SMOKE unless its latest stored channel smoke status is PASS.
'''


STATE_SPEC='''# Longform Factory State / Continuity / Reasoning Spec v1.0

Status: ACTIVE CORE GATE

Continuity authority:
- Chat memory is convenience only, never production authority.
- factory/handoff/registry.json points to channel handoff state.
- projects/<CHANNEL>/handoff/CHANNEL_STATE.json and CHANNEL_HANDOFF.md are the stable channel resume surface.
- Episode handoff files are generated only for Factory-managed episode manifests with schema >=1.2. Legacy episodes are not auto-migrated or modified.

Required handoff fields:
AUTHORITY, CURRENT_STAGE, LOCKED_ASSETS, ACTIVE_RULES, OPEN_DECISIONS, KNOWN_FAILURES, NEXT_ACTION, DO_NOT_REOPEN.

Reasoning provider contract:
describe / available / execute_task / result_schema / supports_web.

Core v1 default provider:
manual_handoff. It requires no API key and makes no network call. The Factory prepares a structured task packet; a human can run it in ChatGPT or another reasoning system and paste a schema-valid JSON result back.

Direct API providers may be added later without changing the provider contract.
'''

AUTH={"authority_pointer_version":"1.7","status":"ACTIVE_CANDIDATE","scope":"Longform Factory Shared Core","supersedes":"LONGFORM_FACTORY_ACTIVE_AUTHORITY_v1_6","active_defaults":{"adapter_registry":"LONGFORM_FACTORY_ADAPTER_REGISTRY_v1_6","channel_profile_matrix":"LONGFORM_FACTORY_CHANNEL_PROFILE_MATRIX_v1_0","cross_channel_integration":"LONGFORM_FACTORY_CROSS_CHANNEL_INTEGRATION_SPEC_v1_0"},"channels":{"JP_STORY":{"default_profile":"JP_STORY_v1","adapter":"JP_STORY_REFERENCE_ADAPTER_v1_4","integration":"ACTIVE_MEDIA_REFERENCE"},"EN_STORY":{"default_profile":"EN_DRAMA_v1","adapter":"EN_STORY_REFERENCE_ADAPTER_v1_0","integration":"ACTIVE_CAPABILITY","media":"PENDING_SMOKE"},"EN_BTS":{"default_profile":"EN_TECH_v1","adapter":"EN_BTS_REFERENCE_ADAPTER_v1_0","integration":"ACTIVE_CAPABILITY","media":"PENDING_SMOKE"},"JP_BTS":{"default_profile":"JP_TECH_v1","adapter":"JP_BTS_REFERENCE_ADAPTER_v1_0","integration":"ACTIVE_CAPABILITY","media":"PENDING_SMOKE"}},"application_policy":{"existing_episode_auto_migration":"DISABLED","next_gate":"REPRESENTATIVE_MEDIA_SMOKE_EN_STORY_THEN_EN_BTS_THEN_JP_BTS","core_completion_target":"Idea to Upload Ready across four isolated channel profiles"}}

with zipfile.ZipFile(PREV_PKG) as z:
    cc=z.read("payload/control_center_current.py").decode("utf-8")

# v1.12.1 — single runtime version authority.
cc=cc.replace(
    "from shared_core.update_manager import UpdateManager, UpdateError",
    "from shared_core.update_manager import UpdateManager, UpdateError, UPDATE_API_VERSION",
    1
)
anchor=')).expanduser().resolve()\n\nsys.path.insert(0,str(ROOT/"factory"))'
if anchor not in cc:
    raise RuntimeError("FACTORY_VERSION insertion anchor missing")
cc=cc.replace(
    anchor,
    ')).expanduser().resolve()\n\nFACTORY_VERSION="1.12.1"\n\nsys.path.insert(0,str(ROOT/"factory"))',
    1
)
cc=cc.replace('UPDATES=UpdateManager(ROOT,APP_PATH,"1.9.9")','UPDATES=UpdateManager(ROOT,APP_PATH,FACTORY_VERSION)',1)
cc=cc.replace('"factory_version":"1.9.9"','"factory_version":FACTORY_VERSION',1)
cc=cc.replace(
    'if u.path=="/api/health": self.send_json({"ok":True,"version":"1.9.9","update_api":"1.0","root":str(ROOT)}); return',
    'if u.path=="/api/health": self.send_json({"ok":True,"version":FACTORY_VERSION,"update_api":UPDATE_API_VERSION,"root":str(ROOT)}); return',
    1
)
cc=cc.replace('Control Center v1.9.9 listening','Control Center v{FACTORY_VERSION} listening',1)
cc=cc.replace('<div class="ver">v1.9.9</div>','<div class="ver">v1.12.1</div>',1)

# Cross-channel integration additions; safe when starting from rolled-back 1.9.9.
if "from cross_channel_media_smoke import media_smoke_status, run_media_smoke" not in cc:
    cc=cc.replace("from narrator_ab_lab import NarratorABLab","from narrator_ab_lab import NarratorABLab\nfrom cross_channel_integration import run_cross_channel_qa\nfrom cross_channel_media_smoke import media_smoke_status, run_media_smoke",1)
if "from continuity_bridge import continuity_status, generate_continuity_snapshot, set_active_workstream_hint" not in cc:
    cc=cc.replace("from narrator_ab_lab import NarratorABLab","from narrator_ab_lab import NarratorABLab\nfrom cross_channel_integration import run_cross_channel_qa\nfrom cross_channel_media_smoke import media_smoke_status, run_media_smoke\nfrom continuity_bridge import continuity_status, generate_continuity_snapshot\nfrom reasoning_provider_bridge import status as reasoning_status, execute_task as reasoning_execute_task",1)
if 'onclick="location.href=\'/channel-integration\'"' not in cc:
    cc=cc.replace('<button class="topbtn" onclick="location.href=\'/qa\'">QA Lab</button>','<button class="topbtn" onclick="location.href=\'/qa\'">QA Lab</button><button class="topbtn" onclick="location.href=\'/channel-integration\'">Channels</button>',1)
if 'onclick="location.href=\'/continuity\'"' not in cc:
    cc=cc.replace('<button class="topbtn" onclick="location.href=\'/channel-integration\'">Channels</button>','<button class="topbtn" onclick="location.href=\'/channel-integration\'">Channels</button><button class="topbtn" onclick="location.href=\'/continuity\'">Continuity</button>',1)
if 'u.path=="/channel-integration"' not in cc:
    ga='        if u.path=="/qa":\n'
    gi='        if u.path=="/channel-integration":\n            p=ROOT/"factory"/"channel_integration_page.html"; raw=p.read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw); return\n        if u.path=="/api/channel-integration/status":\n            p=ROOT/"factory"/"state"/"cross_channel_qa.json"\n            if p.exists(): self.send_json(load_json(p,{})); return\n            self.send_json({"state":"NOT_RUN","checks":[],"matrix":{}}); return\n'
    if ga not in cc:
        raise RuntimeError("GET channel-integration anchor missing")
    cc=cc.replace(ga,gi+ga,1)
if 'u.path=="/api/channel-media-smoke/status"' not in cc:
    ga='        if u.path=="/qa":\n'
    gi='        if u.path=="/api/channel-media-smoke/status":\n            self.send_json(media_smoke_status(ROOT)); return\n'
    if ga not in cc: raise RuntimeError("GET media-smoke anchor missing")
    cc=cc.replace(ga,gi+ga,1)

if 'u.path=="/continuity"' not in cc:
    ga='        if u.path=="/qa":\n'
    gi='        if u.path=="/continuity":\n            p=ROOT/"factory"/"continuity_page.html"; raw=p.read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw); return\n        if u.path=="/api/continuity/status":\n            self.send_json(continuity_status(ROOT)); return\n        if u.path=="/api/reasoning/status":\n            self.send_json(reasoning_status(ROOT)); return\n'
    if ga not in cc: raise RuntimeError("continuity GET anchor missing")
    cc=cc.replace(ga,gi+ga,1)

if 'self.path=="/api/channel-integration/run"' not in cc:
    pa='            if self.path=="/api/updates/upload":\n'
    pi='            if self.path=="/api/channel-integration/run":\n                try:\n                    _body=self.read_body()\n                    out=run_cross_channel_qa(ROOT)\n                    self.send_json(out,200); return\n                except Exception as e: self.send_json({"ok":False,"error":"Cross-Channel QA failed: "+str(e)},400); return\n'
    if pa not in cc:
        raise RuntimeError("POST channel-integration anchor missing")
    cc=cc.replace(pa,pi+pa,1)
if 'self.path=="/api/channel-media-smoke/run"' not in cc:
    pa='            if self.path=="/api/updates/upload":\n'
    pi='            if self.path=="/api/channel-media-smoke/run":\n                try:\n                    body=self.read_body()\n                    if isinstance(body,(bytes,bytearray)): body=json.loads(body.decode("utf-8") or "{}")\n                    elif isinstance(body,str): body=json.loads(body or "{}")\n                    out=run_media_smoke(ROOT,(body or {}).get("channel_id"))\n                    self.send_json(out,200); return\n                except Exception as e: self.send_json({"ok":False,"error":"Media smoke failed: "+str(e)},400); return\n'
    if pa not in cc: raise RuntimeError("POST media-smoke anchor missing")
    cc=cc.replace(pa,pi+pa,1)

if 'self.path=="/api/continuity/snapshot"' not in cc:
    pa='            if self.path=="/api/updates/upload":\n'
    pi='            if self.path=="/api/continuity/snapshot":\n                try:\n                    _body=self.read_body()\n                    generate_continuity_snapshot(ROOT); self.send_json(continuity_status(ROOT),200); return\n                except Exception as e: self.send_json({"ok":False,"error":"Continuity snapshot failed: "+str(e)},400); return\n            if self.path=="/api/continuity/active":\n                try:\n                    body=self.read_body()\n                    if isinstance(body,(bytes,bytearray)): body=json.loads(body.decode("utf-8") or "{}")\n                    elif isinstance(body,str): body=json.loads(body or "{}")\n                    set_active_workstream_hint(ROOT,(body or {}).get("channel_id"),(body or {}).get("episode_id"),(body or {}).get("next_action"))\n                    self.send_json(continuity_status(ROOT),200); return\n                except Exception as e: self.send_json({"ok":False,"error":"Active workstream update failed: "+str(e)},400); return\n            if self.path=="/api/reasoning/prepare":\n                try:\n                    body=self.read_body()\n                    if isinstance(body,(bytes,bytearray)): body=json.loads(body.decode("utf-8") or "{}")\n                    elif isinstance(body,str): body=json.loads(body or "{}")\n                    self.send_json(reasoning_execute_task(ROOT,task=body or {}),200); return\n                except Exception as e: self.send_json({"ok":False,"error":"Reasoning prepare failed: "+str(e)},400); return\n            if self.path=="/api/reasoning/complete":\n                try:\n                    body=self.read_body()\n                    if isinstance(body,(bytes,bytearray)): body=json.loads(body.decode("utf-8") or "{}")\n                    elif isinstance(body,str): body=json.loads(body or "{}")\n                    self.send_json(reasoning_execute_task(ROOT,result=(body or {}).get("result"),task_id=(body or {}).get("task_id")),200); return\n                except Exception as e: self.send_json({"ok":False,"error":"Reasoning completion failed: "+str(e)},400); return\n'
    if pa not in cc: raise RuntimeError("continuity POST anchor missing")
    cc=cc.replace(pa,pi+pa,1)


# Regression guards: refuse to build if the old health/version bug remains.
for forbidden in [
    'UpdateManager(ROOT,APP_PATH,"1.9.9")',
    '"factory_version":"1.9.9"',
    '"version":"1.9.9","update_api":"1.0"',
]:
    if forbidden in cc:
        raise RuntimeError("stale version marker remains: "+forbidden)
for required in [
    'FACTORY_VERSION="1.12.1"',
    'UpdateManager(ROOT,APP_PATH,FACTORY_VERSION)',
    '"factory_version":FACTORY_VERSION',
    '"version":FACTORY_VERSION',
    '"update_api":UPDATE_API_VERSION',
]:
    if required not in cc:
        raise RuntimeError("missing runtime version authority: "+required)

files=[]
def add(src,target,text,mode="0644"):
    p=w(src,text)
    files.append((src,target,p,mode))

add("payload/adapters/channels/base_capability_adapter.py","factory/adapters/channels/base_capability_adapter.py",BASE_ADAPTER)
add("payload/adapters/__init__.py","factory/adapters/__init__.py","# Longform Factory adapters package\n")
add("payload/adapters/channels/__init__.py","factory/adapters/channels/__init__.py","# Channel adapters package\n")
add("payload/adapters/channels/en_story/__init__.py","factory/adapters/channels/en_story/__init__.py","")
add("payload/adapters/channels/en_bts/__init__.py","factory/adapters/channels/en_bts/__init__.py","")
add("payload/adapters/channels/jp_bts/__init__.py","factory/adapters/channels/jp_bts/__init__.py","")
for mod,c in CHANNELS.items():
    src=f'from adapters.channels.base_capability_adapter import DeclarativeCapabilityAdapter\n\nclass {c["class"]}(DeclarativeCapabilityAdapter):\n    ADAPTER_ID={c["aid"]!r}\n    CHANNEL_ID={c["cid"]!r}\n    PROFILE_ID={c["profile"]!r}\n    DISPLAY_NAME={c["name"]!r}\n    REQUIRED_RULES={c["rules"]!r}\n    CAPABILITIES={c["caps"]!r}\n'
    add(f"payload/adapters/channels/{mod}/reference_adapter_v10.py",f"factory/adapters/channels/{mod}/reference_adapter_v10.py",src)
add("payload/adapters/adapter_registry.json","factory/adapters/adapter_registry.json",json.dumps(REG,ensure_ascii=False,indent=2)+"\n")
add("payload/canonical/LONGFORM_FACTORY_ADAPTER_REGISTRY_v1_6.json","factory/canonical/LONGFORM_FACTORY_ADAPTER_REGISTRY_v1_6.json",json.dumps(REG,ensure_ascii=False,indent=2)+"\n")
add("payload/canonical/LONGFORM_FACTORY_CHANNEL_PROFILE_MATRIX_v1_0.json","factory/canonical/LONGFORM_FACTORY_CHANNEL_PROFILE_MATRIX_v1_0.json",json.dumps(PROFILE,ensure_ascii=False,indent=2)+"\n")
add("payload/canonical/LONGFORM_FACTORY_CROSS_CHANNEL_INTEGRATION_SPEC_v1_0.md","factory/canonical/LONGFORM_FACTORY_CROSS_CHANNEL_INTEGRATION_SPEC_v1_0.md",SPEC)
add("payload/canonical/LONGFORM_FACTORY_ACTIVE_AUTHORITY_v1_7.json","factory/canonical/LONGFORM_FACTORY_ACTIVE_AUTHORITY_v1_7.json",json.dumps(AUTH,ensure_ascii=False,indent=2)+"\n")
add("payload/cross_channel_integration.py","factory/cross_channel_integration.py",QA)
add("payload/cross_channel_media_smoke.py","factory/cross_channel_media_smoke.py",MEDIA_SMOKE)
add("payload/canonical/LONGFORM_FACTORY_MEDIA_SMOKE_SPEC_v1_0.md","factory/canonical/LONGFORM_FACTORY_MEDIA_SMOKE_SPEC_v1_0.md",MEDIA_SPEC)
add("payload/canonical/LONGFORM_FACTORY_STATE_CONTINUITY_REASONING_SPEC_v1_0.md","factory/canonical/LONGFORM_FACTORY_STATE_CONTINUITY_REASONING_SPEC_v1_0.md",STATE_SPEC)
add("payload/channel_integration_page.html","factory/channel_integration_page.html",PAGE)
add("payload/continuity_bridge.py","factory/continuity_bridge.py",CONTINUITY)
add("payload/reasoning_provider_bridge.py","factory/reasoning_provider_bridge.py",REASONING)
add("payload/continuity_page.html","factory/continuity_page.html",CONT_PAGE)
add("payload/control_center_current.py","factory/control_center_current.py",cc,"0755")

for _,_,p,_ in files:
    if p.suffix==".py": py_compile.compile(str(p),doraise=True)

REPAIR={"schema":"LONGFORM_FACTORY_RUNTIME_REPAIR_v1","version":"1.12.1","purpose":"Add evidence-driven representative media smoke for EN_STORY, EN_BTS and JP_BTS without touching existing episodes.","allowed_start_versions":["1.9.9","1.10.0","1.10.1"],"touch_scope":["factory/"],"forbidden_scope":["projects/","episode_manifest.json"],"expected_channels":["JP_STORY","EN_STORY","EN_BTS","JP_BTS"]}
add("payload/canonical/LONGFORM_FACTORY_RUNTIME_REPAIR_v1_11_0.json","factory/canonical/LONGFORM_FACTORY_RUNTIME_REPAIR_v1_11_0.json",json.dumps(REPAIR,ensure_ascii=False,indent=2)+"\n")

VERSION_QA={"schema":"LONGFORM_FACTORY_RUNTIME_VERSION_QA_v1","factory_version":"1.12.1","health_uses_factory_version":True,"updater_uses_factory_version":True,"overview_uses_factory_version":True,"health_update_api_uses_runtime_constant":True,"stale_1_9_9_health_marker":False}
add("payload/canonical/LONGFORM_FACTORY_RUNTIME_VERSION_QA_v1_11_0.json","factory/canonical/LONGFORM_FACTORY_RUNTIME_VERSION_QA_v1_11_0.json",json.dumps(VERSION_QA,ensure_ascii=False,indent=2)+"\n")

for marker in ["/api/continuity/active","Pin Active Workstream","PINNED_EXTERNAL_WORKSTREAM"]:
    if marker not in cc and marker!="Pin Active Workstream" and marker!="PINNED_EXTERNAL_WORKSTREAM": raise RuntimeError("continuity active route missing")
if "Pin Active Workstream" not in CONT_PAGE: raise RuntimeError("continuity pin UI missing")
if "PINNED_EXTERNAL_WORKSTREAM" not in CONTINUITY: raise RuntimeError("continuity pin state missing")
# v1.12.1 state/continuity/reasoning guards.
for marker in ["AUTHORITY","CURRENT_STAGE","LOCKED_ASSETS","ACTIVE_RULES","OPEN_DECISIONS","KNOWN_FAILURES","NEXT_ACTION","DO_NOT_REOPEN"]:
    if marker not in CONTINUITY: raise RuntimeError("continuity field missing: "+marker)
for marker in ["describe","available","execute_task","result_schema","supports_web","manual_handoff"]:
    if marker not in REASONING: raise RuntimeError("reasoning contract marker missing: "+marker)
for marker in ["/api/continuity/status","/api/continuity/snapshot","/api/reasoning/prepare","/api/reasoning/complete"]:
    if marker not in cc: raise RuntimeError("continuity/reasoning route missing: "+marker)
if "api_key_required\":False" not in REASONING:
    raise RuntimeError("manual reasoning provider must not require API key")
# v1.12.1 regression guards.
for marker in ['id="mediaBtn_EN_STORY"','id="mediaBtn_EN_BTS"','id="mediaBtn_JP_BTS"','RUN MEDIA SMOKE · NOT RUN']:
    if marker not in PAGE:
        raise RuntimeError("static media smoke button missing: "+marker)
for marker in ['RUNNING…','id="runBtn"','Representative Media Smoke','/api/channel-media-smoke/run']:
    if marker not in PAGE:
        raise RuntimeError("channel/media page marker missing: "+marker)
for marker in ['run_media_smoke','media_smoke_status','_body=self.read_body()','/api/channel-media-smoke/run']:
    if marker not in cc:
        raise RuntimeError("control-center media smoke wiring missing: "+marker)
if 'from cross_channel_media_smoke import media_smoke_status, run_media_smoke' not in cc:
    raise RuntimeError("media smoke import missing")
if CHANNELS["en_story"]["caps"]["voice"].get("casting")!="DECLARATIVE_PER_EPISODE":
    raise RuntimeError("EN_STORY casting must remain declarative")
for marker in ['KPipeline','audio_query','synthesis','ffprobe','factory/_qa/cross_channel_media']:
    if marker not in MEDIA_SMOKE and marker not in MEDIA_SPEC:
        raise RuntimeError("media smoke capability missing: "+marker)
if 'style_id":13' in MEDIA_SMOKE or '"speaker":13' in MEDIA_SMOKE:
    raise RuntimeError("hard-coded VOICEVOX style ID is forbidden")

manifest={"schema":"LONGFORM_FACTORY_UPDATE_PACKAGE_v1","package_id":"LONGFORM_FACTORY_CONTINUITY_STATUS_PIN_FIX_1_12_1","version":VERSION,"from_versions":["1.12.0"],"channel":"dev","title":"Continuity Status + Pin Fix","summary":"Normalizes Continuity Snapshot to READY and adds explicit Active Workstream pinning for chats/workstreams that exist before Factory manifests.","server_script":"factory/control_center_current.py","files":[{"source":s,"target":t,"sha256":sha(p),"mode":m} for s,t,p,m in files],"delete":[]}
w("update_manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
w("release_notes.md","# Longform Factory v1.12.1 — Continuity Status + Pin Fix\\n\\nFixes Snapshot UI state reporting and adds explicit Active Workstream pinning for current chat workstreams that do not yet have Factory manifests. Legacy episodes remain untouched.\\n")
OUT.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    z.write(TMP/"update_manifest.json","update_manifest.json")
    for s,_,p,_ in files: z.write(p,s)
    z.write(TMP/"release_notes.md","release_notes.md")

digest=sha(OUT)
feed=json.loads((ROOT/"feed.json").read_text(encoding="utf-8"))
feed["generated_at"]=datetime.now(timezone.utc).isoformat()
feed["channels"]["dev"]={"version":VERSION,"package_url":f"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/{PKG_NAME}","package_sha256":digest,"updater_api_min":"1.1","published_at":datetime.now(timezone.utc).isoformat(),"title":"Continuity Status + Pin Fix","summary":"Fixes Continuity READY state and adds explicit Active Workstream pinning for pre-manifest workstreams."}
(ROOT/"feed.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"version":VERSION,"package":str(OUT),"sha256":digest},indent=2))
