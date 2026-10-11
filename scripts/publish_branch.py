"""Publish an explicitly approved, validated public directory without a worktree."""
import argparse,json,os,re,subprocess,tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.publishing.export import privacy_check

def publish_directory(directory,branch,message):
    directory=Path(directory).resolve()
    if branch not in ('gh-pages','research-data'):raise ValueError('Unexpected publication branch')
    if not directory.is_dir():raise ValueError('Public directory missing')
    for p in directory.rglob('*'):
        if p.is_symlink():raise ValueError('Symlink in publication')
        if p.is_file():
            if p.suffix=='.json':privacy_check(json.loads(p.read_text()))
            if p.suffix in ('.sqlite','.db') or p.name in ('.env','run.lock'):raise ValueError('Private state in publication')
    # Only approved directory content enters a temporary Git index.
    with tempfile.TemporaryDirectory(prefix='public-index-') as temp:
        context=os.environ.copy();context['GIT_INDEX_FILE']=str(Path(temp)/'index')
        subprocess.run(['git','--work-tree='+str(directory),'add','--all'],env=context,check=True)
        tree=subprocess.check_output(['git','write-tree'],env=context,text=True).strip()
        remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/'+branch],text=True).strip()
        args=['git','commit-tree',tree]
        if remote:
            subprocess.run(['git','fetch','origin',branch],check=True)
            parent=subprocess.check_output(['git','rev-parse','FETCH_HEAD'],text=True).strip();args+=['-p',parent]
        commit=subprocess.check_output(args,input=message+'\n',text=True).strip()
        subprocess.run(['git','update-ref','refs/heads/'+branch,commit],check=True)
        subprocess.run(['git','push','origin',branch],check=True)
        print('PUBLIC_BRANCH_COMMIT:',branch,commit)
        return commit
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('branch');parser.add_argument('--message',default='Publish verified public research output')
    args=parser.parse_args();publish_directory(args.directory,args.branch,args.message)
