#!/usr/bin/env python3
"""Audit previous exploratory candidate files structurally only. Not a live verification."""
import argparse, collections, datetime as dt, json, re
from pathlib import Path
from urllib.parse import urlparse,parse_qs


def audit(path, asof):
    root=json.loads(path.read_text(encoding='utf-8'))
    entries=root['entries'] if isinstance(root,dict) else root
    issues=[]; ids=[]; valid=[]; channels=collections.Counter()
    for i,r in enumerate(entries,1):
        uri=r.get('video_url','')
        u=urlparse(uri)
        vid=(parse_qs(u.query).get('v') or [''])[0]
        if u.netloc not in ('www.youtube.com','youtube.com','m.youtube.com') or not re.fullmatch('[A-Za-z0-9_-]{11}',vid):
            issues.append({'n':i,'type':'BAD_URL','value':uri});continue
        ids.append(vid)
        channels[r.get('channel','')]+=1
        try:
            d=dt.date.fromisoformat(r['publish_date'])
            age=(asof-d).days
            if age<0 or age>90: issues.append({'n':i,'type':'OUT_OF_WINDOW','days_old':age})
        except (ValueError,TypeError,KeyError):issues.append({'n':i,'type':'DATE_UNVERIFIED'})
        try:
            seconds=sum(int(x)*unit for x,unit in zip(r['duration'].split(':'),[3600,60,1][-len(r['duration'].split(':')):]))
            if seconds<480: issues.append({'n':i,'type':'UNDER_8_MIN','seconds':seconds})
        except (ValueError,TypeError,KeyError):issues.append({'n':i,'type':'DURATION_UNVERIFIED'})
        if not isinstance(r.get('views_snapshot'),int):issues.append({'n':i,'type':'VIEWS_UNVERIFIED'})
        if r.get('subscribers_snapshot') is None:issues.append({'n':i,'type':'SUBSCRIBERS_UNVERIFIED'})
        valid.append(vid)
    for vid,cnt in collections.Counter(ids).items():
        if cnt>1: issues.append({'type':'DUPLICATE_ID','id':vid,'count':cnt})
    return {'input':str(path),'input_origin':'PRIOR_THIRD_PARTY_SNAPSHOTS_NOT_LIVE_VERIFIED',
            'count':len(entries),'valid_url_count':len(valid),
            'unique_ids':len(set(ids)),'distinct_named_channels':len(channels),
            'top_channel_counts':channels.most_common(8),'issues':issues,
            'live_api_verified':False,'greenlight':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--as-of',default='2026-10-17');p.add_argument('--out',type=Path,default=Path('audit-result.json'))
    a=p.parse_args();report=audit(a.input,dt.date.fromisoformat(a.as_of))
    a.out.parent.mkdir(exist_ok=True,parents=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='issues'},ensure_ascii=False));print('issues:',report['issues'])