import json
import time
import hashlib
import urllib.request
import urllib.error
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit, urljoin

AGENT='RussiaDemandResearch/0.2 (+https://github.com/akaemov/ai-intelligence-service-arc)'
ALLOWED={'api.hh.ru','www.bashinform.ru','bashinform.ru','rssexport.rbc.ru','zakupki.gov.ru','workspace.ru','www.b2b-center.ru','www.fl.ru','www.weblancer.net','trudvsem.ru','opendata.trudvsem.ru','api.openai.com'}
class LimitedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.has_header('Authorization') and urlsplit(newurl).hostname!=urlsplit(req.full_url).hostname:raise ValueError('Authenticated cross-host redirect denied')
        if urlsplit(newurl).scheme != 'https' or urlsplit(newurl).hostname not in ALLOWED:
            raise ValueError('Redirect destination not approved')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class Client:
    def __init__(self, config, cache):
        self.config=config; self.cache=Path(cache); self.cache.mkdir(parents=True,exist_ok=True)
        self.started=time.monotonic(); self.requests=0; self.pages=0; self.last=0; self.robots={}
        self.source=None;self.source_requests=0;self.source_pages=0;self.cache_hits=0
        self.opener=urllib.request.build_opener(LimitedRedirect())
    def begin_source(self,source):
        self.source=source;self.source_requests=0;self.source_pages=0
    def get(self,url, page=False, headers=None):
        u=urlsplit(url)
        if u.scheme!='https' or u.hostname not in ALLOWED or u.username or u.password:
            raise ValueError('Unsupported destination')
        if page and (self.pages >= self.config['max_pages'] or self.source_pages>=self.config.get('per_source_pages',999)): raise RuntimeError('Page limit exhausted')
        key=self.cache/hashlib.sha256(url.encode()).hexdigest()
        if key.exists() and time.time()-key.stat().st_mtime < 3600:
            self.cache_hits+=1
            if page:self.pages+=1;self.source_pages+=1
            return key.read_bytes()
        for attempt in range(3):
            elapsed=time.monotonic()-self.started
            if self.requests>=self.config['max_requests'] or self.source_requests>=self.config.get('per_source_requests',999) or elapsed >= self.config['max_seconds']:
                raise RuntimeError('Request/time limit exhausted')
            delay=max(0,1-(time.monotonic()-self.last)) + (2**attempt if attempt else 0)
            if elapsed+delay>=self.config['max_seconds']: raise RuntimeError('Time limit exhausted')
            time.sleep(delay)
            self.requests+=1;self.source_requests+=1; self.last=time.monotonic()
            try:
                with self.opener.open(urllib.request.Request(url,headers={'User-Agent':AGENT,'HH-User-Agent':AGENT,'Accept':'application/json, application/rss+xml, text/html',**(headers or {})}),timeout=min(12,max(0.1,self.config['max_seconds']-(time.monotonic()-self.started)))) as r:
                    body=r.read(10_000_001)
                    if len(body)>10_000_000: raise ValueError('Response exceeds 10 MB')
                key.write_bytes(body)
                if page:self.pages+=1;self.source_pages+=1
                return body
            except urllib.error.HTTPError as e:
                if e.code not in (429,500,502,503,504) or attempt==2: raise
            except urllib.error.URLError as e:
                if '403' in str(e) or attempt==2: raise
        raise RuntimeError('Retry exhausted')
    def allowed(self,url):
        u=urlsplit(url); root=f'{u.scheme}://{u.netloc}'
        if root not in self.robots:
            try:
                content=self.get(root+'/robots.txt').decode('utf-8')
                rp=urllib.robotparser.RobotFileParser(); rp.parse(content.splitlines()); self.robots[root]=rp
            except urllib.error.HTTPError as e:
                if e.code==404:
                    rp=urllib.robotparser.RobotFileParser(); rp.parse([]); self.robots[root]=rp
                else: raise
        if not self.robots[root].can_fetch(AGENT,url): raise PermissionError('robots.txt disallows collection')
        return True
