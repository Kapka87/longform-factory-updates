#!/usr/bin/env python3
"""YouTube Discovery Gate v1: evidence collection and validation only (no D2 scoring).
Standard library only. Requires a user-owned YouTube Data API v3 key for live mode.
No official API data is committed; designed for ephemeral output retention.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

UTC = dt.timezone.utc
API = 'https://www.googleapis.com/youtube/v3/'
SEED_FORMATS = (
    'I tried', 'what happened to', 'things you did not know',
    'how it works', 'the story of', 'before and after',
    'I spent a week', 'mistakes to avoid', 'hidden history',
    'under $', 'I built', 'the truth about',
)
# Title-only quality warnings are prompts for human review, NEVER factual findings.
NON_LATIN_TITLE_RE = re.compile(r'[\u0600-\u06ff\u0900-\u0dff]')
THIRD_PARTY_MEDIA_TITLE_RE = re.compile(r'\b(?:full\s+(?:nigerian\s+)?movie|lost\s+scene)\b',re.I)


def title_review_flags(title):
    """Detect metadata mismatches/risk hints without inferring audio or copyright status."""
    flags=[]
    if NON_LATIN_TITLE_RE.search(title):
        flags.append('TITLE_SCRIPT_REVIEW_ONLY')
    if THIRD_PARTY_MEDIA_TITLE_RE.search(title):
        flags.append('THIRD_PARTY_MEDIA_RIGHTS_REVIEW_ONLY')
    return flags


FIELDS = ('video_id','url','title','channel_id','channel_title','published_at',
          'duration_seconds','view_count','subscriber_count','subscriber_hidden',
          'audio_language','language_status','source_status','channel_size_status',
          'baseline_video_views','discovery_routes','flags')


def iso_now():
    return dt.datetime.now(UTC)


def parse_time(value):
    return dt.datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(UTC)


def dur_seconds(s):
    # YouTube's ISO8601 video duration, including days
    m = re.fullmatch(r'P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',s or '')
    return sum(int(x or 0)*y for x,y in zip(m.groups(),(86400,3600,60,1))) if m else None


class LiveAPI:
    def __init__(self,key):
        if not key: raise ValueError('LIVE_BLOCKED_NO_API_KEY')
        self.key=key
        self.calls=Counter()
    def get(self,endpoint,**params):
        self.calls[endpoint]+=1
        query=urllib.parse.urlencode(params)
        # Never append API keys to URL (may leak to request logs).
        req=urllib.request.Request(API+endpoint+'?'+query,headers={
            'User-Agent':'Discovery-Gate/1.1', 'x-goog-api-key':self.key})
        try:
            with urllib.request.urlopen(req,timeout=25) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            # Prevent inadvertent reflection of API credentials in error messages
            raise RuntimeError('YOUTUBE_API_HTTP_%d on %s'%(e.code,endpoint)) from None
        except urllib.error.URLError:
            raise RuntimeError('YOUTUBE_API_NETWORK_UNAVAILABLE') from None


class FixtureAPI:
    """Deterministic fixture responses for zero-network contract tests."""
    def __init__(self,fixture):
        self.fixture=fixture
        self.calls=Counter()
    def get(self,endpoint,**params):
        self.calls[endpoint]+=1
        if endpoint=='search':
            ids=self.fixture['search_ids'].get(params.get('q',''),[])
            return {'items':[{'id':{'videoId':v}} for v in ids]}
        if endpoint=='videoCategories':
            return {'items':[{'id':str(v),'snippet':{'assignable':True}} for v in self.fixture.get('category_ids',[])]}
        if endpoint=='videos':
            videos=self.fixture.get('videos',{})
            return {'items':[videos[i] for i in params['id'].split(',') if i in videos]}
        if endpoint=='channels':
            channels=self.fixture.get('channels',{})
            return {'items':[channels[i] for i in params['id'].split(',') if i in channels]}
        if endpoint=='playlistItems':
            items=self.fixture.get('uploads',{}).get(params['playlistId'],[])
            return {'items':[{'snippet':{'resourceId':{'videoId':v}}} for v in items]}
        raise ValueError(endpoint)


def chunks(items,n):
    for x in range(0,len(items),n): yield items[x:x+n]


def verified_collect(api,now,search_budget=26,max_candidates=130,max_channels=35,
                     min_seconds=480,small_limit=10000,region='US'):
    """Only emits official API fields, categorical labels and unmodified raw comparisons.
    No outlier ratios or custom scores: respect YouTube developer policies pending approval.
    """
    since=(now-dt.timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ')
    until=now.strftime('%Y-%m-%dT%H:%M:%SZ')
    routes={}
    queries=[]
    # Diverse search routes are interleaved so the call budget cannot consume
    # every search on narrative keywords before reaching broad categories.
    # 'medium' is 4-20 min; 'long' is 20+; enforce minimum 8 min after videos.list.
    for duration in ('medium','long'):
        queries.append(('broad:'+duration,dict(videoDuration=duration,order='viewCount')))
    categories=api.get('videoCategories',part='snippet',regionCode=region).get('items',[])
    cat_queries=[]
    for category in categories:
        if category.get('snippet',{}).get('assignable',True) is False: continue
        cat_queries.append(('category:'+str(category['id']),dict(videoCategoryId=str(category['id']),
                       videoDuration='medium',order='viewCount')))
    format_queries=[('format:'+phrase,dict(q=phrase,videoDuration='medium',order='viewCount'))
                    for phrase in SEED_FORMATS]
    while cat_queries or format_queries:
        if cat_queries: queries.append(cat_queries.pop(0))
        if format_queries: queries.append(format_queries.pop(0))
    query_count=0
    for route,opts in queries[:search_budget]:
        query_count+=1
        data=api.get('search',part='snippet',type='video',maxResults=50,
                     publishedAfter=since,publishedBefore=until,
                     relevanceLanguage='en',regionCode=region,**opts)
        for item in data.get('items',[]):
            v=item.get('id',{}).get('videoId')
            if isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_-]{11}',v):
                routes.setdefault(v,set()).add(route)
    all_ids=list(routes)
    observed={}
    for part in chunks(all_ids,50):
        r=api.get('videos',part='snippet,statistics,contentDetails,status',id=','.join(part))
        for item in r.get('items',[]): observed[item['id']]=item
    # Do not silently consider failed/deleted metadata verified.
    rejects=Counter()
    matched=[]
    for vid in all_ids:
        item=observed.get(vid)
        if not item: rejects['MISSING_VIDEO_METADATA']+=1;continue
        snippet=item.get('snippet',{})
        stats=item.get('statistics',{})
        status=item.get('status',{})
        try:
            published=parse_time(snippet['publishedAt'])
            seconds=dur_seconds(item.get('contentDetails',{}).get('duration'))
            views=int(stats['viewCount'])
        except (KeyError,ValueError,TypeError):
            rejects['INCOMPLETE_OFFICIAL_FIELDS']+=1;continue
        if not (now-dt.timedelta(days=90)<=published<=now):
            rejects['OUTSIDE_90_DAYS']+=1;continue
        if seconds is None or seconds<min_seconds:
            rejects['TOO_SHORT']+=1;continue
        if status.get('privacyStatus') not in (None,'public'):
            rejects['NOT_PUBLIC']+=1;continue
        lang=snippet.get('defaultAudioLanguage') or snippet.get('defaultLanguage') or ''
        if lang and not lang.lower().startswith('en'):
            rejects['EXPLICITLY_NON_ENGLISH']+=1;continue
        if not snippet.get('channelId'):
            rejects['MISSING_CHANNEL_ID']+=1;continue
        matched.append(dict(video_id=vid,url='https://www.youtube.com/watch?v='+vid,
                     title=snippet.get('title',''),channel_id=snippet['channelId'],
                     channel_title=snippet.get('channelTitle',''),
                     published_at=published.strftime('%Y-%m-%dT%H:%M:%SZ'),
                     duration_seconds=seconds,view_count=views,
                     audio_language=lang,language_status='DECLARED_EN' if lang else 'UNVERIFIED',
                     source_status='YOUTUBE_API_METADATA',discovery_routes=';'.join(sorted(routes[vid]))))
    matched.sort(key=lambda x:x['view_count'],reverse=True)
    # Fetch all discovered channel metadata before choosing the SMALL channels.
    # Limiting channel lookups to the highest-viewed 35 first would silently
    # exclude most small channels and negate the discovery objective.
    candidate_channels=list(dict.fromkeys(v['channel_id'] for v in matched))
    channel_data={}
    for part in chunks(candidate_channels,50):
        for ch in api.get('channels',part='snippet,statistics,contentDetails',id=','.join(part)).get('items',[]):
            channel_data[ch['id']]=ch
    results=[]
    seen_per_channel=Counter()
    admitted_channels=set()
    for v in matched:
        if len(results)>=max_candidates:break
        cid=v['channel_id']
        if cid not in admitted_channels and len(admitted_channels)>=max_channels:
            continue
        ch=channel_data.get(cid)
        flags=title_review_flags(v.get('title',''))
        if not ch:
            rejects['MISSING_CHANNEL_METADATA']+=1;continue
        st=ch.get('statistics',{})
        hidden=bool(st.get('hiddenSubscriberCount',False))
        if hidden or st.get('subscriberCount') is None:
            subs=None
            sz='SUBSCRIBERS_UNVERIFIED'
        else:
            try: subs=int(st['subscriberCount'])
            except (ValueError,TypeError): subs=None
            sz='SMALL_CHANNEL_CONFIRMED' if subs is not None and subs<=small_limit else 'OUTSIDE_SMALL_CHANNEL_SCOPE'
        if sz!='SMALL_CHANNEL_CONFIRMED':
            rejects[sz]+=1;continue
        if seen_per_channel[cid]>=3:
            rejects['CHANNEL_DIVERSITY_CAP']+=1;continue
        seen_per_channel[cid]+=1
        admitted_channels.add(cid)
        if v['language_status']=='UNVERIFIED':flags.append('LANGUAGE_NEEDS_MANUAL_REVIEW')
        v.update(subscriber_count=subs,subscriber_hidden=hidden,
                 channel_size_status=sz,baseline_video_views='',flags=';'.join(flags))
        results.append(v)
    # Minimal independent channel baseline: fetch upload IDs then raw view figures.
    # DO NOT calculate or label any ratio/quality/outlier score without applicable policy approval.
    by_channel={}
    for cid in dict.fromkeys(v['channel_id'] for v in results):
        ch=channel_data.get(cid,{})
        playlist=(ch.get('contentDetails',{}).get('relatedPlaylists') or {}).get('uploads')
        if not playlist:
            by_channel[cid]=[];continue
        data=api.get('playlistItems',part='snippet',playlistId=playlist,maxResults=20)
        ids=[x.get('snippet',{}).get('resourceId',{}).get('videoId') for x in data.get('items',[])]
        ids=[v for v in ids if isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_-]{11}',v)]
        if not ids: by_channel[cid]=[];continue
        videos=api.get('videos',part='statistics,contentDetails,snippet,status',id=','.join(ids))
        baseline=[]
        for item in videos.get('items',[]):
            try:
                seconds=dur_seconds(item.get('contentDetails',{}).get('duration'))
                p=parse_time(item['snippet']['publishedAt'])
                views=int(item['statistics']['viewCount'])
                if seconds and seconds>=min_seconds and p<=now and item.get('status',{}).get('privacyStatus') in (None,'public'):
                    baseline.append({'id':item['id'],'views':views,'published_at':p.strftime('%Y-%m-%d')})
            except (KeyError,ValueError,TypeError):pass
        by_channel[cid]=baseline[:10]
    for v in results:
        # Raw unmodified comparable view counts: no computed metrics
        comparisons=[str(b['views']) for b in by_channel[v['channel_id']] if b['id']!=v['video_id']]
        v['baseline_video_views']=';'.join(comparisons[:8])
        if len(comparisons)<3:
            v['flags']+=';INSUFFICIENT_BASELINE' if v['flags'] else 'INSUFFICIENT_BASELINE'
    return {'generated_at':now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'source':'YouTube Data API v3','discovery_scope':'CATEGORY_UNRESTRICTED_BEST_EFFORT',
            'language_policy':'Explicit non-English excluded; absent/defaultLanguage metadata is UNVERIFIED',
            'verified_scope':'Official metadata is not a human verification of audio, video or rights',
            'no_market_greenlight':True,'no_custom_scores':True,
            'search_calls':query_count,'total_search_unique_ids':len(all_ids),
            'video_metadata_found':len(observed),'matched_duration_date':len(matched),
            'channels_metadata_requested':len(candidate_channels),
            'small_channel_candidates':len(results),'independent_channels':len(set(v['channel_id'] for v in results)),
            'rejects':dict(sorted(rejects.items())),'api_calls':dict(api.calls),
            'candidates':results}


def safe_csv(value):
    s='' if value is None else str(value)
    # Stop formula injection if user opens CSV in Excel/Sheets.
    return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s


def write_outputs(data,folder):
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'candidates.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');wr.writeheader()
        for record in data['candidates']:wr.writerow({k:safe_csv(record.get(k,'')) for k in FIELDS})
    (folder/'candidates.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Discovery Gate v1 — collection/verification only',
           '',f"- Collected: {data['generated_at']}",
           f"- Source: {data['source']}",
           f"- Unique URLs in search: {data['total_search_unique_ids']}",
           f"- Official metadata fetched: {data['video_metadata_found']}",
           f"- Date/duration matches: {data['matched_duration_date']}",
           f"- Small-channel candidates: {data['small_channel_candidates']}",
           f"- Independent channels: {data['independent_channels']}",
           '- Final judgment: **NOT PERFORMED / NO_GREENLIGHT**',
           '- Outlier scores: NOT calculated; approval of derived metrics has not been established.',
           '- Language/audience/rights/video QC: NOT confirmed solely by API metadata.',
           '- Search sample: not representative of the entire YouTube universe.',
           '', '## Candidates (public raw metadata)',
           '|Video|Views|Subscribers|Duration (seconds)|Language|Raw comparable view counts|',
           '|---|---:|---:|---:|---|---|']
    for r in data['candidates'][:60]:
        title=r['title'].replace('|','/').replace('\n',' ')
        lines.append(f"|[{title}]({r['url']})|{r['view_count']}|{r['subscriber_count']}|{r['duration_seconds']}|{r['language_status']}|{r['baseline_video_views']}|")
    lines.extend(['','## Rejection tally','']+[f'- {k}: {v}' for k,v in data['rejects'].items()])
    lines.extend(['','## Required D2 checks','',
        '- Confirm actual first 60 seconds and narration format via video playback.',
        '- Independently check provenance/rights and production feasibility.',
        '- Do not infer other creators\' CTR, RPM, retention or monetization.',
        '- Use existing D0/D1/D2 100-point and K1–K6 rules; no automatic GO.',
        '- Delete/refresh API data within policy retention limits. Workflow artifact retention is 7 days.'])
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,help='Offline verification test only. Never claim live API validation.')
    p.add_argument('--out',type=Path,default=Path('discovery-output'))
    p.add_argument('--date',help='Override UTC timestamp for deterministic tests')
    p.add_argument('--search-budget',type=int,default=26)
    args=p.parse_args(argv)
    if not 1<=args.search_budget<=60:p.error('--search-budget must be 1..60')
    now=parse_time(args.date) if args.date else iso_now()
    if args.fixture:
        api=FixtureAPI(json.loads(args.fixture.read_text(encoding='utf-8')))
        mode='OFFLINE_FIXTURE'
    else:
        key=os.getenv('YOUTUBE_API_KEY','')
        if not key:
            print('LIVE_BLOCKED_NO_API_KEY: configure repository Actions secret YOUTUBE_API_KEY; no fake data emitted',file=sys.stderr)
            return 3
        api=LiveAPI(key);mode='LIVE_API'
    try: result=verified_collect(api,now,search_budget=args.search_budget)
    except RuntimeError as e:
        print('LIVE_BLOCKED: '+str(e),file=sys.stderr);return 4
    result['run_mode']=mode
    write_outputs(result,args.out)
    print(json.dumps({k:v for k,v in result.items() if k not in ('candidates',)},ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())