"""Run a trusted project script with ignored local Langfuse configuration."""
import os,runpy,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for line in (root/'.env.langfuse').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key,value=line.split('=',1)
        if key.startswith('LANGFUSE_'):os.environ[key]=value.strip().strip('"').strip("'")
target=(root/sys.argv[1]).resolve()
if not target.is_relative_to(root):raise SystemExit('Script must be inside this lab')
sys.argv=sys.argv[1:];sys.path.insert(0,str(target.parent));runpy.run_path(str(target),run_name='__main__')
