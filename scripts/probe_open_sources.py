"""Inspect publicly permitted sources; emit metadata only, never profiles or contacts."""
import json,urllib.request,urllib.robotparser,urllib.error,sys
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.collectors.dom import DOM
AGENT='RussiaDemandResearch/0.2 (+https://github.com/akaemov/ai-intelligence-service-arc)'
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':AGENT}),timeout=15) as r:
        body=r.read(6000001)
        if len(body)>6000000:raise ValueError('Oversize response')
        return body.decode('utf-8','replace')
def probe(base):
    result={'url':base}
    try:
        rp=urllib.robotparser.RobotFileParser()
        try:rp.parse(get(urljoin(base,'/robots.txt')).splitlines())
        except urllib.error.HTTPError as e:
            if e.code==404:rp.parse([])
            else:raise
        result['allowed']=rp.can_fetch(AGENT,base)
        if not result['allowed']:return result
        tree=DOM(get(base)).root
        feeds=[urljoin(base,n.attrs['href']) for n in tree.nodes('link') if 'rss' in n.attrs.get('type','') and n.attrs.get('href')]
        feeds+=[urljoin(base,n.attrs['href']) for n in tree.nodes('a') if 'rss' in n.attrs.get('href','').lower()]
        result['title']=[n.text()[:100] for n in tree.nodes('title')][:1]
        result['feeds']=[]
        for url in list(dict.fromkeys(feeds))[:3]:
            if urlsplit(url).hostname!=urlsplit(base).hostname:continue
            info={'url':url,'allowed':rp.can_fetch(AGENT,url)}
            if info['allowed']:
                try:
                    xml=ET.fromstring(get(url));items=xml.findall('.//item');info['items']=len(items)
                    info['fields']=list(dict.fromkeys(n.tag for item in items[:2] for n in item))
                except Exception as e:info['error']=type(e).__name__
            result['feeds'].append(info)
        result['indexes']=[urljoin(base,n.attrs['href']) for n in tree.nodes('a') if 'projects' in n.attrs.get('href','')][:3]
    except Exception as e:result['error']=type(e).__name__+(' HTTP '+str(e.code) if hasattr(e,'code') else '')
    return result
for base in ['https://habr.com/ru/','https://freelance.ru/','https://www.cnews.ru/']:
    result=json.dumps(probe(base),ensure_ascii=False)
    print('::notice title=Open source probe::'+result.replace('%','%25').replace('\r','%0D').replace('\n','%0A'),flush=True)
