import argparse
import fcntl
import json
import sqlite3
import uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
from src.collectors.http import Client
from src.collectors.adapters import collect
from src.processing.pipeline import normalize,deduplicate
from src.analysis.report import analyze
from src.processing.verifier import verify
from src.publishing.export import publish,atomic_write

ROOT=Path(__file__).resolve().parents[1]

def validate_config(c):
    for key in ('max_requests','max_pages','max_seconds','days','compare_days'):
        if not isinstance(c[key],int) or not 1<=c[key]<= (3660 if key in ('days','compare_days') else 3600):raise ValueError('Invalid limit: '+key)
    if c['max_api_budget']<0:raise ValueError('Negative API budget')
    if not c['services'] or not set(c['services'])<= {'marketing','advertising','ai','research'}:raise ValueError('Unknown service')
    if not set(c['groups'])<= {'vacancies','media','procurement'}:raise ValueError('Unknown source group')
    if c.get('llm',{}).get('enabled'):raise ValueError('LLM integration not verified; leave disabled')
    if c['region']!='Республика Башкортостан':raise ValueError('This version supports Башкортостан only; arbitrary region mapping unverified')
    return c

def execute(config,state,output):
    validate_config(config)
    state=Path(state);state.mkdir(parents=True,exist_ok=True)
    with open(state/'run.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        now=datetime.now(timezone.utc);run_id=str(uuid.uuid4())
        run={'id':run_id,'started_at':now.isoformat(),'config':config,
         'period_start':(now-timedelta(days=config['days'])).isoformat(),'period_end':now.isoformat(),
         'status':'running','llm_status':'disabled','api_spend':0,'currency':'RUB'}
        coverage=[];items=[];client=Client(config,state/'cache')
        for source in config['sources']:
            info={**source,'status':'disabled','last_success_at':None,'error':None,'collected':0,'accepted':0}
            if source['category'] in config['groups']:
                try:
                    raw,meta=collect(client,source,config)
                    info.update(meta);info['collected']=len(raw)
                    for record in raw:
                        try:
                            item=verify(normalize(record,source,run_id,config,now),record)
                            # Do not retain full irrelevant pages or identifying profiles.
                            if item.signal_type!='F':items.append(item);info['accepted']+=1
                        except (ValueError,KeyError,TypeError) as error:
                            info.setdefault('validation_errors',[]).append(type(error).__name__)
                    info['status']='partial' if info.get('validation_errors') else 'ok'
                    info['last_success_at']=now.isoformat()
                except Exception as error:
                    # Errors may contain credential-bearing URLs; keep only a safe summary.
                    message=str(error)
                    info['status']='blocked' if '403' in message or 'robots' in message or isinstance(error,PermissionError) else 'error'
                    info['error']=type(error).__name__+(' HTTP '+str(error.code) if hasattr(error,'code') else '')+': '+('доступ к поиску/API отклонён (HTTP 403)' if '403' in message else 'robots.txt или ограничение доступа' if isinstance(error,PermissionError) else 'сбор не выполнен; проверьте доступ, формат и лимиты')
            coverage.append(info)
            print(json.dumps({'source':source['id'],'status':info['status'],'collected':info['collected'],'error':info['error']},ensure_ascii=False),flush=True)
        unique,duplicates=deduplicate(items)
        previous_path=state/'last-success.json' if (state/'last-success.json').exists() else Path(output)
        previous=json.loads(previous_path.read_text()) if previous_path.exists() else None
        summary=analyze(unique,config,coverage,duplicates,previous)
        ok=sum(x['status']=='ok' for x in coverage)
        enabled=sum(x['status']!='disabled' for x in coverage)
        run.update(status='success' if ok==enabled and enabled else 'partial' if ok else 'failed',
                   finished_at=datetime.now(timezone.utc).isoformat(),requests=client.requests,pages=client.pages)
        db=sqlite3.connect(state/'research.sqlite')
        db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS observations (run_id TEXT, id TEXT, payload TEXT, PRIMARY KEY(run_id,id))')
        db.execute('INSERT INTO runs VALUES (?,?)',(run_id,json.dumps(run,ensure_ascii=False)))
        db.executemany('INSERT INTO observations VALUES (?,?,?)',[(run_id,o.observation_id,json.dumps(o.dict(),ensure_ascii=False)) for o in unique])
        db.commit();db.close()
        history=[]
        history_file=state/'history.json'
        if history_file.exists():history=json.loads(history_file.read_text())
        elif previous:history=previous.get('history',[])
        history.append({'run':run,'coverage':coverage,'summary':summary})
        history=history[-30:];atomic_write(history_file,json.dumps(history,ensure_ascii=False))
        payload={'run':run,'coverage':coverage,'summary':summary,'observations':[o.dict() for o in unique],'history':history}
        publish(payload,state/'runs'/f'{run_id}.json')
        # An attempt is separate from the latest successful/partial result.
        publish(payload,Path(output).parent/'attempt.json')
        if ok:
            publish(payload,output);publish(payload,state/'last-success.json')
        elif not Path(output).exists():
            # First failed run honestly displays coverage errors; no fictitious observations.
            publish(payload,output)
        print(json.dumps({'run_id':run_id,'status':run['status'],'verified_sources':ok,'observations':len(unique),'requests':client.requests,'report':str(state/'runs'/f'{run_id}.json')},ensure_ascii=False))
        return 0 if run['status']=='success' else 2

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default=str(ROOT/'config/research.json'))
    parser.add_argument('--state',default=str(ROOT/'.state'))
    parser.add_argument('--output',default=str(ROOT/'web/public/data/latest.json'))
    for name in ('days','compare-days','max-requests','max-pages','max-seconds'):parser.add_argument('--'+name,type=int)
    parser.add_argument('--max-api-budget',type=float)
    parser.add_argument('--cities');parser.add_argument('--services');parser.add_argument('--groups')
    args=parser.parse_args();config=json.loads(Path(args.config).read_text())
    for name in ('days','compare_days','max_requests','max_pages','max_seconds','max_api_budget'):
        if getattr(args,name) is not None:config[name]=getattr(args,name)
    for name in ('cities','services','groups'):
        if getattr(args,name):config[name]=[x.strip() for x in getattr(args,name).split(',') if x.strip()]
    return execute(config,args.state,args.output)
if __name__=='__main__':raise SystemExit(main())
