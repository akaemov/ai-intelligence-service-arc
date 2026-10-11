import csv
import io
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
from src.models import PRIVATE

TOKEN=re.compile(r'(?i)(?:gh[pousr]_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,}|sk-[a-z0-9_-]{16,}|(?:api[_-]?key|access[_-]?token|password|secret)\s*[=:]\s*[^\s,\"}]{6,})')
def privacy_check(payload):
    def inspect(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in ('raw_content','full_text','email','phone','private_profile'):raise ValueError('Private field in export')
                inspect(v)
        elif isinstance(value,list):
            for v in value:inspect(v)
        elif isinstance(value,str):
            if PRIVATE.search(value) or TOKEN.search(value):raise ValueError('Public export failed privacy gate')
            if value.startswith(('http://','https://')):
                url=urlsplit(value)
                if url.username or url.password or any(k.lower() in ('token','key','api_key','access_token','email','phone') for k,v in parse_qsl(url.query)):
                    raise ValueError('Unsafe public URL')
    inspect(payload)
    for key in ('LLM_API_KEY','GH_TOKEN','GITHUB_TOKEN','HH_TOKEN'):
        secret=os.environ.get(key)
        if secret and len(secret)>=12 and secret in json.dumps(payload,ensure_ascii=False):raise ValueError('Runtime secret in export')

def atomic_write(path,body):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.pending-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(body);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def to_csv(observations):
    out=io.StringIO()
    keys=list(observations[0]) if observations else ['observation_id','source_url','title','signal_type']
    writer=csv.DictWriter(out,fieldnames=keys);writer.writeheader()
    for row in observations:
        clean={k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()}
        for k,v in clean.items():
            if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')):clean[k]="'"+v
        writer.writerow(clean)
    return out.getvalue()

def publish(payload,path):
    privacy_check(payload)
    atomic_write(path,json.dumps(payload,ensure_ascii=False,indent=2))
