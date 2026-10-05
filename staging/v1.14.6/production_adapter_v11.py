from __future__ import annotations
from pathlib import Path
import json
from adapters.channels.jp_bts.production_adapter_v10 import JPBTSProductionAdapter as _V10
from adapters.channels.production_adapter_common_v10 import _write

class JPBTSProductionAdapter(_V10):
    ADAPTER_ID="JP_BTS_PRODUCTION_ADAPTER_v1_1"
    ADAPTER_VERSION="1.1"
    DISCOVERY_CONTRACT="JP_BTS_DISCOVERY_GATE_v2"
    PHASES=("D0_WIDE","D1_MARKET_SCREEN","D2_DEEP_VALIDATION")

    D0_SCHEMA={
      "type":"object","required":["status","summary","decisions"],
      "properties":{
        "status":{"const":"PASS"},"summary":{"type":"string"},
        "decisions":{"type":"array","minItems":20,"maxItems":30,"items":{"type":"object","required":["candidate_id","premise","viewer_question","why_interesting","fatal_flaw"],"properties":{
          "candidate_id":{"type":"string"},"premise":{"type":"string"},"viewer_question":{"type":"string"},"why_interesting":{"type":"string"},"fatal_flaw":{"type":["string","null"]}
        }}}
      }
    }
    D1_SCHEMA={
      "type":"object","required":["status","summary","decisions"],
      "properties":{
        "status":{"const":"PASS"},"summary":{"type":"string"},
        "decisions":{"type":"array","minItems":5,"maxItems":8,"items":{"type":"object","required":["candidate_id","japan_relevance","pain_or_surprise","youtube_demand","saturation","bts_gap","source_evidence"],"properties":{
          "candidate_id":{"type":"string"},"japan_relevance":{"type":"string"},"pain_or_surprise":{"type":"string"},"youtube_demand":{"type":"string"},"saturation":{"type":"string"},"bts_gap":{"type":"string"},
          "source_evidence":{"type":"array","items":{"type":"object","required":["url","retrieved_at","evidence_type"],"properties":{"url":{"type":"string"},"retrieved_at":{"type":"string"},"evidence_type":{"type":"string"}}}}
        }}}
      }
    }
    D2_SCHEMA={
      "type":"object","required":["status","summary","gate_status","winner_candidate_id","decisions"],
      "properties":{
        "status":{"const":"PASS"},"summary":{"type":"string"},
        "gate_status":{"enum":["DISCOVERY_PASS","CONDITIONAL_RESEARCH","HOLD","DROP","NO_PASS"]},
        "winner_candidate_id":{"type":["string","null"]},
        "decisions":{"type":"array","minItems":1,"maxItems":3,"items":{"type":"object","required":["candidate_id","audience_evidence","click_potential","retention_engine","opportunity_gap","evidence_production","revenue_fit","hard_kills","total_score","recommendation","comparables","source_evidence"],"properties":{
          "candidate_id":{"type":"string"},
          "audience_evidence":{"type":"object","required":["score","evidence"]},
          "click_potential":{"type":"object","required":["score","titles","thumbnail_hooks","evidence"]},
          "retention_engine":{"type":"object","required":["score","reveal_chain","evidence"]},
          "opportunity_gap":{"type":"object","required":["score","demand_exists","competition_strong","bts_gap_exists","evidence"]},
          "evidence_production":{"type":"object","required":["score","primary_sources","visualizable","archival_availability","diagram_dependency","generative_reenactment_dependency","rights_risk","complexity"]},
          "revenue_fit":{"type":"object","required":["score","advertiser_safe","evergreen","japan_relevance","search_recommendation","series_expansion","niche_risk","upside_vs_cost"]},
          "hard_kills":{"type":"array","items":{"enum":["K1_NO_MARKET_EVIDENCE","K2_NO_CLICK","K3_NO_LONGFORM_ENGINE","K4_UNVERIFIABLE_CORE","K5_PRODUCTION_MISMATCH","K6_COMMODITY_EXPLANATION"]}},
          "total_score":{"type":"number","minimum":0,"maximum":100},
          "recommendation":{"enum":["DISCOVERY_PASS","CONDITIONAL_RESEARCH","HOLD","DROP"]},
          "comparables":{"type":"array","items":{"type":"object","required":["title","channel","published_at","views","channel_size","views_sub_ratio","format","hook","explains","misses","url","retrieved_at"],"properties":{"title":{"type":"string"},"channel":{"type":"string"},"published_at":{"type":["string","null"]},"views":{"type":["integer","null"]},"channel_size":{"type":["integer","null"]},"views_sub_ratio":{"type":["number","null"]},"format":{"type":"string"},"hook":{"type":"string"},"explains":{"type":"string"},"misses":{"type":"string"},"url":{"type":"string"},"retrieved_at":{"type":"string"}}}},
          "source_evidence":{"type":"array","items":{"type":"object","required":["url","retrieved_at","evidence_type"],"properties":{"url":{"type":"string"},"retrieved_at":{"type":"string"},"evidence_type":{"type":"string"}}}}
        }}}
      }
    }

    def _disc(self,m):
        return m.setdefault("jp_bts_discovery_v2",{"contract":self.DISCOVERY_CONTRACT,"phase":"D0_WIDE","status":"IN_PROGRESS","history":[]})

    def _phase(self,m):
        d=self._disc(m); p=d.get("phase","D0_WIDE")
        return p if p in self.PHASES else "D0_WIDE"

    def _schema(self,phase):
        return {"D0_WIDE":self.D0_SCHEMA,"D1_MARKET_SCREEN":self.D1_SCHEMA,"D2_DEEP_VALIDATION":self.D2_SCHEMA}[phase]

    def _instruction(self,phase):
        if phase=="D0_WIDE":
            return "JP_BTS Discovery Gate v2 / D0 WIDE. Generate 20-30 distinct Japan-relevant information-first longform candidates. Cheap screen only; do not deep-research. Each candidate must include premise, viewer question, why it is interesting now, and an obvious fatal flaw if any. Do not force a winner."
        if phase=="D1_MARKET_SCREEN":
            return "JP_BTS Discovery Gate v2 / D1 MARKET SCREEN. Use ONLY candidate_ids present in the supplied D0 result and return 5-8 survivors. Research Japanese daily-life relevance, money/time/pain/anxiety/surprise, Japanese YouTube or adjacent demand evidence, saturation, and a genuine Behind-the-Steps reinterpretation gap. Every factual market claim needs source_evidence with URL, retrieval date, and evidence type. Never fabricate YouTube statistics."
        return "JP_BTS Discovery Gate v2 / D2 DEEP VALIDATION. Use ONLY candidate_ids present in the supplied D1 result and deeply validate at most the top 3. Score Audience Evidence 20, Click Potential 20, Retention Engine 20, Opportunity Gap 15, Evidence & Production Feasibility 15, Revenue Fit 10. Apply hard kills K1-K6. Click Potential must include 3 provisional titles and 2 thumbnail hooks. Retention needs at least 3 reveals/escalations. Opportunity Gap should seek >=3 direct comparables and preferably >=3 adjacent; use null for unavailable stats, never invent them. No forced winner: winner_candidate_id may be null and all candidates may fail. Discovery is NOT Greenlight."

    def _validate_shape(self,obj,schema,path="$"):
        if not isinstance(obj,dict): raise ValueError(path+" must be object")
        for k in schema.get("required",[]): 
            if k not in obj: raise ValueError(path+" missing "+k)
        props=schema.get("properties",{})
        for k,s in props.items():
            if k not in obj: continue
            v=obj[k]; typ=s.get("type")
            if "const" in s and v!=s["const"]: raise ValueError(path+"."+k+" must equal "+str(s["const"]))
            if "enum" in s and v not in s["enum"]: raise ValueError(path+"."+k+" invalid enum")
            if typ=="array":
                if not isinstance(v,list): raise ValueError(path+"."+k+" must be array")
                if len(v)<s.get("minItems",0) or len(v)>s.get("maxItems",10**9): raise ValueError(path+"."+k+" item count invalid")
                item=s.get("items")
                if item:
                    for i,x in enumerate(v):
                        if "enum" in item and x not in item["enum"]: raise ValueError(path+"."+k+" invalid item")
                        elif item.get("type")=="object": self._validate_shape(x,item,path+"."+k+"["+str(i)+"]")
            elif typ=="object":
                if not isinstance(v,dict): raise ValueError(path+"."+k+" must be object")
                self._validate_shape(v,s,path+"."+k)
            elif isinstance(typ,list):
                good=(v is None and "null" in typ) or (isinstance(v,str) and "string" in typ) or (isinstance(v,(int,float)) and not isinstance(v,bool) and ("number" in typ or "integer" in typ))
                if not good: raise ValueError(path+"."+k+" type invalid")
            elif typ=="string" and not isinstance(v,str): raise ValueError(path+"."+k+" must be string")
            elif typ=="number" and not (isinstance(v,(int,float)) and not isinstance(v,bool)): raise ValueError(path+"."+k+" must be number")
            elif typ=="integer" and not (isinstance(v,int) and not isinstance(v,bool)): raise ValueError(path+"."+k+" must be integer")

    def _create_task(self,ep,m):
        if self._stage(m)!="DISCOVERY": return super()._create_task(ep,m)
        phase=self._phase(m); old=self._load_task(ep,"DISCOVERY")
        if old and old.get("status")=="AWAITING_MANUAL_RESULT" and old.get("discovery_phase")==phase:
            return {"ok":True,"message":"Existing "+phase+" task reused","task_id":old.get("task_id")}
        import reasoning_provider_bridge as reasoning
        prior=None
        if phase=="D1_MARKET_SCREEN": prior=self._reason_dir(ep)/"DISCOVERY_D0_WIDE_result.json"
        elif phase=="D2_DEEP_VALIDATION": prior=self._reason_dir(ep)/"DISCOVERY_D1_MARKET_SCREEN_result.json"
        prior_result=json.loads(prior.read_text(encoding="utf-8")) if prior and prior.exists() else None
        instruction=self._instruction(phase)
        context=self._task_context(ep,m,"DISCOVERY"); context.update({"discovery_contract":self.DISCOVERY_CONTRACT,"discovery_phase":phase,"prior_phase_result":prior_result})
        packet=reasoning.execute_task(self.root,task={"task_type":f"{self.CHANNEL_ID}_DISCOVERY_{phase}","channel_id":self.CHANNEL_ID,"episode_id":m.get("episode_id"),"instruction":instruction,"context":context})
        packet["discovery_contract"]=self.DISCOVERY_CONTRACT; packet["discovery_phase"]=phase; packet["result_schema"]=self._schema(phase)
        packet["manual_prompt"]="Return JSON only matching result_schema. "+instruction+"\n\nresult_schema:\n"+json.dumps(packet["result_schema"],ensure_ascii=False,indent=2)
        if prior_result is not None: packet["manual_prompt"]+="\n\nprior_phase_result:\n"+json.dumps(prior_result,ensure_ascii=False,indent=2)
        _write(self._task_copy(ep,"DISCOVERY"),packet); self._set_stage(m,"DISCOVERY","BLOCKED",current=True); self._save_manifest(ep,m)
        return {"ok":True,"message":phase+" reasoning task prepared","task_id":packet.get("task_id")}

    def _import_result(self,ep,m,body):
        if self._stage(m)!="DISCOVERY": return super()._import_result(ep,m,body)
        phase=self._phase(m); task=self._load_task(ep,"DISCOVERY")
        if not task or task.get("discovery_phase")!=phase: raise RuntimeError("No task prepared for current Discovery phase")
        raw=body.get("result"); result=json.loads(raw) if isinstance(raw,str) else raw
        if not isinstance(result,dict): raise ValueError("result JSON required")
        self._validate_shape(result,self._schema(phase))
        ids=[str(x.get("candidate_id")) for x in result.get("decisions",[]) if isinstance(x,dict)]
        if len(ids)!=len(set(ids)): raise ValueError("candidate_id values must be unique")
        if phase!="D0_WIDE":
            prev="D0_WIDE" if phase=="D1_MARKET_SCREEN" else "D1_MARKET_SCREEN"
            pp=self._reason_dir(ep)/f"DISCOVERY_{prev}_result.json"
            pobj=json.loads(pp.read_text(encoding="utf-8")); allowed={str(x.get("candidate_id")) for x in pobj.get("decisions",[])}
            if not set(ids)<=allowed: raise ValueError(phase+" contains candidate_id not present in "+prev)
        if phase=="D2_DEEP_VALIDATION":
            for row in result["decisions"]:
                scores=[row["audience_evidence"]["score"],row["click_potential"]["score"],row["retention_engine"]["score"],row["opportunity_gap"]["score"],row["evidence_production"]["score"],row["revenue_fit"]["score"]]
                caps=[20,20,20,15,15,10]
                if any(not isinstance(x,(int,float)) or isinstance(x,bool) or x<0 or x>cap for x,cap in zip(scores,caps)): raise ValueError("D2 component score outside allowed range")
                if abs(sum(scores)-row["total_score"])>0.01: raise ValueError("D2 total_score must equal component score sum")
                if len(row["click_potential"].get("titles") or [])<3 or len(row["click_potential"].get("thumbnail_hooks") or [])<2: raise ValueError("D2 click package incomplete")
                if len(row["retention_engine"].get("reveal_chain") or [])<3: raise ValueError("D2 retention reveal chain requires >=3")
                if row["hard_kills"] and row["recommendation"]=="DISCOVERY_PASS": raise ValueError("Hard Kill overrides DISCOVERY_PASS")
            winner=result.get("winner_candidate_id")
            if winner is not None and winner not in ids: raise ValueError("winner_candidate_id must reference D2 candidate")
            if winner is not None:
                wr=next(x for x in result["decisions"] if x["candidate_id"]==winner)
                if wr["recommendation"]!="DISCOVERY_PASS" or wr["hard_kills"]: raise ValueError("winner must be a clean DISCOVERY_PASS")
            if result["gate_status"]=="DISCOVERY_PASS" and winner is None: raise ValueError("DISCOVERY_PASS requires winner_candidate_id")
            if result["gate_status"]!="DISCOVERY_PASS" and winner is not None: raise ValueError("non-pass gate must not force a winner")
        archive=self._reason_dir(ep)/f"DISCOVERY_{phase}_result.json"; _write(archive,result)
        d=self._disc(m); d["history"].append({"phase":phase,"result_path":str(archive)})
        if phase=="D0_WIDE":
            d["phase"]="D1_MARKET_SCREEN"; self._set_stage(m,"DISCOVERY","READY",current=True)
        elif phase=="D1_MARKET_SCREEN":
            d["phase"]="D2_DEEP_VALIDATION"; self._set_stage(m,"DISCOVERY","READY",current=True)
        else:
            d["status"]=result["gate_status"]; d["winner_candidate_id"]=result.get("winner_candidate_id")
            if result["gate_status"]=="DISCOVERY_PASS":
                self._set_stage(m,"DISCOVERY","COMPLETE"); self._set_stage(m,"GREENLIGHT","NEEDS_REVIEW",current=True)
            else:
                self._set_stage(m,"DISCOVERY","NEEDS_REVIEW",current=True)
        self._save_manifest(ep,m)
        try:self._task_copy(ep,"DISCOVERY").unlink()
        except FileNotFoundError:pass
        return {"ok":True,"message":phase+" result imported","discovery_phase":d.get("phase"),"gate_status":d.get("status")}
