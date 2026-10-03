#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, os, re, shutil, subprocess, sys, threading, time, urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get(
    "LONGFORM_FACTORY_ROOT",
    str(Path.home()/"Desktop"/"KohoroAudition"/"LongformFactory_v1_Production")
)).expanduser().resolve()

sys.path.insert(0,str(ROOT/"factory"))
from shared_core.lifecycle import resolve_lifecycle
from shared_core.manifest_v12 import create_manifest
from shared_core.rule_registry import load_registry as load_rule_registry, verify as verify_rule_registry
from shared_core.adapter_runtime import AdapterManager, AdapterError
from shared_core.artifact_index import ArtifactIndexManager
from shared_core.stage_job_engine import StageJobEngine
from shared_core.update_manager import UpdateManager, UpdateError
from voice_diagnostic import VoiceDiagnosticManager
from narrator_ab_lab import NarratorABLab

CHANNEL_RE = re.compile(r"^(EN_STORY|EN_BTS|JP_STORY|JP_BTS)$")
EP_RE = re.compile(r"^(EN_STORY|EN_BTS|JP_STORY|JP_BTS)_EP\d{3}$")
HEAVY_JOB = "BUILD_PREVIEW"

STATE = ROOT/"factory"/"state"
STATE.mkdir(parents=True, exist_ok=True)
QUEUE_PATH = STATE/"job_queue.json"
EVENTS_PATH = STATE/"events.jsonl"
SERVER_LOG = STATE/"control_center_current.log"
QA_STATUS = STATE/"qa_core_v1_status.json"
QA_LOG = STATE/"qa_core_v1.log"
QA_TIMEOUT_SECONDS = 60
QA_PROC_LOCK = threading.Lock()
QA_PROC = None
LIVE_QA_STATUS = STATE/"qa_live_status.json"
LIVE_QA_LOG = STATE/"qa_live.log"
LIVE_QA_TIMEOUT_SECONDS = 180
LIVE_QA_PROC_LOCK = threading.Lock()
LIVE_QA_PROC = None
QUEUE_LOCK = threading.Lock()
ADAPTERS = AdapterManager(ROOT)
ARTIFACTS = ArtifactIndexManager(ROOT)
JOBS = StageJobEngine(ROOT,ADAPTERS)
APP_PATH=(Path.home()/"Desktop"/"Longform Factory.app").resolve()
UPDATES=UpdateManager(ROOT,APP_PATH,"1.9.9")
VOICE_DIAG=VoiceDiagnosticManager(ROOT)
NARRATOR_AB=NarratorABLab(ROOT)

PHASES = [
  ("DISCOVERY","Discovery",["DISCOVERY"]),
  ("GREENLIGHT","Greenlight",["GREENLIGHT"]),
  ("EDITORIAL","Editorial",["RESEARCH","FACT_LOCK","SCRIPT","SCRIPT_QC"]),
  ("VISUALS","Visuals",["VISUAL_PLAN","VISUAL_BUILD","VISUAL_QC"]),
  ("MEDIA","Media",["VOICE","TIMING","SUBTITLES","EDIT_PLAN","RENDER","AUTO_QC","PREVIEW_REVIEW","FINAL"]),
  ("PUBLISHING","Publishing",["THUMBNAIL","TITLE","DESCRIPTION","TAGS","PUBLISHING_QC","PUBLISHING_REVIEW"]),
  ("UPLOAD","Upload Ready",["UPLOAD_READY"]),
]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def log(msg):
    line=f"{now_iso()} {msg}"
    with SERVER_LOG.open("a",encoding="utf-8") as f:
        f.write(line+"\n")
    print(line,flush=True)

def event(episode_id, kind, message, **extra):
    rec={"ts":now_iso(),"episode_id":episode_id,"kind":kind,"message":message,**extra}
    with EVENTS_PATH.open("a",encoding="utf-8") as f:
        f.write(json.dumps(rec,ensure_ascii=False)+"\n")

def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default

def save_json_atomic(path: Path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def load_registry():
    return load_json(ROOT/"factory"/"canonical"/"channel_registry.runtime.json",{"channels":{}})

def status_norm(v):
    return str(v or "").upper().replace(" ","_")

def locked(v):
    return status_norm(v) in {"LOCK","FINAL_LOCK","FINAL"}

def valid_pair(channel, episode):
    return bool(CHANNEL_RE.fullmatch(channel or "") and EP_RE.fullmatch(episode or "") and episode.startswith(channel+"_EP"))

def episode_dir(channel, episode):
    if not valid_pair(channel,episode):
        raise ValueError("Invalid channel/episode id")
    base=(ROOT/"projects"/channel/"episodes").resolve()
    p=(base/episode).resolve()
    if base not in p.parents:
        raise ValueError("Path escape blocked")
    return p

def latest_file(folder: Path, pattern: str):
    if not folder.exists(): return None
    xs=[p for p in folder.glob(pattern) if p.is_file()]
    return max(xs,key=lambda p:p.stat().st_mtime) if xs else None

def file_rel(p: Path|None, ep: Path):
    if not p: return None
    try: return str(p.relative_to(ep))
    except Exception: return str(p)

def pid_alive(pid):
    try:
        os.kill(int(pid),0); return True
    except Exception: return False

def job_available(channel, manifest=None, ep=None, job_name="BUILD_PREVIEW"):
    try:
        if manifest is None:
            return False
        spec=ADAPTERS.job_spec(Path(ep) if ep else ROOT,manifest,job_name)
        if not spec: return False
        runner=spec.get("runner")
        if runner: return (ROOT/runner).exists()
        command=spec.get("command")
        return isinstance(command,list) and bool(command)
    except Exception:
        return False

def runner_available(channel, manifest=None, ep=None):
    return job_available(channel,manifest,ep,"BUILD_PREVIEW")

def voice_runner_available(channel, manifest=None, ep=None):
    return job_available(channel,manifest,ep,"BUILD_VOICE_ONLY")

def stage_label(sid):
    return sid.replace("_"," ").title()

def phase_summary(lc):
    stages=lc.get("stages",{})
    out=[]
    current=lc.get("current_stage")
    for key,label,ids in PHASES:
        states=[stages.get(x,{}).get("runtime_state","NOT_STARTED") for x in ids]
        if any(x=="FAILED" for x in states): state="fail"
        elif any(x=="BLOCKED" for x in states): state="blocked"
        elif any(x=="NEEDS_REVIEW" for x in states): state="review"
        elif any(x in {"RUNNING","QUEUED"} for x in states): state="running"
        elif states and all(x=="COMPLETE" for x in states): state="done"
        elif current in ids: state="current"
        else: state="todo"
        out.append({"key":key,"label":label,"state":state,"detail":stage_label(current) if current in ids else ""})
    return out

def legacy_lock_summary(m):
    ws=m.get("workstreams",{})
    return {
      "script":m.get("script",{}).get("status") or ws.get("script",{}).get("status") or "DRAFT",
      "visuals":m.get("visuals",{}).get("status") or ws.get("visuals",{}).get("status") or "DRAFT",
    }

def derive_ui_action(channel, ep, m, lc, source, job):
    js=status_norm(job.get("state"))
    if js=="RUNNING":
        return "inspect","View Progress",job.get("message") or "Running",False
    if js=="QUEUED":
        return "inspect","View Queue",job.get("message") or "Queued",False
    if js=="FAILED":
        return "retry","Retry","Build Failed",True

    sid=lc.get("current_stage","DISCOVERY")
    rs=lc.get("stages",{}).get(sid,{}).get("runtime_state","NOT_STARTED")

    if sid=="UPLOAD_READY" and rs=="COMPLETE":
        return "inspect","Ready","Upload Ready",False
    if rs=="FAILED":
        return "retry","Retry",f"{stage_label(sid)} Failed",True
    if rs=="BLOCKED":
        return "open_folder","Inspect",f"{stage_label(sid)} Blocked",True
    if rs=="NEEDS_REVIEW":
        if sid=="PREVIEW_REVIEW" and latest_file(ep/"output"/"preview","*_PREVIEW_v*.mp4"):
            return "open_preview","Review","Preview Ready",True
        return "inspect","Review",f"{stage_label(sid)} Needs Review",True

    media_build={"VOICE","TIMING","SUBTITLES","EDIT_PLAN","RENDER","AUTO_QC"}
    if sid in media_build and runner_available(channel,m,ep):
        return "build_preview","Continue",f"Ready · {stage_label(sid)}",False

    locks=legacy_lock_summary(m)
    if source=="LEGACY_DERIVED" and locked(locks["script"]) and locked(locks["visuals"]) and sid=="VOICE" and runner_available(channel,m,ep):
        return "build_preview","Continue","Ready to Build",False

    return "inspect","Inspect",f"{stage_label(sid)} · Adapter Pending", sid in {"GREENLIGHT","SCRIPT_QC","VISUAL_QC","PUBLISHING_REVIEW"}

def apply_adapter_ui(channel, ep, m, lc, action, label, status, attention):
    adapter_ui=None
    if channel=="JP_STORY" and str(m.get("schema_version"))=="1.2":
        try:
            adapter_ui=ADAPTERS.inspect(ep,m)
        except Exception as e:
            adapter_ui={"active":False,"reason":str(e)}
        if adapter_ui.get("active"):
            stage=adapter_ui.get("stage")
            state=adapter_ui.get("state")
            buttons=adapter_ui.get("buttons") or []
            if stage=="GREENLIGHT" and state=="NEEDS_REVIEW":
                action,label,status,attention="inspect","Review Candidates","Greenlight Review",True
            elif stage=="PREVIEW_REVIEW" and state=="NEEDS_REVIEW":
                action,label,status,attention="open_preview","Review","Preview Ready",True
            elif adapter_ui.get("import_result") and adapter_ui.get("task_exists"):
                action,label,status,attention="inspect","Import Result",f"{stage.replace('_',' ').title()} · AI result needed",True
            else:
                primary=next((b for b in buttons if b.get("primary")),None) or (buttons[0] if buttons else None)
                if primary:
                    a=primary.get("action")
                    if a in {"open_preview","build_preview"}:
                        action=a
                    else:
                        action="adapter:"+a
                    label=primary.get("label","Continue")
                    status=f"{stage.replace('_',' ').title()} · {state.replace('_',' ').title()}"
                    attention=state in {"NEEDS_REVIEW","BLOCKED","FAILED"}
    return action,label,status,attention,adapter_ui

def scan_episode(channel, ep):
    mp=ep/"episode_manifest.json"
    if not mp.exists(): return None
    m=load_json(mp,{})
    if m.get("episode_id",ep.name)!=ep.name or m.get("channel_id")!=channel:
        return None
    lc,lc_source=resolve_lifecycle(ep,m)
    job=JOBS.latest_for_episode(ep,m)
    preview=latest_file(ep/"output"/"preview","*_PREVIEW_v*.mp4")
    final=latest_file(ep/"output"/"final","*.mp4")
    qcfile=latest_file(ep/"output"/"preview","*_QC.json")
    voice_review=latest_file(ep/"output"/"audio_review","*_VOICE_REVIEW_v*.wav")
    voice_qc=latest_file(ep/"output"/"audio_review","*_VOICE_REVIEW_v*_QC.json")
    pubdir=ep/"output"/"publishing"
    srt=latest_file(pubdir,"*.srt")
    buildlog=ep/"output"/"preview"/f"{ep.name}_BUILD.log"
    action,label,status,attention=derive_ui_action(channel,ep,m,lc,lc_source,job)
    action,label,status,attention,adapter_ui=apply_adapter_ui(channel,ep,m,lc,action,label,status,attention)
    try:
        artifact_index=ARTIFACTS.ensure_index(ep,m,ADAPTERS)
        artifact_summary=ARTIFACTS.summary(artifact_index)
        artifact_items=artifact_index.get("items",[])
    except Exception as e:
        artifact_summary={"item_count":0,"active_count":0,"superseded_count":0,"error":str(e)}
        artifact_items=[]
    return {
      "channel_id":channel,
      "episode_id":ep.name,
      "schema_version":str(m.get("schema_version","")),
      "profile":m.get("profile",""),
      "status":status,
      "attention":attention,
      "next_action":action,
      "next_label":label,
      "runner_available":runner_available(channel,m,ep),
      "voice_runner_available":voice_runner_available(channel,m,ep),
      "job":job,
      "lifecycle":lc,
      "lifecycle_source":lc_source,
      "current_stage":lc.get("current_stage"),
      "phases":phase_summary(lc),
      "locks":legacy_lock_summary(m),
      "outputs":{
        "preview":file_rel(preview,ep),
        "final":file_rel(final,ep),
        "qc":file_rel(qcfile,ep),
        "voice_review":file_rel(voice_review,ep),
        "voice_qc":file_rel(voice_qc,ep),
        "srt":file_rel(srt,ep),
        "build_log":file_rel(buildlog if buildlog.exists() else None,ep),
      },
      "authority":m.get("authority",{}),
      "render":m.get("render",{}),
      "qc":m.get("qc",{}),
      "adapter_ui":adapter_ui,
      "artifact_summary":artifact_summary,
      "artifacts":artifact_items,
      "manifest_mtime":mp.stat().st_mtime,
    }

def recent_events(limit=16):
    if not EVENTS_PATH.exists(): return []
    out=[]
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines()[-limit:][::-1]:
        try: out.append(json.loads(line))
        except Exception: pass
    return out

def queue_load():
    with QUEUE_LOCK:
        q=load_json(QUEUE_PATH,[])
        return q if isinstance(q,list) else []

def queue_save(q):
    with QUEUE_LOCK:
        save_json_atomic(QUEUE_PATH,q)

def rule_status():
    regp=ROOT/"factory"/"canonical"/"rule_registry.json"
    reg=load_rule_registry(regp)
    checks=verify_rule_registry(reg,ROOT)
    bad=[x for x in checks if not x["exists"] or not x["hash_match"]]
    return {
      "registry_present":regp.exists(),
      "registered":len(checks),
      "integrity_pass":not bad,
      "failures":bad,
      "active_defaults":reg.get("active_defaults",{}),
    }

def scan_all():
    reg=load_registry()
    eps=[]
    for channel in reg.get("channels",{}):
        if not CHANNEL_RE.fullmatch(channel): continue
        base=ROOT/"projects"/channel/"episodes"
        if not base.exists(): continue
        for ep in sorted(base.iterdir()):
            if ep.is_dir() and EP_RE.fullmatch(ep.name):
                x=scan_episode(channel,ep)
                if x: eps.append(x)
    eps.sort(key=lambda x:x["manifest_mtime"],reverse=True)
    running=[x for x in eps if status_norm(x.get("job",{}).get("state")) in {"RUNNING","DETACHED_RUNNING","CLAIMED"}]
    queued=[x for x in eps if status_norm(x.get("job",{}).get("state")) in {"QUEUED","RETRY_QUEUED"}]
    attention=[x for x in eps if x["attention"] and x not in running and x not in queued]
    return {
      "factory_version":"1.9.9",
      "root":str(ROOT),
      "channels":reg.get("channels",{}),
      "rules":rule_status(),
      "attention":attention,
      "running":running,
      "queued":queued,
      "episodes":eps,
      "events":recent_events(),
      "queue":JOBS.queue_snapshot(),
      "resources":JOBS.resource_snapshot(),
      "timestamp":now_iso(),
    }

def active_heavy_job():
    for e in scan_all()["running"]:
        j=e.get("job",{})
        if j.get("job")==HEAVY_JOB and pid_alive(j.get("pid",0)):
            return e
    return None

def write_queued(ep,position):
    save_json_atomic(ep/"work"/"job_status.json",{
      "episode_id":ep.name,"job":HEAVY_JOB,"state":"QUEUED","stage":"QUEUE",
      "overall_progress":0.0,"queue_position":position,
      "message":f"Waiting in queue · position {position}","updated_at":now_iso()
    })

def preflight(channel,episode):
    ep=episode_dir(channel,episode)
    m=load_json(ep/"episode_manifest.json",{})
    checks=[]
    def add(name,ok,detail="",severity="error"):
        checks.append({"name":name,"pass":bool(ok),"detail":str(detail),"severity":severity})
    add("Manifest",bool(m) and m.get("episode_id")==episode,"Valid" if m else "Missing")
    locks=legacy_lock_summary(m)
    add("Script FINAL LOCK",locked(locks["script"]),locks["script"])
    add("Visual FINAL LOCK",locked(locks["visuals"]),locks["visuals"])
    try:
        apf=ADAPTERS.preflight(ep,m,"RENDER")
        for c in apf.get("checks",[]):
            add("Adapter · "+str(c.get("name","check")),c.get("pass"),c.get("detail",""))
        jspec=ADAPTERS.job_spec(ep,m,"BUILD_PREVIEW")
        if jspec:
            rp=ROOT/jspec["runner"]
            add("Adapter preview runner",rp.exists(),rp)
        else:
            add("Adapter preview runner",False,"BUILD_PREVIEW not supported")
    except Exception as e:
        add("Adapter preflight",False,e)
    add("ffmpeg",bool(shutil.which("ffmpeg")),shutil.which("ffmpeg") or "missing")
    add("ffprobe",bool(shutil.which("ffprobe")),shutil.which("ffprobe") or "missing")
    try:
        free=shutil.disk_usage(ROOT).free
        add("Disk space",free>2*1024**3,f"{free/1024**3:.1f} GB free")
    except Exception: pass
    return {"pass":all(x["pass"] for x in checks if x["severity"]=="error"),"checks":checks}

def enqueue_preview(channel,episode):
    ep=episode_dir(channel,episode)
    m=load_json(ep/"episode_manifest.json",{})
    result=JOBS.enqueue_adapter_job(ep,m,"BUILD_PREVIEW")
    if result.get("ok"):
        event(episode,"QUEUED","BUILD_PREVIEW queued",
              job_id=(result.get("job") or {}).get("job_id"),
              resource_class=(result.get("job") or {}).get("resource_class"))
    return result

def enqueue_voice_only(channel,episode):
    ep=episode_dir(channel,episode)
    m=load_json(ep/"episode_manifest.json",{})
    result=JOBS.enqueue_adapter_job(ep,m,"BUILD_VOICE_ONLY")
    if result.get("ok"):
        event(episode,"QUEUED","BUILD_VOICE_ONLY queued",
              job_id=(result.get("job") or {}).get("job_id"),
              resource_class=(result.get("job") or {}).get("resource_class"))
    return result


def mark_unexpected_failure(ep,rc,log_path):
    js=load_json(ep/"work"/"job_status.json",{})
    if status_norm(js.get("state")) in {"COMPLETE","FAILED"}: return
    js.update({"state":"FAILED","stage":js.get("stage","UNKNOWN"),"message":f"Runner exited with code {rc}","detail":str(log_path),"updated_at":now_iso()})
    save_json_atomic(ep/"work"/"job_status.json",js)
    event(ep.name,"FAILED",f"Runner exited with code {rc}",log=str(log_path))

def _monitor_generic_job(job_id,proc,logf):
    try:
        rc=proc.wait()
    except Exception:
        rc=255
    try: logf.close()
    except Exception: pass
    job=JOBS.finish(job_id,rc)
    if not job: return
    try:
        ep=ROOT/job["episode_path"]
        m_after=load_json(ep/"episode_manifest.json",{})
        ARTIFACTS.ensure_index(ep,m_after,ADAPTERS,force=True)
    except Exception as e:
        log(f"artifact index refresh failed after {job_id}: {e}")
    event(job.get("episode_id",""),"JOB_COMPLETE",
          f"{job.get('job_name')} {job.get('state')}",
          job_id=job_id,exit_code=rc,resource_class=job.get("resource_class"))

def worker_loop():
    JOBS.reconcile()
    while True:
        try:
            JOBS.reconcile()
            started=0
            while True:
                job=JOBS.claim_next()
                if not job: break
                try:
                    proc,logf,started_job=JOBS.start_claimed(job)
                    event(started_job["episode_id"],"JOB_START",
                          f"{started_job['job_name']} started",
                          job_id=started_job["job_id"],pid=proc.pid,
                          resource_class=started_job["resource_class"],
                          attempt=started_job["attempt"])
                    threading.Thread(
                        target=_monitor_generic_job,
                        args=(started_job["job_id"],proc,logf),
                        daemon=True
                    ).start()
                    started+=1
                except Exception as e:
                    failed=JOBS.finish(job["job_id"],127)
                    log(f"job start failed {job.get('job_id')}: {e}")
                    event(job.get("episode_id",""),"JOB_START_FAIL",str(e),job_id=job.get("job_id"))
            time.sleep(.35 if started else .8)
        except Exception as e:
            log(f"generic job worker error: {e}")
            time.sleep(1.5)


def open_path(p):
    p=Path(p)
    if not p.exists(): raise FileNotFoundError(str(p))
    subprocess.Popen(["open",str(p)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def new_episode(body):
    channel=str(body.get("channel_id","")).strip()
    raw=str(body.get("episode_number","")).strip()
    if not CHANNEL_RE.fullmatch(channel): raise ValueError("Invalid channel")
    if not raw.isdigit() or int(raw)<1: raise ValueError("Episode number must be positive")
    n=int(raw); eid=f"{channel}_EP{n:03d}"
    ep=episode_dir(channel,eid)
    if ep.exists(): raise ValueError(f"{eid} already exists")
    reg=load_registry()
    profile=reg["channels"][channel]["default_profile"]
    profile_data=load_json(ROOT/"factory"/"profiles"/f"{profile}.json",{})
    canonical=profile_data.get("canonical_source")
    for sub in [
      "input/discovery","input/research","input/script","input/voice","input/visuals","input/config","input/optional_audio",
      "work/migrations","work/voice","work/timing","work/srt","work/visual_mapping","work/render_cache",
      "output/preview","output/final","output/publishing"
    ]:
        (ep/sub).mkdir(parents=True,exist_ok=True)
    m=create_manifest(channel,n,profile,channel_canonical=canonical)
    default_adapter=ADAPTERS.default_adapter_id(channel)
    if default_adapter:
        m.setdefault("authority",{})["channel_adapter"]=default_adapter
    save_json_atomic(ep/"episode_manifest.json",m)
    try: ARTIFACTS.ensure_index(ep,m,ADAPTERS,force=True)
    except Exception: pass
    event(eid,"CREATED","Episode created with manifest v1.2",profile=profile)
    return {"ok":True,"message":f"{eid} created","episode_id":eid}

def migration_report(channel,episode):
    ep=episode_dir(channel,episode)
    if load_json(ep/"episode_manifest.json",{}).get("schema_version")=="1.2":
        return {"ok":True,"message":"Already manifest v1.2"}
    from shared_core.manifest_v12 import write_migration_report
    r=write_migration_report(ep)
    event(episode,"MIGRATION_REPORT","Manifest v1.2 migration report created")
    return {"ok":True,"message":"Migration report created (not applied)","report":r}

def do_adapter_action(ep: Path, m: dict, action: str, body: dict):
    result=ADAPTERS.invoke_action(ep,m,action,body)
    if result.get("message")=="OPEN_TASK_PATH" and result.get("path"):
        open_path(Path(result["path"]))
        return {"ok":True,"message":"Task Pack opened"}
    return result

def do_action(body):
    channel=body.get("channel_id",""); episode=body.get("episode_id",""); action=body.get("action","")
    ep=episode_dir(channel,episode)
    item=scan_episode(channel,ep)
    if not item: raise ValueError("Episode not found")
    if action=="continue": action=item["next_action"]
    m=load_json(ep/"episode_manifest.json",{})
    if str(action).startswith("adapter:"):
        adapter_action=str(action).split(":",1)[1]
        result=do_adapter_action(ep,m,adapter_action,body)
        if result.get("ok",True):
            try:
                m2=load_json(ep/"episode_manifest.json",m)
                ARTIFACTS.ensure_index(ep,m2,ADAPTERS,force=True)
            except Exception: pass
        event(episode,"ADAPTER_ACTION",result.get("message",adapter_action),action=adapter_action)
        return result
    if action=="build_preview": return enqueue_preview(channel,episode)
    if action=="build_voice_only": return enqueue_voice_only(channel,episode)
    if action=="cancel_job":
        result=JOBS.cancel_latest(ep,m)
        if result.get("ok"):
            event(episode,"JOB_CANCELED",result.get("message","Job canceled"),
                  job_id=(result.get("job") or {}).get("job_id"),
                  job_name=(result.get("job") or {}).get("job_name"))
        return result
    if action=="retry":
        result=JOBS.retry_latest(ep,m)
        if result.get("ok"):
            event(episode,"JOB_RETRY",result.get("message","Retry queued"),
                  job_id=(result.get("job") or {}).get("job_id"),
                  attempt=(result.get("job") or {}).get("attempt"))
        return result
    if action=="open_preview":
        p=latest_file(ep/"output"/"preview","*_PREVIEW_v*.mp4")
        if not p: raise FileNotFoundError("Preview not found")
        open_path(p); return {"ok":True,"message":"Preview opened"}
    if action=="open_voice_review":
        p=latest_file(ep/"output"/"audio_review","*_VOICE_REVIEW_v*.wav")
        if not p: raise FileNotFoundError("Voice Review not found")
        open_path(p); return {"ok":True,"message":"Voice Review opened"}
    if action=="open_voice_qc":
        p=latest_file(ep/"output"/"audio_review","*_VOICE_REVIEW_v*_QC.json")
        if not p: raise FileNotFoundError("Voice QC not found")
        open_path(p); return {"ok":True,"message":"Voice QC opened"}
    if action=="open_final":
        p=latest_file(ep/"output"/"final","*.mp4")
        if not p: raise FileNotFoundError("Final video not found")
        open_path(p); return {"ok":True,"message":"Final opened"}
    if action=="open_folder": open_path(ep); return {"ok":True,"message":"Episode folder opened"}
    if action=="open_log":
        j=JOBS.latest_for_episode(ep,m)
        rel=j.get("log_path") if isinstance(j,dict) else None
        p=(ep/rel) if rel else ep/"output"/"preview"/f"{episode}_BUILD.log"
        open_path(p if p.exists() else SERVER_LOG); return {"ok":True,"message":"Log opened"}
    if action=="open_qc":
        p=latest_file(ep/"output"/"preview","*_QC.json")
        if not p: raise FileNotFoundError("QC report not found")
        open_path(p); return {"ok":True,"message":"QC opened"}
    if action=="open_srt":
        p=latest_file(ep/"output"/"publishing","*.srt")
        if not p: raise FileNotFoundError("SRT not found")
        open_path(p); return {"ok":True,"message":"SRT opened"}
    if action=="open_artifact":
        aid=str(body.get("artifact_id",""))
        item_art=ARTIFACTS.get(ep,m,aid,ADAPTERS)
        if not item_art: raise FileNotFoundError("Artifact not found")
        p=ARTIFACTS.resolve_path(ep,item_art)
        open_path(p)
        return {"ok":True,"message":f"Opened {item_art.get('filename')}"}
    if action=="refresh_artifacts":
        idx=ARTIFACTS.ensure_index(ep,m,ADAPTERS,force=True)
        return {"ok":True,"message":f"Artifact Index refreshed · {idx.get('item_count',0)} items"}
    if action=="migration_report": return migration_report(channel,episode)
    if action=="inspect": return {"ok":True,"message":"Inspect in dashboard"}
    raise ValueError(f"Unknown action: {action}")

def _tail_text(path: Path, max_lines=24, max_chars=6000):
    try:
        lines=path.read_text(encoding="utf-8",errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])[-max_chars:]
    except Exception:
        return ""

def _qa_monitor(proc, started_at):
    global QA_PROC
    try:
        try:
            rc=proc.wait(timeout=QA_TIMEOUT_SECONDS)
            timed_out=False
        except subprocess.TimeoutExpired:
            timed_out=True
            proc.terminate()
            try:
                rc=proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill(); rc=proc.wait()
        st=load_json(QA_STATUS,{})
        if timed_out:
            st.update({
              "state":"FAIL",
              "current":"Acceptance QA timed out",
              "progress":1.0,
              "detail":f"QA exceeded {QA_TIMEOUT_SECONDS}s timeout.",
              "exit_code":rc,
              "finished_at":now_iso(),
              "log_tail":_tail_text(QA_LOG)
            })
            save_json_atomic(QA_STATUS,st)
            event("FACTORY_QA","FAIL","Core v1 acceptance QA timed out",exit_code=rc)
            return

        # The QA runner normally writes PASS/FAIL itself. If it exited without
        # doing so, expose the process result instead of leaving RUNNING forever.
        st=load_json(QA_STATUS,{})
        if st.get("state")=="RUNNING":
            report=load_json(ROOT/"factory"/"_qa"/"reports"/"CORE_V1_ACCEPTANCE_REPORT.json",{})
            if report.get("status") in {"PASS","FAIL"}:
                st["state"]=report["status"]
                st["current"]="Acceptance QA passed" if report["status"]=="PASS" else "Acceptance QA failed"
                st["progress"]=1.0
                st["checks"]=report.get("checks",st.get("checks",[]))
                st["detail"]="Recovered final state from acceptance report."
            elif rc==0:
                st["state"]="FAIL"
                st["current"]="QA exited without final status"
                st["progress"]=1.0
                st["detail"]="Runner returned exit code 0 but did not publish a PASS/FAIL status."
            else:
                st["state"]="FAIL"
                st["current"]="QA process failed"
                st["progress"]=1.0
                st["detail"]=f"Runner exited with code {rc}."
            st["exit_code"]=rc
            st["finished_at"]=now_iso()
            st["log_tail"]=_tail_text(QA_LOG)
            save_json_atomic(QA_STATUS,st)
        event("FACTORY_QA","COMPLETE",f"Core v1 acceptance QA process exited ({rc})",exit_code=rc)
    except Exception as e:
        st=load_json(QA_STATUS,{})
        st.update({
          "state":"FAIL","current":"QA monitor failed","progress":1.0,
          "detail":str(e),"finished_at":now_iso(),"log_tail":_tail_text(QA_LOG)
        })
        save_json_atomic(QA_STATUS,st)
    finally:
        with QA_PROC_LOCK:
            QA_PROC=None

def qa_status():
    d=load_json(QA_STATUS,{})
    if not d:
        return {"state":"IDLE","current":"Not run","progress":0.0,"checks":[],"detail":None,"report":None}
    if d.get("state")=="RUNNING":
        started=d.get("started_epoch")
        if started:
            d["elapsed_seconds"]=round(max(0,time.time()-float(started)),1)
        else:
            d["elapsed_seconds"]=None
    else:
        d["elapsed_seconds"]=d.get("elapsed_seconds")
    if "log_tail" not in d and d.get("state") in {"FAIL","PASS"}:
        d["log_tail"]=_tail_text(QA_LOG)
    return d

def qa_run():
    global QA_PROC
    st=qa_status()
    with QA_PROC_LOCK:
        if QA_PROC is not None and QA_PROC.poll() is None:
            return {"ok":False,"error":"QA is already running"}
    if st.get("state")=="RUNNING":
        # Clear stale legacy RUNNING state from pre-v1.4.1 monitor.
        oldpid=st.get("pid")
        alive=False
        if oldpid:
            try:
                ps=subprocess.check_output(["/bin/ps","-p",str(oldpid),"-o","stat="],text=True,stderr=subprocess.DEVNULL).strip()
                alive=bool(ps and "Z" not in ps.upper())
            except Exception:
                alive=False
        if alive:
            return {"ok":False,"error":"QA is already running"}

    script=ROOT/"factory"/"qa"/"core_v1_acceptance.py"
    if not script.exists():
        return {"ok":False,"error":"QA runner missing"}

    env=os.environ.copy()
    env["LONGFORM_QA_LAUNCHED_BY_GUI"]="1"
    QA_LOG.parent.mkdir(parents=True,exist_ok=True)

    # Critical ordering: publish STARTING before spawning the fast child.
    started_epoch=time.time()
    save_json_atomic(QA_STATUS,{
      "state":"RUNNING",
      "current":"Starting acceptance QA",
      "progress":0.01,
      "checks":[],
      "pid":None,
      "started_at":now_iso(),
      "started_epoch":started_epoch,
      "updated_at":now_iso(),
      "detail":None
    })

    lf=QA_LOG.open("a",encoding="utf-8")
    lf.write(f"\n=== QA RUN {now_iso()} ===\n"); lf.flush()
    try:
        env["PYTHONUTF8"]="1"
        env["PYTHONIOENCODING"]="utf-8"
        proc=subprocess.Popen(
            [sys.executable,str(script),"--root",str(ROOT)],
            stdin=subprocess.DEVNULL,
            stdout=lf,
            stderr=subprocess.STDOUT,
            close_fds=True,
            start_new_session=True,
            env=env
        )
    except Exception as e:
        lf.close()
        st=load_json(QA_STATUS,{})
        st.update({
          "state":"FAIL","current":"Could not start QA","progress":1.0,
          "detail":str(e),"finished_at":now_iso(),"log_tail":_tail_text(QA_LOG)
        })
        save_json_atomic(QA_STATUS,st)
        return {"ok":False,"error":str(e)}

    lf.close()
    with QA_PROC_LOCK:
        QA_PROC=proc

    # Update only the PID; never overwrite child-published progress/checks.
    st2=load_json(QA_STATUS,{})
    if st2.get("state")=="RUNNING":
        st2["pid"]=proc.pid
        st2["updated_at"]=now_iso()
        save_json_atomic(QA_STATUS,st2)

    threading.Thread(target=_qa_monitor,args=(proc,started_epoch),daemon=True).start()
    event("FACTORY_QA","START","Core v1 acceptance QA started",pid=proc.pid)
    return {"ok":True,"message":"Core v1 acceptance QA started","pid":proc.pid}

def qa_reset():
    global QA_PROC
    with QA_PROC_LOCK:
        if QA_PROC is not None and QA_PROC.poll() is None:
            return {"ok":False,"error":"Cannot reset while QA is running"}
    target=ROOT/"factory"/"_qa"/"jp_story_reference"
    if target.exists():
        shutil.rmtree(target)
    if QA_STATUS.exists():
        QA_STATUS.unlink()
    event("FACTORY_QA","RESET","QA fixture reset")
    return {"ok":True,"message":"QA fixture reset"}

def qa_open_report():
    p=ROOT/"factory"/"_qa"/"reports"/"CORE_V1_ACCEPTANCE_REPORT.json"
    if not p.exists():
        return {"ok":False,"error":"QA report not found"}
    open_path(p)
    return {"ok":True,"message":"QA report opened"}

def qa_open_log():
    if not QA_LOG.exists():
        QA_LOG.parent.mkdir(parents=True,exist_ok=True)
        QA_LOG.write_text("No QA log yet.\n",encoding="utf-8")
    open_path(QA_LOG)
    return {"ok":True,"message":"QA log opened"}

def live_qa_status():
    d=load_json(LIVE_QA_STATUS,{})
    if not d:
        return {"state":"IDLE","current":"Not run","progress":0.0,"checks":[],"detail":None,"report":None}
    if d.get("state")=="RUNNING" and d.get("started_epoch"):
        d["elapsed_seconds"]=round(max(0,time.time()-float(d["started_epoch"])),1)
    if d.get("state") in {"PASS","FAIL"} and "log_tail" not in d:
        d["log_tail"]=_tail_text(LIVE_QA_LOG)
    return d

def _live_qa_monitor(proc):
    global LIVE_QA_PROC
    try:
        try:
            rc=proc.wait(timeout=LIVE_QA_TIMEOUT_SECONDS); timed_out=False
        except subprocess.TimeoutExpired:
            timed_out=True; proc.terminate()
            try: rc=proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill(); rc=proc.wait()
        st=load_json(LIVE_QA_STATUS,{})
        if timed_out:
            st.update({
              "state":"FAIL","current":"Live Integration QA timed out","progress":1.0,
              "detail":f"Exceeded {LIVE_QA_TIMEOUT_SECONDS}s timeout.","exit_code":rc,
              "finished_at":now_iso(),"log_tail":_tail_text(LIVE_QA_LOG)
            })
            save_json_atomic(LIVE_QA_STATUS,st)
            return
        st=load_json(LIVE_QA_STATUS,{})
        if st.get("state")=="RUNNING":
            report=load_json(ROOT/"factory"/"_qa"/"reports"/"LIVE_INTEGRATION_REPORT.json",{})
            if report.get("status") in {"PASS","FAIL"}:
                st["state"]=report["status"]
                st["current"]="Live Integration QA passed" if report["status"]=="PASS" else "Live Integration QA failed"
                st["progress"]=1.0; st["checks"]=report.get("checks",st.get("checks",[]))
                st["detail"]="Recovered final state from live integration report."
                if report.get("preview"): st["preview"]=report["preview"]
            else:
                st.update({"state":"FAIL","current":"Live Integration QA process failed","progress":1.0,"detail":f"Runner exited with code {rc}."})
            st["exit_code"]=rc; st["finished_at"]=now_iso(); st["log_tail"]=_tail_text(LIVE_QA_LOG)
            save_json_atomic(LIVE_QA_STATUS,st)
    except Exception as e:
        st=load_json(LIVE_QA_STATUS,{})
        st.update({"state":"FAIL","current":"Live QA monitor failed","progress":1.0,"detail":str(e),"log_tail":_tail_text(LIVE_QA_LOG)})
        save_json_atomic(LIVE_QA_STATUS,st)
    finally:
        with LIVE_QA_PROC_LOCK:
            LIVE_QA_PROC=None

def live_qa_run():
    global LIVE_QA_PROC
    with LIVE_QA_PROC_LOCK:
        if LIVE_QA_PROC is not None and LIVE_QA_PROC.poll() is None:
            return {"ok":False,"error":"Live Integration QA is already running"}
    script=ROOT/"factory"/"qa"/"live_integration.py"
    if not script.exists(): return {"ok":False,"error":"Live Integration QA runner missing"}
    started=time.time()
    save_json_atomic(LIVE_QA_STATUS,{
      "state":"RUNNING","current":"Starting Live Integration QA","progress":0.01,
      "checks":[],"pid":None,"started_at":now_iso(),"started_epoch":started,"updated_at":now_iso()
    })
    env=os.environ.copy(); env["PYTHONUTF8"]="1"; env["PYTHONIOENCODING"]="utf-8"
    LIVE_QA_LOG.parent.mkdir(parents=True,exist_ok=True)
    lf=LIVE_QA_LOG.open("a",encoding="utf-8"); lf.write(f"\n=== LIVE QA RUN {now_iso()} ===\n"); lf.flush()
    try:
        proc=subprocess.Popen(
          [sys.executable,str(script),"--root",str(ROOT)],
          stdin=subprocess.DEVNULL,stdout=lf,stderr=subprocess.STDOUT,
          close_fds=True,start_new_session=True,env=env
        )
    except Exception as e:
        lf.close()
        st=load_json(LIVE_QA_STATUS,{})
        st.update({"state":"FAIL","current":"Could not start Live QA","progress":1.0,"detail":str(e),"log_tail":_tail_text(LIVE_QA_LOG)})
        save_json_atomic(LIVE_QA_STATUS,st)
        return {"ok":False,"error":str(e)}
    lf.close()
    with LIVE_QA_PROC_LOCK: LIVE_QA_PROC=proc
    st=load_json(LIVE_QA_STATUS,{})
    if st.get("state")=="RUNNING":
        st["pid"]=proc.pid; save_json_atomic(LIVE_QA_STATUS,st)
    threading.Thread(target=_live_qa_monitor,args=(proc,),daemon=True).start()
    return {"ok":True,"message":"Live Integration QA started","pid":proc.pid}

def live_qa_reset():
    global LIVE_QA_PROC
    with LIVE_QA_PROC_LOCK:
        if LIVE_QA_PROC is not None and LIVE_QA_PROC.poll() is None:
            return {"ok":False,"error":"Cannot reset while Live QA is running"}
    target=ROOT/"factory"/"_qa"/"live_integration"
    if target.exists(): shutil.rmtree(target)
    if LIVE_QA_STATUS.exists(): LIVE_QA_STATUS.unlink()
    return {"ok":True,"message":"Live Integration QA fixture reset"}

def live_qa_open_report():
    p=ROOT/"factory"/"_qa"/"reports"/"LIVE_INTEGRATION_REPORT.json"
    if not p.exists(): return {"ok":False,"error":"Live Integration report not found"}
    open_path(p); return {"ok":True,"message":"Live Integration report opened"}

def live_qa_open_log():
    if not LIVE_QA_LOG.exists():
        LIVE_QA_LOG.parent.mkdir(parents=True,exist_ok=True)
        LIVE_QA_LOG.write_text("No Live QA log yet.\n",encoding="utf-8")
    open_path(LIVE_QA_LOG); return {"ok":True,"message":"Live QA log opened"}

def live_qa_open_preview():
    st=live_qa_status()
    p=st.get("preview")
    if not p:
        p=load_json(ROOT/"factory"/"_qa"/"reports"/"LIVE_INTEGRATION_REPORT.json",{}).get("preview")
    if not p or not Path(p).exists(): return {"ok":False,"error":"Live QA preview not found"}
    open_path(Path(p)); return {"ok":True,"message":"Live QA preview opened"}

HTML=r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Longform Factory</title><style>
:root{--bg:#f5f6f8;--card:#fff;--ink:#15171a;--muted:#6b7280;--line:#e5e7eb;--accent:#111827;--blue:#2563eb;--green:#138a5b;--red:#c0392b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink)}button,input,select{font:inherit}
header{height:66px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 28px;position:sticky;top:0;z-index:4}.brand{font-size:20px;font-weight:760}.ver{margin-left:9px;color:var(--muted);font-size:12px}.spacer{flex:1}
.search{width:260px;border:1px solid var(--line);border-radius:9px;padding:9px 12px;background:#fafafa}.topbtn{margin-left:9px;border:1px solid var(--line);background:#fff;border-radius:8px;padding:8px 11px;cursor:pointer}.topbtn.primary{background:#111827;color:white;border-color:#111827}
.wrap{max-width:1320px;margin:0 auto;padding:24px 28px 60px}.summary{display:flex;gap:10px;margin-bottom:23px;flex-wrap:wrap}.badge{background:white;border:1px solid var(--line);border-radius:10px;padding:9px 12px}.badge.good{color:var(--green)}.badge.bad{color:var(--red)}
.section{margin-bottom:26px}.section h2{font-size:12px;letter-spacing:.08em;color:var(--muted);margin:0 0 10px;text-transform:uppercase}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px}.card.click{cursor:pointer}.card.click:hover{border-color:#cbd5e1;box-shadow:0 4px 14px rgba(0,0,0,.05)}.row{display:flex;align-items:center;gap:9px}.ep{font-weight:700}.channel{font-size:11px;color:var(--muted);background:#f1f5f9;padding:3px 6px;border-radius:5px}.status{margin-top:8px;color:#374151}
.action{border:0;background:var(--accent);color:#fff;border-radius:8px;padding:8px 12px;cursor:pointer;font-weight:650}.action.secondary{background:#fff;color:var(--ink);border:1px solid var(--line)}
.bar{height:7px;background:#e5e7eb;border-radius:9px;overflow:hidden;margin:12px 0 7px}.fill{height:100%;background:var(--blue);transition:width .35s}.tiny{font-size:12px;color:var(--muted)}
.table{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}.tr{display:grid;grid-template-columns:150px 135px 1fr 170px 90px;gap:10px;align-items:center;padding:12px 14px;border-top:1px solid var(--line);cursor:pointer}.tr:first-child{border-top:0}.tr:hover{background:#fafafa}.pill{display:inline-block;padding:3px 7px;border-radius:999px;font-size:11px;background:#eef2ff;color:#3730a3}.empty{padding:22px;color:var(--muted);background:#fff;border:1px dashed #d1d5db;border-radius:12px}
.drawer{position:fixed;right:-540px;top:0;width:520px;height:100vh;background:#fff;z-index:10;box-shadow:-10px 0 35px rgba(0,0,0,.13);transition:right .22s;overflow:auto}.drawer.open{right:0}.drawerHead{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);padding:18px 20px;z-index:2}.drawerBody{padding:18px 20px 44px}.close{float:right;border:0;background:#f3f4f6;border-radius:7px;padding:6px 9px;cursor:pointer}.bigstatus{font-size:20px;font-weight:750;margin:4px 0 2px}
.phase{display:flex;align-items:center;justify-content:space-between;padding:9px 0;border-bottom:1px solid #f0f1f2}.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:8px;background:#cbd5e1}.dot.done{background:var(--green)}.dot.fail,.dot.blocked{background:var(--red)}.dot.review,.dot.current,.dot.running{background:var(--blue)}
.outbuttons{display:flex;gap:7px;flex-wrap:wrap}.details{margin-top:20px;padding-top:14px;border-top:1px solid var(--line)}details summary{cursor:pointer;color:var(--muted)}pre{white-space:pre-wrap;background:#f8fafc;border:1px solid var(--line);border-radius:8px;padding:10px;font-size:11px}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#111827;color:#fff;border-radius:9px;padding:10px 14px;z-index:30;opacity:0;pointer-events:none;transition:opacity .2s}.toast.show{opacity:1}.event{padding:7px 0;border-bottom:1px solid #f2f2f2}
.modalbg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.28);z-index:20;align-items:center;justify-content:center}.modalbg.open{display:flex}.modal{width:400px;background:#fff;border-radius:14px;padding:20px;box-shadow:0 20px 70px rgba(0,0,0,.25)}.field{margin:12px 0}.field label{display:block;font-size:12px;color:var(--muted);margin-bottom:5px}.field input,.field select{width:100%;padding:9px;border:1px solid var(--line);border-radius:8px}
.artifactbox{margin-top:18px;padding:14px;border:1px solid var(--line);border-radius:10px;background:#fff}.artifacthead{display:flex;align-items:center;gap:8px}.artifactlist{margin-top:10px}.artifactrow{display:grid;grid-template-columns:1fr auto;gap:8px;padding:9px 0;border-top:1px solid #eef0f2}.artifactrow:first-child{border-top:0}.artifactname{font-weight:650;word-break:break-all}.artifactmeta{font-size:11px;color:var(--muted);margin-top:3px}.artstatus{display:inline-block;padding:2px 6px;border-radius:999px;background:#f1f5f9;margin-left:5px}.artifactbox details{margin-top:8px}.adapterbox{margin-top:18px;padding:14px;border:1px solid var(--line);border-radius:10px;background:#fafafa}.candidate{padding:10px 0;border-top:1px solid var(--line)}.candidate:first-child{border-top:0}.importbox{margin-top:10px;padding:10px;background:#fff;border:1px dashed #cbd5e1;border-radius:8px}.importbox textarea{width:100%;min-height:120px;border:1px solid var(--line);border-radius:7px;padding:8px;font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
@media(max-width:800px){.tr{grid-template-columns:1fr 1fr}.tr>*:nth-child(n+3){grid-column:1/-1}.drawer{width:100%}.search{width:150px}}
</style></head><body>
<header><div class="brand">Longform Factory</div><div class="ver">v1.9.9</div><div class="spacer"></div><input id="search" class="search" placeholder="Search episodes…  ⌘K"><button class="topbtn" onclick="location.href='/qa'">QA Lab</button><button class="topbtn primary" onclick="openNew()">+ New Episode</button><button class="topbtn" onclick="location.href='/voice-diagnostic'">Voice Diagnostic</button><button class="topbtn" onclick="location.href='/narrator-ab'">Narrator A/B</button><button class="topbtn" onclick="location.href='/updates'">Updates</button><button class="topbtn" onclick="refresh()">Refresh</button></header>
<div class="wrap">
<div class="summary"><div id="rulesBadge" class="badge">Rules…</div><div id="episodeBadge" class="badge">Episodes…</div></div>
<section class="section"><h2>Needs Your Attention</h2><div id="attention" class="grid"></div></section>
<section class="section"><h2>Running</h2><div id="running" class="grid"></div></section>
<section class="section"><h2>Queue</h2><div id="queued" class="grid"></div></section>
<section class="section"><h2>All Episodes</h2><div id="episodes" class="table"></div></section>
<section class="section"><h2>Recent Events</h2><div id="events" class="card"></div></section></div>
<aside id="drawer" class="drawer"><div class="drawerHead"><button class="close" onclick="closeDrawer()">Close</button><div id="dchannel" class="tiny"></div><div id="did" class="ep"></div></div><div id="dbody" class="drawerBody"></div></aside>
<div id="newbg" class="modalbg"><div class="modal"><h3>New Episode</h3><div class="field"><label>Channel</label><select id="newchannel"></select></div><div class="field"><label>Episode number</label><input id="newnum" type="number" min="1" placeholder="3"></div><div class="row"><button class="action" onclick="createEpisode()">Create</button><button class="action secondary" onclick="closeNew()">Cancel</button></div><div class="tiny" style="margin-top:12px">New episodes use Manifest Schema v1.2. Existing episodes are not migrated.</div></div></div>
<div id="toast" class="toast"></div>
<script>
let data=null,selected=null;
const uiState={artifactOpen:{},technicalOpen:{}};
function uiKey(ep,section){return `${ep}::${section}`}
function captureInspectorState(){
  if(!selected)return;
  document.querySelectorAll('#dbody .artifactbox details[data-state-key]').forEach(d=>{
    uiState.artifactOpen[d.getAttribute('data-state-key')]=d.open;
  });
  document.querySelectorAll('#dbody .details details[data-state-key]').forEach(d=>{
    uiState.technicalOpen[d.getAttribute('data-state-key')]=d.open;
  });
}
function applyInspectorState(){
  if(!selected)return;
  document.querySelectorAll('#dbody .artifactbox details[data-state-key]').forEach(d=>{
    const k=d.getAttribute('data-state-key');
    if(Object.prototype.hasOwnProperty.call(uiState.artifactOpen,k))d.open=!!uiState.artifactOpen[k];
    d.addEventListener('toggle',()=>{uiState.artifactOpen[k]=d.open});
  });
  document.querySelectorAll('#dbody .details details[data-state-key]').forEach(d=>{
    const k=d.getAttribute('data-state-key');
    if(Object.prototype.hasOwnProperty.call(uiState.technicalOpen,k))d.open=!!uiState.technicalOpen[k];
    d.addEventListener('toggle',()=>{uiState.technicalOpen[k]=d.open});
  });
}
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const pct=j=>Math.round(100*Number(j?.overall_progress||0));
function toast(m){let t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2400)}
function card(e,kind){let j=e.job||{},run=['RUNNING','QUEUED'].includes(String(j.state||'').toUpperCase());return `<div class="card click" onclick="inspect('${e.channel_id}','${e.episode_id}')"><div class="row"><span class="ep">${esc(e.episode_id)}</span><span class="channel">${esc(e.channel_id)}</span><span class="spacer"></span>${kind==='attention'?`<button class="action" onclick="event.stopPropagation();doAction('${e.channel_id}','${e.episode_id}','continue')">${esc(e.next_label)}</button>`:''}</div><div class="status">${esc(e.status)}</div><div class="tiny">${esc(e.current_stage||'')} · manifest ${esc(e.schema_version)}</div>${run?`<div class="bar"><div class="fill" style="width:${pct(j)}%"></div></div><div class="tiny">${esc(j.resource_class||'')} · attempt ${esc(j.attempt||1)} · ${esc(j.stage||'')} · ${esc(j.message||'')} ${j.item_total?` · ${j.item_current||0}/${j.item_total}`:''}</div>`:''}</div>`}
function render(){let q=document.getElementById('search').value.trim().toLowerCase(),f=e=>!q||[e.episode_id,e.channel_id,e.status,e.current_stage].join(' ').toLowerCase().includes(q);let att=data.attention.filter(f),run=data.running.filter(f),que=data.queued.filter(f),eps=data.episodes.filter(f);document.getElementById('attention').innerHTML=att.length?att.map(e=>card(e,'attention')).join(''):'<div class="empty">Nothing needs your attention.</div>';document.getElementById('running').innerHTML=run.length?run.map(e=>card(e,'run')).join(''):'<div class="empty">No active jobs.</div>';document.getElementById('queued').innerHTML=que.length?que.map(e=>card(e,'queue')).join(''):'<div class="empty">Queue is empty.</div>';document.getElementById('episodes').innerHTML=eps.length?eps.map(e=>`<div class="tr" onclick="inspect('${e.channel_id}','${e.episode_id}')"><div><b>${esc(e.episode_id)}</b></div><div><span class="pill">${esc(e.profile)}</span></div><div>${esc(e.status)}</div><div class="tiny">${esc(e.current_stage)} · ${esc(e.lifecycle_source)}</div><div>${e.job?.state==='RUNNING'?pct(e.job)+'%':''}</div></div>`).join(''):'<div class="empty">No episodes.</div>';document.getElementById('events').innerHTML=data.events.length?data.events.map(x=>`<div class="event"><b>${esc(x.episode_id||'Factory')}</b> · ${esc(x.message||x.kind)}<div class="tiny">${esc(x.ts||'')}</div></div>`).join(''):'<div class="tiny">No recent events.</div>';let rb=document.getElementById('rulesBadge');rb.className='badge '+(data.rules.integrity_pass?'good':'bad');rb.textContent=data.rules.integrity_pass?`Rules ✓ ${data.rules.registered} verified`:`Rules issue · ${data.rules.failures.length}`;document.getElementById('episodeBadge').textContent=`${data.episodes.length} Episodes`;if(selected){captureInspectorState();let e=data.episodes.find(x=>x.episode_id===selected);if(e)drawInspector(e)}}
async function refresh(){try{data=await (await fetch('/api/dashboard')).json();render();fillChannels()}catch(e){toast('Dashboard refresh failed')}}
function inspect(c,id){selected=id;let e=data.episodes.find(x=>x.channel_id===c&&x.episode_id===id);if(!e)return;document.getElementById('drawer').classList.add('open');drawInspector(e)}function closeDrawer(){document.getElementById('drawer').classList.remove('open');selected=null}
function adapterHtml(e){
  let a=e.adapter_ui;if(!a||!a.active)return '';
  let buttons=(a.buttons||[]).map(b=>{
    if(b.action==='copy_prompt')return `<button class="action ${b.primary?'':'secondary'}" onclick="adapterPrompt('${e.channel_id}','${e.episode_id}',true)">${esc(b.label)}</button>`;
    return `<button class="action ${b.primary?'':'secondary'}" onclick="doAction('${e.channel_id}','${e.episode_id}','adapter:${b.action}')">${esc(b.label)}</button>`;
  }).join('');
  let candidates=(a.candidates||[]).map(c=>`<div class="candidate"><b>${esc(c.candidate_id)}</b><div style="margin:4px 0 7px">${esc(c.premise||'')}</div><div class="tiny">${esc(c.content_gate||'')} · duplicate ${esc(c.duplicate_status||'')} · fit ${esc(c.channel_fit||'')}</div><div style="margin-top:7px"><button class="action" onclick="adapterGreenlight('${e.channel_id}','${e.episode_id}','${esc(c.candidate_id)}','GREENLIGHT')">Greenlight</button> <button class="action secondary" onclick="adapterGreenlight('${e.channel_id}','${e.episode_id}','${esc(c.candidate_id)}','REWORK')">Rework</button> <button class="action secondary" onclick="adapterGreenlight('${e.channel_id}','${e.episode_id}','${esc(c.candidate_id)}','DROP')">Drop</button></div></div>`).join('');
  let imp=a.import_result?`<div class="importbox"><div class="tiny">AI result JSON</div><textarea id="resultbox" placeholder="Paste RESULT.json here"></textarea><div style="margin-top:7px"><button class="action" onclick="adapterImport('${e.channel_id}','${e.episode_id}')">Import Result</button> <button class="action secondary" onclick="adapterPrompt('${e.channel_id}','${e.episode_id}',false)">View Prompt</button></div></div>`:'';
  let review='';
  if(a.review){
    if(a.review.type==='SCRIPT')review=`<details style="margin-top:10px" open><summary>Script Review</summary><div class="tiny">QC ${esc(a.review.qc_status||'')} · issues ${(a.review.issues||[]).length}</div><pre>${esc(a.review.script_text||'')}</pre></details>`;
    if(a.review.type==='VISUAL')review=`<details style="margin-top:10px" open><summary>Visual Review</summary><div class="tiny">${a.review.visual_count||0} visuals · ${a.review.run_count||0} runs · static ratio ${a.review.static_ratio==null?'—':Math.round(a.review.static_ratio*100)+'%'}</div><pre>${esc(JSON.stringify({reveal_checks:a.review.reveal_checks,missing:a.review.missing},null,2))}</pre></details>`;
    if(a.review.type==='PREVIEW')review=`<details style="margin-top:10px" open><summary>Preview QC</summary><pre>${esc(JSON.stringify(a.review.qc||{},null,2))}</pre></details>`;
    if(a.review.type==='PUBLISHING')review=`<details style="margin-top:10px" open><summary>Publishing Review</summary><b>${esc(a.review.title||'')}</b><div style="margin:8px 0">${esc(a.review.description||'')}</div><div class="tiny">${esc(a.review.tags||'')}</div><pre>${esc(JSON.stringify(a.review.qc||{},null,2))}</pre></details>`;
  }
  return `<div class="adapterbox"><b>Channel Adapter</b><div class="tiny">${esc(a.adapter_id)} · ${esc(a.stage)} · ${esc(a.state)} · provider: handoff</div><div class="outbuttons" style="margin-top:10px">${buttons}</div>${candidates}${imp}${review}</div>`;
}

function fmtBytes(n){n=Number(n||0);if(n<1024)return n+' B';if(n<1024*1024)return (n/1024).toFixed(1)+' KB';if(n<1024*1024*1024)return (n/1024/1024).toFixed(1)+' MB';return (n/1024/1024/1024).toFixed(2)+' GB'}
function artifactHtml(e){
  let xs=e.artifacts||[],s=e.artifact_summary||{};
  if(!xs.length)return `<div class="artifactbox"><div class="artifacthead"><b>Artifacts</b><span class="spacer"></span><button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','refresh_artifacts')">Refresh Index</button></div><div class="tiny" style="margin-top:8px">No indexed artifacts yet.</div></div>`;
  let stages={};xs.forEach(a=>(stages[a.stage]||(stages[a.stage]=[])).push(a));
  let groups=Object.keys(stages).sort().map(stage=>{
    let rows=stages[stage].map(a=>`<div class="artifactrow"><div><div class="artifactname">${esc(a.filename)} <span class="artstatus">${esc(a.status)}</span></div><div class="artifactmeta">${esc(a.kind)} · ${fmtBytes(a.bytes)} · SHA ${esc((a.sha256||'').slice(0,10))}${a.active?'':' · inactive'}</div></div><div><button class="action secondary" onclick="doArtifact(event,'${e.channel_id}','${e.episode_id}','${a.artifact_id}')">Open</button></div></div>`).join('');
    let k=`${e.episode_id}::artifact::${stage}`;
    let defaultOpen=stage===e.current_stage||stage==='FINAL';
    let openAttr=(Object.prototype.hasOwnProperty.call(uiState.artifactOpen,k)?uiState.artifactOpen[k]:defaultOpen)?'open':'';
    return `<details data-state-key="${esc(k)}" ${openAttr}><summary><b>${esc(stage)}</b> · ${stages[stage].length}</summary><div class="artifactlist">${rows}</div></details>`;
  }).join('');
  return `<div class="artifactbox"><div class="artifacthead"><b>Artifact Browser</b><span class="tiny">${s.item_count||0} items · ${s.active_count||0} active · ${s.superseded_count||0} superseded</span><span class="spacer"></span><button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','refresh_artifacts')">Refresh Index</button></div>${groups}</div>`;
}
async function doArtifact(ev,c,id,aid){ev.stopPropagation();try{let r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:c,episode_id:id,action:'open_artifact',artifact_id:aid})});let x=await r.json();if(!r.ok||!x.ok)throw new Error(x.error||'Open failed');toast(x.message)}catch(e){toast(e.message)}}
function drawInspector(e){document.getElementById('dchannel').textContent=e.channel_id+' · '+e.profile+' · manifest '+e.schema_version;document.getElementById('did').textContent=e.episode_id;let j=e.job||{},isrun=['RUNNING','QUEUED','RETRY_QUEUED','CLAIMED','DETACHED_RUNNING'].includes(j.state);let phases=e.phases.map(p=>`<div class="phase"><div><span class="dot ${p.state}"></span>${esc(p.label)}</div><div class="tiny">${esc(p.detail||p.state)}</div></div>`).join('');let progress=isrun?`<div class="bar"><div class="fill" style="width:${pct(j)}%"></div></div><div class="tiny">${pct(j)}% · ${esc(j.resource_class||'')} · attempt ${esc(j.attempt||1)} · ${esc(j.stage||'')} · ${esc(j.message||'')}${j.item_total?` · ${j.item_current||0}/${j.item_total}`:''}${j.cache_hits!=null?` · cache ${j.cache_hits}`:''}</div>`:'';let btn=e.next_action==='inspect'?`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','open_folder')">Open Episode</button>`:`<button class="action" onclick="doAction('${e.channel_id}','${e.episode_id}','continue')">${esc(e.next_label)}</button>`;let outs=`<div class="outbuttons">${e.outputs.preview?`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','open_preview')">Preview</button>`:''}${e.outputs.voice_review?`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','open_voice_review')">Voice Review</button>`:''}${e.outputs.voice_qc?`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','open_voice_qc')">Voice QC</button>`:''}${e.voice_runner_available&&!isrun?`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','build_voice_only')">Rebuild Voice Only</button>`:''}${e.runner_available&&e.outputs.preview&&!isrun?`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','build_preview')">Rebuild Preview</button>`:''}${isrun?`<button class="action secondary" onclick="if(confirm('Cancel the current job?'))doAction('${e.channel_id}','${e.episode_id}','cancel_job')">Cancel Job</button>`:''}${e.outputs.final?`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','open_final')">Final</button>`:''}${e.outputs.srt?`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','open_srt')">SRT</button>`:''}${e.outputs.qc?`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','open_qc')">QC</button>`:''}<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','open_folder')">Folder</button><button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','open_log')">Log</button></div>`;let migrate=e.schema_version==='1.2'?'':`<button class="action secondary" onclick="doAction('${e.channel_id}','${e.episode_id}','migration_report')">Prepare v1.2 Migration Report</button>`;document.getElementById('dbody').innerHTML=`<div class="bigstatus">${esc(e.status)}</div><div class="tiny">Current stage · ${esc(e.current_stage)} · ${esc(e.lifecycle_source)}</div><div style="margin:14px 0" class="row">${btn}</div>${progress}${adapterHtml(e)}${artifactHtml(e)}<h3>Lifecycle</h3>${phases}<h3>Outputs</h3>${outs}${migrate?`<div style="margin-top:15px">${migrate}</div>`:''}<div class="details"><details data-state-key="${esc(e.episode_id+'::technical')}"><summary>Authority / technical details</summary><pre>${esc(JSON.stringify({authority:e.authority,locks:e.locks,lifecycle:e.lifecycle,job:e.job,adapter:e.adapter_ui},null,2))}</pre></details></div>`;applyInspectorState()}
async function adapterPrompt(c,id,copy){try{let r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:c,episode_id:id,action:'adapter:get_prompt'})});let x=await r.json();if(!r.ok||!x.ok)throw new Error(x.error||'Prompt unavailable');if(copy){await navigator.clipboard.writeText(x.prompt_text);toast('Task prompt copied')}else{alert(x.prompt_text)}}catch(e){toast(e.message)}}
async function adapterImport(c,id){let el=document.getElementById('resultbox'),txt=el?el.value.trim():'';if(!txt){toast('Paste RESULT.json first');return}try{JSON.parse(txt)}catch(e){toast('Invalid JSON');return}try{let r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:c,episode_id:id,action:'adapter:import_result',result:txt})});let x=await r.json();if(!r.ok||!x.ok)throw new Error(x.error||'Import failed');toast(x.message||'Imported');setTimeout(refresh,250)}catch(e){toast(e.message)}}
async function adapterGreenlight(c,id,candidate,decision){try{let r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:c,episode_id:id,action:'adapter:greenlight',candidate_id:candidate,decision:decision})});let x=await r.json();if(!r.ok||!x.ok)throw new Error(x.error||'Decision failed');toast(x.message);setTimeout(refresh,250)}catch(e){toast(e.message)}}
async function doAction(c,id,a){try{let r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:c,episode_id:id,action:a})});let x=await r.json();if(!r.ok||x.ok===false){toast(x.error||'Action failed');if(x.preflight)alert('Preflight failed:\n'+x.preflight.checks.filter(y=>!y.pass).map(y=>'• '+y.name+': '+y.detail).join('\n'))}else toast(x.message||'Done');setTimeout(refresh,350)}catch(e){toast('Action failed')}}
function fillChannels(){let s=document.getElementById('newchannel');if(s.options.length||!data)return;Object.keys(data.channels).forEach(c=>{let o=document.createElement('option');o.value=c;o.textContent=c;s.appendChild(o)})}
function openNew(){document.getElementById('newbg').classList.add('open');fillChannels();document.getElementById('newnum').focus()}function closeNew(){document.getElementById('newbg').classList.remove('open')}
async function createEpisode(){let c=document.getElementById('newchannel').value,n=document.getElementById('newnum').value;try{let r=await fetch('/api/new_episode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:c,episode_number:n})});let x=await r.json();if(!r.ok||!x.ok)throw new Error(x.error||'Create failed');toast(x.message);closeNew();document.getElementById('newnum').value='';setTimeout(refresh,300)}catch(e){toast(e.message)}}
document.getElementById('search').addEventListener('input',render);document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();document.getElementById('search').focus()}});refresh();setInterval(refresh,1000);
</script></body></html>'''

QA_HTML=r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Longform Factory QA Lab</title>
<style>body{margin:0;background:#f5f6f8;font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#15171a}.wrap{max-width:900px;margin:0 auto;padding:30px}.card{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:20px;margin-bottom:14px}.row{display:flex;gap:10px;align-items:center}.spacer{flex:1}.btn{border:1px solid #d1d5db;background:#fff;border-radius:8px;padding:9px 12px;cursor:pointer}.btn.primary{background:#111827;color:#fff;border-color:#111827}.bar{height:9px;background:#e5e7eb;border-radius:9px;overflow:hidden;margin:14px 0}.fill{height:100%;background:#2563eb}.muted{color:#6b7280}.check{padding:8px 0;border-top:1px solid #f0f1f2}.pass{color:#138a5b}.fail{color:#c0392b}</style></head><body><div class="wrap">
<div class="row"><h1>Core v1 QA Lab</h1><div class="spacer"></div><button class="btn" onclick="location.href='/qa/live'">Level 2: Live Integration</button><button class="btn" onclick="location.href='/'">Back to Dashboard</button></div>
<div class="card"><div class="row"><div><b id="state">IDLE</b><div id="current" class="muted">Not run</div></div><div class="spacer"></div><button class="btn primary" onclick="runQa()">Run Core QA</button><button class="btn" onclick="openReport()">Open Report</button><button class="btn" onclick="openLog()">Open QA Log</button><button class="btn" onclick="resetQa()">Reset Fixture</button></div><div class="bar"><div id="fill" class="fill" style="width:0%"></div></div><div id="detail" class="muted"></div><div id="elapsed" class="muted" style="margin-top:6px"></div><pre id="logtail" style="white-space:pre-wrap;background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:10px;display:none"></pre></div>
<div class="card"><b>Acceptance Checks</b><div id="checks" style="margin-top:12px"></div></div>
<div class="card muted">QA uses only <code>factory/_qa/</code>. It does not create a real Episode. External AI/TTS/render quality is simulated here; production media quality remains a separate Preview Review responsibility.</div>
</div><script>
async function refresh(){let s=await (await fetch('/api/qa/status')).json();document.getElementById('state').textContent=s.state||'IDLE';document.getElementById('current').textContent=s.current||'';document.getElementById('detail').textContent=s.detail||'';document.getElementById('elapsed').textContent=s.state==='RUNNING'&&s.elapsed_seconds!=null?`Elapsed ${s.elapsed_seconds}s · timeout 60s`:'';document.getElementById('fill').style.width=Math.round(100*(s.progress||0))+'%';document.getElementById('checks').innerHTML=(s.checks||[]).map(x=>`<div class="check ${x.status==='PASS'?'pass':'fail'}">${x.status==='PASS'?'✓':'✕'} <b>${x.name}</b><div class="muted">${x.detail||''}</div></div>`).join('')||'<div class="muted">No checks yet.</div>';let lt=document.getElementById('logtail');if(s.log_tail&&s.state==='FAIL'){lt.style.display='block';lt.textContent=s.log_tail}else{lt.style.display='none';lt.textContent=''}}
async function post(url){let r=await fetch(url,{method:'POST'}),x=await r.json();if(!r.ok||x.ok===false)alert(x.error||'Failed');refresh()}
function runQa(){post('/api/qa/run')}function resetQa(){post('/api/qa/reset')}function openReport(){post('/api/qa/open_report')}function openLog(){post('/api/qa/open_log')}
refresh();setInterval(refresh,700);
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): return
    def send_json(self,obj,status=200):
        raw=json.dumps(obj,ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw)
    def read_body(self):
        n=int(self.headers.get("Content-Length","0"))
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
    def do_GET(self):
        u=urllib.parse.urlparse(self.path)
        if u.path=="/":
            raw=HTML.encode("utf-8"); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw); return
        if u.path=="/qa":
            raw=QA_HTML.encode("utf-8"); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw); return
        if u.path=="/qa/live":
            page=ROOT/"factory"/"qa"/"live_qa_page.html"
            if not page.exists(): self.send_json({"error":"live qa page missing"},404); return
            raw=page.read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw); return
        if u.path=="/api/qa/live/status": self.send_json(live_qa_status()); return
        if u.path=="/api/health": self.send_json({"ok":True,"version":"1.9.9","update_api":"1.0","root":str(ROOT)}); return
        if u.path=="/updates":
            p=ROOT/"factory"/"update"/"update_page.html"; raw=p.read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw); return
        if u.path=="/api/updates/status": self.send_json(UPDATES.status()); return
        if u.path=="/api/updates/config": self.send_json(UPDATES.config()); return
        if u.path=="/api/updates/history": self.send_json({"ok":True,"history":UPDATES.history()}); return
        if u.path=="/api/updates/check":
            try: self.send_json(UPDATES.check_remote()); return
            except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return

        if u.path=="/api/voice_diagnostic/status": self.send_json(VOICE_DIAG.status()); return
        if u.path=="/voice-diagnostic":
            p=ROOT/"factory"/"voice_diagnostic_page.html"; raw=p.read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw); return
        if u.path=="/narrator-ab":
            p=ROOT/"factory"/"narrator_ab_page.html"; raw=p.read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw); return
        if u.path=="/api/narrator_ab/status": self.send_json(NARRATOR_AB.status()); return
        if u.path=="/api/narrator_ab/catalog":
            try: self.send_json(NARRATOR_AB.catalog()); return
            except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return
        if u.path=="/api/narrator_ab/units":
            q=urllib.parse.parse_qs(u.query); ep=(q.get("episode_id") or ["JP_STORY_EP002"])[0]
            try: self.send_json(NARRATOR_AB.units(ep)); return
            except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return
        if u.path=="/api/narrator_ab/resolve":
            q=urllib.parse.parse_qs(u.query); ep=(q.get("episode_id") or ["JP_STORY_EP002"])[0]; tc=(q.get("timecode") or [""])[0]
            try: self.send_json(NARRATOR_AB.resolve_time(ep,tc)); return
            except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return
        if u.path=="/api/narrator_ab/latest_sweep":
            q=urllib.parse.parse_qs(u.query); ep=(q.get("episode_id") or ["JP_STORY_EP002"])[0]
            try:
                out=NARRATOR_AB.latest_sweep(ep); self.send_json(out,200 if out.get("ok") else 400); return
            except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return
        if u.path=="/api/qa/status": self.send_json(qa_status()); return
        if u.path=="/api/dashboard": self.send_json(scan_all()); return
        self.send_json({"error":"not found"},404)
    def do_POST(self):
        try:
            if self.path=="/api/updates/upload":
                n=int(self.headers.get("Content-Length","0")); raw=self.rfile.read(n); name=self.headers.get("X-Filename","update.lfupdate.zip")
                try: out=UPDATES.receive_upload(name,raw); self.send_json(out,200); return
                except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return
            body=self.read_body()
            if self.path=="/api/updates/config":
                try: out=UPDATES.save_config(body.get("feed_url",""),body.get("channel","dev")); self.send_json({"ok":True,**out}); return
                except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return
            if self.path=="/api/updates/download":
                try: out=UPDATES.download_remote(); self.send_json(out,200); return
                except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return
            if self.path=="/api/updates/install_latest":
                try:
                    out=UPDATES.install_latest(os.getpid())
                    self.send_json(out,200 if out.get("ok") else 400); return
                except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return
            if self.path=="/api/updates/install":
                try: out=UPDATES.install(body.get("package_path"),os.getpid()); self.send_json(out,200 if out.get("ok") else 400); return
                except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return
            if self.path=="/api/voice_diagnostic/run":
                out=VOICE_DIAG.run_async(body.get("episode_id","JP_STORY_EP002"),body.get("target_wav","unit_001_265337c517c5ec06c424.wav")); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/voice_diagnostic/open":
                out=VOICE_DIAG.open_results(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/narrator_ab/open_unit":
                out=NARRATOR_AB.open_unit(body.get("episode_id","JP_STORY_EP002"),body.get("unit_index")); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/narrator_ab/run_sweep":
                out=NARRATOR_AB.run_style_sweep_async(body.get("episode_id","JP_STORY_EP002"),body.get("unit_index")); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/narrator_ab/run_candidate":
                out=NARRATOR_AB.run_candidate_async(body.get("episode_id","JP_STORY_EP002"),body.get("unit_index"),body.get("style_id")); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/narrator_ab/build_full_candidate":
                episode_id=body.get("episode_id","JP_STORY_EP002")
                staged=NARRATOR_AB.stage_sweep_candidate(episode_id,body.get("candidate_number"))
                if not staged.get("ok"):
                    self.send_json(staged,400); return
                ep=episode_dir("JP_STORY",episode_id)
                m=load_json(ep/"episode_manifest.json",{})
                queued=JOBS.enqueue_adapter_job(ep,m,"BUILD_VOICE_CANDIDATE")
                if not queued.get("ok"):
                    self.send_json({"ok":False,"error":queued.get("error","Failed to queue candidate voice build"),"candidate":staged.get("candidate")},400); return
                event(episode_id,"QUEUED","BUILD_VOICE_CANDIDATE queued",
                      job_id=(queued.get("job") or {}).get("job_id"),
                      resource_class=(queued.get("job") or {}).get("resource_class"),
                      candidate=staged.get("candidate"))
                c=staged.get("candidate") or {}
                self.send_json({
                  "ok":True,
                  "message":f"Candidate Voice Only queued: #{c.get('candidate_number')} · {c.get('speaker')} / {c.get('style')} / id {c.get('style_id')}",
                  "candidate":c,
                  "job":queued.get("job")
                }); return
            if self.path=="/api/narrator_ab/open":
                out=NARRATOR_AB.open_results(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/action":
                out=do_action(body); self.send_json(out,200 if out.get("ok",True) else 400); return
            if self.path=="/api/new_episode":
                out=new_episode(body); self.send_json(out,200); return
            if self.path=="/api/qa/run":
                out=qa_run(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/qa/reset":
                out=qa_reset(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/qa/open_report":
                out=qa_open_report(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/qa/open_log":
                out=qa_open_log(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/qa/live/run":
                out=live_qa_run(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/qa/live/reset":
                out=live_qa_reset(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/qa/live/open_report":
                out=live_qa_open_report(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/qa/live/open_log":
                out=live_qa_open_log(); self.send_json(out,200 if out.get("ok") else 400); return
            if self.path=="/api/qa/live/open_preview":
                out=live_qa_open_preview(); self.send_json(out,200 if out.get("ok") else 400); return
            self.send_json({"error":"not found"},404)
        except Exception as e:
            log(f"request error: {e}"); self.send_json({"ok":False,"error":str(e)},400)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--host",default="127.0.0.1"); ap.add_argument("--port",type=int,default=8765); args=ap.parse_args()
    if not ROOT.exists(): raise SystemExit(f"Factory root missing: {ROOT}")
    threading.Thread(target=worker_loop,daemon=True).start()
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    log(f"Control Center v1.9.9 listening on http://{args.host}:{args.port}")
    try: server.serve_forever(poll_interval=.4)
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=="__main__":
    main()
