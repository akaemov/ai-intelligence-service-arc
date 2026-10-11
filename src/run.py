import argparse,fcntl,json,re,sqlite3,uuid
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path
from src.collectors.http import Client
from src.collectors.adapters import collect
from src.processing.pipeline import normalize,deduplicate,DICTIONARY
from src.analysis.report import analyze
from src.processing.verifier import verify
from src.processing.geography import load_directory
from src.publishing.export import publish,atomic_write

ROOT=Path(__file__).resolve().parents[1]
MODES={'russia','selected_regions','industries'}
GROUPS={'requests','procurement','vacancies','media','search','search_statistics','surveys','official_data','social','discussions','companies','associations','directories','maps_reviews','classifieds','aggregators'}

def validate_config(c):
    for k in ('max_requests','max_pages','max_seconds','days','compare_days','per_region_observations','per_source_pages','per_source_requests'):
        if isinstance(c.get(k),bool) or not isinstance(c.get(k),int) or not 1<=c[k]<=3660:raise ValueError('Invalid limit: '+k)
    if not isinstance(c.get('max_api_budget'),(float,int)) or c['max_api_budget']<0:raise ValueError('Invalid API budget')
    if c.get('mode') not in MODES:raise ValueError('Unknown mode')
    for k in ('regions','cities','industries','segments','services','groups'):
        if not isinstance(c.get(k),list) or not all(isinstance(x,str) for x in c[k]):raise ValueError('Expected string list: '+k)
    if c['mode']=='selected_regions' and not c['regions']:raise ValueError('Selected regions required')
    if c['mode']=='industries' and not c['industries']:raise ValueError('Selected industries required')
    if not c['services'] or not set(c['services'])<=set(DICTIONARY['services']):raise ValueError('Unknown service')
    if not set(c['groups'])<=GROUPS:raise ValueError('Unknown source group')
    if not set(c['segments'])<={'business','government','individual','unknown'}:raise ValueError('Unknown segment')
    for source in c['sources']:
        if not re.fullmatch(r'[a-z0-9_-]+',source['id']):raise ValueError('Invalid source ID')
    if c.get('llm',{}).get('enabled') and c['max_api_budget']<=0:raise ValueError('Enabled LLM requires explicit API budget')
    return c

def safe_error(error):
    code=getattr(error,'code',None);message=str(error)
    blocked=code in (401,403,429) or '403' in message or isinstance(error,PermissionError)
    return ('blocked' if blocked else 'error'),type(error).__name__+(f' HTTP {code}' if code else '')+': '+('доступ ограничен; обход не выполняется' if blocked else 'не удалось получить/проверить данные; подробности в диагностике адаптера')

def execute(config,state,output,resume=None):
    config=json.loads(json.dumps(config));validate_config(config)
    config['dictionary_version']=DICTIONARY['version']
    state=Path(state);state.mkdir(parents=True,exist_ok=True)
    with open(state/'run.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        run_id=str(uuid.UUID(resume)) if resume else str(uuid.uuid4())
        checkpoint=state/'checkpoints'/run_id;checkpoint.mkdir(parents=True,exist_ok=True)
        manifest=checkpoint/'manifest.json'
        if resume:
            previous_manifest=json.loads(manifest.read_text())
            if previous_manifest['config']!=config:raise ValueError('Resume configuration must match original')
            now=datetime.fromisoformat(previous_manifest['started_at'])
        else:
            now=datetime.now(timezone.utc);atomic_write(manifest,json.dumps({'config':config,'started_at':now.isoformat()},ensure_ascii=False))
        period_start=(now-timedelta(days=config['days'])).isoformat()
        run={'id':run_id,'schema_version':2,'started_at':now.isoformat(),'config':config,'resumed':bool(resume),
          'period_start':period_start,'period_end':now.isoformat(),'status':'running','llm_status':'disabled','api_spend':0,'currency':'USD'}
        client=Client(config,state/'cache')
        directory,geo_error=load_directory(client,state)
        if directory:
            for region in config['regions']:
                if not directory.region(region):raise ValueError('Region absent from current directory: '+region)
        config['_directory']=directory
        coverage=[];items=[];region_counts=Counter()
        sources=sorted(config['sources'],key=lambda s:({'requests':0,'procurement':1,'vacancies':2}.get(s['category'],3)))
        old_path=state/'last-success.json' if (state/'last-success.json').exists() else Path(output)
        previous=json.loads(old_path.read_text()) if old_path.exists() else None
        previous_coverage={s['id']:s for s in (previous or {}).get('coverage',[])}
        for source in sources:
            info={**source,'status':'disabled','last_checked_at':datetime.now(timezone.utc).isoformat(),
              'last_success_at':previous_coverage.get(source['id'],{}).get('last_success_at'),
              'error':None,'collected':0,'accepted':0,'quota_excluded':0}
            raw=[];saved=checkpoint/(source['id']+'.json')
            if source['category'] in config['groups'] and source.get('enabled',True):
                client.begin_source(source['id'])
                try:
                    if resume and saved.exists() and not json.loads(saved.read_text())['meta'].get('partial'):
                        restored=json.loads(saved.read_text());raw=restored['records'];meta=restored['meta'];info['resumed_from_checkpoint']=True
                    else:
                        raw,meta=collect(client,source,config)
                        atomic_write(saved,json.dumps({'records':raw,'meta':meta},ensure_ascii=False))
                    info.update(meta);info['collected']=len(raw)
                    for record in raw:
                        try:
                            item=verify(normalize(record,source,run_id,config,now),record)
                            if item.signal_type=='F':continue
                            group=item.customer_region or '__unknown__'
                            if region_counts[group]>=config['per_region_observations']:
                                info['quota_excluded']+=1;continue
                            region_counts[group]+=1
                            if (item.customer_segment or 'unknown') not in config['segments']:
                                item.federal_eligible=False;item.regional_eligible=False
                                item.limitations.append('Сегмент вне выбранных параметров запуска')
                            items.append(item);info['accepted']+=1
                        except (ValueError,KeyError,TypeError):info.setdefault('validation_errors',[]).append('Некорректные факты/схема')
                    info['status']='partial' if info.get('partial') or info.get('validation_errors') else 'ok'
                    info['last_success_at']=datetime.now(timezone.utc).isoformat()
                except Exception as error:info['status'],info['error']=safe_error(error)
            coverage.append(info)
            print(json.dumps({'source':source['id'],'status':info['status'],'collected':info['collected'],'accepted':info['accepted'],'error':info['error']},ensure_ascii=False),flush=True)
        config.pop('_directory',None)
        unique,duplicates=deduplicate(items)
        analysis_config={**config,'_period_start':period_start}
        summary=analyze(unique,analysis_config,coverage,duplicates,previous,directory)
        usable=sum(x['status'] in ('ok','partial') for x in coverage)
        ok=sum(x['status']=='ok' for x in coverage);enabled=sum(x['status']!='disabled' for x in coverage)
        run.update(status='success' if ok==enabled and enabled else 'partial' if usable else 'failed',finished_at=datetime.now(timezone.utc).isoformat(),
          requests=client.requests,pages=client.pages,cache_hits=client.cache_hits,geography_error=geo_error,dictionary_version=DICTIONARY['version'])
        # LLM absence is explicit. Facts remain usable; no generated conclusions substitute missing data.
        if config.get('llm',{}).get('enabled'):
            from src.analysis.llm import enrich
            run['llm_status'],run['api_spend']=enrich(unique,config,client)
            run['requests']=client.requests
        db=sqlite3.connect(state/'research.sqlite')
        db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS observations (run_id TEXT, id TEXT, payload TEXT, PRIMARY KEY(run_id,id))')
        db.execute('INSERT OR REPLACE INTO runs VALUES (?,?)',(run_id,json.dumps(run,ensure_ascii=False)))
        db.execute('DELETE FROM observations WHERE run_id=?',(run_id,))
        db.executemany('INSERT INTO observations VALUES (?,?,?)',[(run_id,o.observation_id,json.dumps(o.dict(),ensure_ascii=False)) for o in unique]);db.commit();db.close()
        history_file=state/'history.json'
        history=json.loads(history_file.read_text()) if history_file.exists() else (previous or {}).get('history',[])
        history=[h for h in history if h['run']['id']!=run_id]
        history.append({'run':run,'coverage':coverage,'summary':summary});history=history[-30:]
        atomic_write(history_file,json.dumps(history,ensure_ascii=False))
        geo_public=directory.payload if directory else {'regions':[],'provider':None,'error':geo_error}
        payload={'schema_version':2,'run':run,'coverage':coverage,'summary':summary,'geography_directory':geo_public,
          'observations':[o.dict() for o in unique],'history':history}
        publish(payload,state/'runs'/f'{run_id}.json');publish(payload,Path(output).parent/'attempt.json')
        if usable:publish(payload,output);publish(payload,state/'last-success.json')
        elif not Path(output).exists():publish(payload,output)
        print(json.dumps({'run_id':run_id,'status':run['status'],'verified_sources':ok,'minimum_ready':summary['minimum_ready'],
          'observations':len(unique),'federal_observations':summary['federal_observations'],'report':str(state/'runs'/f'{run_id}.json')},ensure_ascii=False))
        return 0 if run['status']=='success' else 2

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default=str(ROOT/'config/research.json'));parser.add_argument('--state',default=str(ROOT/'.state'))
    parser.add_argument('--output',default=str(ROOT/'web/public/data/latest.json'));parser.add_argument('--resume')
    for name in ('days','compare-days','max-requests','max-pages','max-seconds','per-region-observations','per-source-pages','per-source-requests'):parser.add_argument('--'+name,type=int)
    parser.add_argument('--max-api-budget',type=float);parser.add_argument('--mode',choices=sorted(MODES))
    for name in ('regions','cities','industries','segments','services','groups'):parser.add_argument('--'+name)
    args=parser.parse_args();config=json.loads(Path(args.config).read_text())
    for name in ('days','compare_days','max_requests','max_pages','max_seconds','per_region_observations','per_source_pages','per_source_requests','max_api_budget','mode'):
        if getattr(args,name) is not None:config[name]=getattr(args,name)
    for name in ('regions','cities','industries','segments','services','groups'):
        if getattr(args,name) is not None:config[name]=[x.strip() for x in getattr(args,name).split(',') if x.strip()]
    return execute(config,args.state,args.output,args.resume)
if __name__=='__main__':raise SystemExit(main())
