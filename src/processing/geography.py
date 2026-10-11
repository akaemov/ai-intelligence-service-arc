"""Provider-specific geography. Never interchange HH IDs with other codes."""
import json
from datetime import datetime,timezone
from pathlib import Path
from src.models import digest

def key(value):return ' '.join(value.casefold().replace('ё','е').split())
class Directory:
    def __init__(self,payload):
        self.payload=payload;self.regions=payload['regions'];self.locations={}
        for r in self.regions:
            for city in [r,*r.get('cities',[])]:
                self.locations.setdefault(key(city['name']),[]).append((r['name'],city['name']))
    def resolve(self,name):
        matches=self.locations.get(key(name),[])
        distinct=set(matches)
        return next(iter(distinct)) if len(distinct)==1 else None
    def region(self,name):
        names=[r['name'] for r in self.regions if key(r['name'])==key(name)]
        return names[0] if len(names)==1 else None
    def area_id(self,region):
        return next((r['provider_id'] for r in self.regions if r['name']==region),None)

def build_directory(areas):
    root=next((r for r in areas if r['name']=='Россия'),None)
    if not root:raise ValueError('Russia absent from provider directory')
    regions=[]
    def flatten(nodes):
        result=[]
        for n in nodes:
            result.append({'name':n['name'],'provider_id':n['id']});result.extend(flatten(n.get('areas',[])))
        return result
    for node in root.get('areas',[]):
        regions.append({'name':node['name'],'provider_id':node['id'],'federal_district':None,'cities':flatten(node.get('areas',[]))})
    return {'provider':'hh','source_url':'https://api.hh.ru/areas','fetched_at':datetime.now(timezone.utc).isoformat(),
            'content_hash':digest(json.dumps(areas,sort_keys=True,ensure_ascii=False)),'country':'Россия','country_provider_id':root['id'],
            'code_system':'HH area IDs, not FIAS/OKATO','district_status':'authoritative mapping not connected','regions':regions}

def load_directory(client,state):
    path=Path(state)/'geography.json'
    try:
        payload=build_directory(json.loads(client.get('https://api.hh.ru/areas')))
        path.write_text(json.dumps(payload,ensure_ascii=False))
        return Directory(payload),None
    except Exception as error:
        if path.exists():return Directory(json.loads(path.read_text())), 'Использован сохранённый справочник; актуальность требует повторной проверки'
        return None,type(error).__name__+': справочник географии недоступен; региональные показатели ограничены'
