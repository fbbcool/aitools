import os
from pathlib import Path
from templater import Templater, TemplaterVariable

vars = []
vars.append(TemplaterVariable('path', ['/tmp/dataset', '/tmp/datasetx']))
vars.append(TemplaterVariable('resolutions', [768, 1024], disable=True))

url = '/home/misw/venv/aitools/aitools/conf/diffpipe'
name = 'dataset'
t = Templater(name, url, vars_list=vars)
print(t.get_string)
workspace = Path(os.environ['WORKSPACE'])
t.save(workspace)
