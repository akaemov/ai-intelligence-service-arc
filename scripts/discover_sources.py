"""Non-destructive source discovery; public logs contain metadata, not full pages."""
import json,re,time,urllib.request,urllib.robotparser,urllib.error
from urllib.parse import urljoin,urlsplit
from html.parser import HTMLParser
AGENT='RussiaDemandResearch/0.2 (+https://github.com/akaemov/ai-intelligence-service-arc)'
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.classes={};self.href=None;self.text=[];self.meta={}
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  for c in a.get('class','').split():self.classes[c]=self.classes.get(c,0)+1
  if tag=='a':self.href=a.get('href');self.text=[]
  if tag=='meta' and a.get('property'):self.meta[a['property']]=a.get('content','')[:150]
 def handle_data(self,t):
  if self.href:self.text.append(t)
 def handle_endtag(self,tag):
  if tag=='a' and self.href:self.links.append((self.href,' '.join(self.text).strip()));self.href=None

def get(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':AGENT}),timeout=15) as r:
  body=r.read(6_000_001)
  if len(body)>6_000_000:raise ValueError('response too large')
  return r.status,body.decode('utf-8','replace')

def inspect(base):
 report={'url':base}
 try:
  rp=urllib.robotparser.RobotFileParser()
  try:status,robots=get(urljoin(base,'/robots.txt'));rp.parse(robots.splitlines())
  except urllib.error.HTTPError as e:
   if e.code==404:rp.parse([])
   else:raise
  report['home_allowed']=rp.can_fetch(AGENT,base)
  if not report['home_allowed']:return report
  status,text=get(base);p=Parser();p.feed(text);report['http']=status
  candidates=[]
  for href,title in p.links:
   url=urljoin(base,href)
   if urlsplit(url).hostname==urlsplit(base).hostname and re.search(r'tenders|market|jobs|projects|opendata|api',href,re.I):
    if url not in candidates:candidates.append(url)
  report['discovered_links']=candidates[:12]
  # Follow first public index discovered in homepage HTML, not guessed paths.
  for u in candidates[:2]:
   allowed=rp.can_fetch(AGENT,u);entry={'url':u,'allowed':allowed}
   if allowed:
    time.sleep(1);status,body=get(u);q=Parser();q.feed(body)
    entry.update(http=status,classes=sorted(q.classes.items(),key=lambda x:-x[1])[:35],
      links=[urljoin(u,h) for h,t in q.links if re.search(r'tender|market|jobs|projects|opendata',h,re.I)][:20],
      metadata=q.meta,challenge=bool(re.search(r'<title>[^<]*(captcha|access denied|just a moment)',body,re.I)))
   report.setdefault('pages',[]).append(entry)
 except Exception as e:report['error']=type(e).__name__+(' HTTP '+str(e.code) if hasattr(e,'code') else '')
 return report
for base in ['https://workspace.ru/','https://www.b2b-center.ru/','https://www.fl.ru/','https://www.weblancer.net/','https://trudvsem.ru/']:
 print(json.dumps(inspect(base),ensure_ascii=False),flush=True)
