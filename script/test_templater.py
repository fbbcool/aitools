import os
from pathlib import Path
from templater import Templater, TemplaterVariable

vars = []
vars.append(TemplaterVariable('path', ['/tmp/dataset', '/tmp/datasetx']))
vars.append(TemplaterVariable('resolutions', [768, 1024], disable=True))

t = Templater('dataset', 'zimage', variant='turbo', vars_list=vars)
t.save()

t = Templater('diffpipe', 'zimage', variant='turbo', vars_list=[])
t.save()
