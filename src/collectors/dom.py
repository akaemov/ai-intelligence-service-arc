"""Small inert HTML tree. Scripts are data, never executed."""
from dataclasses import dataclass,field
from html.parser import HTMLParser
@dataclass
class Node:
    tag:str
    attrs:dict=field(default_factory=dict)
    children:list=field(default_factory=list)
    parent:object=None
    def text(self):return ' '.join(x if isinstance(x,str) else x.text() for x in self.children if isinstance(x,str) or x.tag not in ('script','style')).strip()
    def nodes(self,tag=None):
        result=[]
        for child in self.children:
            if isinstance(child,Node):
                if tag is None or child.tag==tag:result.append(child)
                result.extend(child.nodes(tag))
        return result
    def has_class(self,value):return value in self.attrs.get('class','').split()
class DOM(HTMLParser):
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self,body):
        super().__init__(convert_charrefs=True);self.root=Node('root');self.stack=[self.root];self.feed(body)
    def handle_starttag(self,tag,attrs):
        node=Node(tag,dict(attrs),parent=self.stack[-1]);self.stack[-1].children.append(node)
        if tag not in self.VOID:self.stack.append(node)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.VOID:self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):self.stack[-1].children.append(data)
