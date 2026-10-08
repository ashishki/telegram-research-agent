"""Reproduce native76 allegation using exactly its committed stream-reader function."""
import ast,io,json,subprocess,time
from typing import Any
from types import SimpleNamespace
commit='c4b689b03c5fc38070e87e57e85543c68b58e90d'
source=subprocess.check_output(['git','show',commit+':tools/mimo_code_review.py'],text=True)
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='_read_review_stream')
namespace={'time':time,'json':json,'Any':Any}
exec(compile(ast.Module(body=[node],type_ignores=[]),'captured_native76_stream','exec'),namespace)
content=json.dumps({'verdict':'ADVISORY','findings':[],'summary':'Synthetic complete verdict','not_verified':[]})
event={'model':'mimo-v2.6-pro','choices':[{'index':0,'delta':{'content':content},'finish_reason':None}]}
for kind in ('empty','json_only','json_and_stop'):
 events=[] if kind=='empty' else [event]
 if kind=='json_and_stop':events.append({'model':'mimo-v2.6-pro','choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})
 wire=b''.join(b'data: '+json.dumps(e).encode()+b'\n\n' for e in events)
 data=io.BytesIO(wire);reads=[]
 def readline(limit):
  line=data.readline(limit);reads.append(len(line));return line
 http=SimpleNamespace(readline=readline,fp=SimpleNamespace(raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=lambda value:None))))
 try:namespace['_read_review_stream'](http,'mimo-v2.6-pro',time.monotonic()+30)
 except ValueError as e:
  assert str(e)=='review_stream_incomplete' and e.review_stream_state['terminal_event']=='eof'
  assert e.review_stream_state['wire_bytes']==len(wire) and reads[-1]==0
  print(json.dumps({'reviewed_commit':commit,'case':kind,'result':'EOF denied','wire_bytes':len(wire),'read_lengths':reads,'state':e.review_stream_state}))
 else:raise AssertionError('Truncated stream accepted')
