import os
from pathlib import Path
from templater import Templater, TemplaterVariable

vars = []
vars.append(TemplaterVariable('path', ['/tmp/dataset', '/tmp/datasetx']))
vars.append(TemplaterVariable('resolutions', [768, 1024], disable=True))

t = Templater('zimage', 'dataset', variant='turbo', vars_list=vars, use_generics=True)
t.save()

t = Templater('zimage', 'diffpipe', variant='turbo', vars_list=[], use_generics=True)
t.save()
