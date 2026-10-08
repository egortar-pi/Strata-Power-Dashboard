#!/usr/bin/env python3
"""Local AI power and tokens dashboard. Python standard library only."""
import argparse, json, os, sqlite3, subprocess, threading, time, urllib.request, urllib.error, pathlib, datetime, math
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT=pathlib.Path(os.environ.get('AI_DASH_DIR',str(pathlib.Path.home()/'.local/share/ai-power-dashboard')))
DB=ROOT/'history.sqlite3'; HTML=pathlib.Path(__file__).with_name('index.html')
LOCK=threading.RLock()
DEFAULT={
 'electricity_price':0.25,'currency':'EUR',
 'cpu_idle_w':25,'cpu_busy_w':110,'board_other_w':55,'psu_efficiency':0.88,
 'strata_url':'http://127.0.0.1:8080/metrics',
 'input_path':'totals.prompt_tokens','output_path':'totals.output_tokens',
 'api_input_per_million':3.0,'api_output_per_million':15.0,
 'sample_seconds':5
}
# CPU busy watt is an adjustable estimate; Intel's 140W TDP is not metered draw.
PATHS_IN=['total_input_tokens','input_tokens','tokens.input','tokens.prompt','usage.prompt_tokens','usage.input_tokens','totals.prompt_tokens','total_prompt_tokens','prompt_tokens','stats.total_prompt_tokens','requests.prompt_tokens']
PATHS_OUT=['total_output_tokens','output_tokens','tokens.output','tokens.generated','usage.completion_tokens','usage.output_tokens','totals.output_tokens','totals.completion_tokens','total_completion_tokens','completion_tokens','generated_tokens','stats.total_generated_tokens','requests.completion_tokens']

def con():
 c=sqlite3.connect(DB,timeout=30); c.row_factory=sqlite3.Row; c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA busy_timeout=30000'); return c

def init():
 ROOT.mkdir(parents=True,exist_ok=True)
 with con() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS samples(ts REAL PRIMARY KEY,cpu_usage REAL,gpu_w REAL,system_w REAL,gpu_kwh_delta REAL,system_kwh_delta REAL,strata_ok INTEGER, input_delta INTEGER,output_delta INTEGER,error TEXT);
  CREATE TABLE IF NOT EXISTS gpus(ts REAL NOT NULL,uuid TEXT NOT NULL,name TEXT,idx INTEGER,watts REAL,util REAL,mem_used REAL,mem_total REAL,kwh_delta REAL NOT NULL,PRIMARY KEY(ts,uuid));
  CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT);''')
  cols={r[1] for r in c.execute('PRAGMA table_info(samples)')}
  if 'cached_delta' not in cols:c.execute('ALTER TABLE samples ADD COLUMN cached_delta INTEGER NOT NULL DEFAULT 0')
  for k,v in DEFAULT.items(): c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',(k,json.dumps(v)))

def settings(c):
 data={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}
 return {**DEFAULT,**data}

def state(c,k):
 r=c.execute('SELECT value FROM state WHERE key=?',(k,)).fetchone();return json.loads(r['value']) if r else None

def setstate(c,k,v):c.execute('INSERT OR REPLACE INTO state VALUES(?,?)',(k,json.dumps(v)))

def numeric(v):
 try:
  n=float(str(v).replace(' W','').replace(' MiB','').strip());return n if math.isfinite(n) else None
 except (ValueError,TypeError): return None

def gpu_read():
 fields='index,uuid,name,power.draw,utilization.gpu,memory.used,memory.total'
 out=subprocess.run(['nvidia-smi',f'--query-gpu={fields}','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8,check=True).stdout
 gpu=[]
 for line in out.splitlines():
  parts=[x.strip() for x in line.split(',')]
  if len(parts)<7:continue
  idx,uuid,name,pw,ut,mem,tot=parts[:7]
  gpu.append(dict(idx=int(idx),uuid=uuid,name=name,watts=numeric(pw),util=numeric(ut),mem_used=numeric(mem),mem_total=numeric(tot)))
 return gpu

def cpu_read():
 with open('/proc/stat') as f: parts=list(map(int,f.readline().split()[1:]))
 idle=parts[3]+parts[4];total=sum(parts);return [idle,total]

def traverse(data,path):
 if not path:return None
 cur=data
 for component in path.split('.'):
  if isinstance(cur,dict):cur=cur.get(component)
  elif isinstance(cur,list) and component.isdigit() and int(component)<len(cur):cur=cur[int(component)]
  else:return None
 return numeric(cur)

def find_tokens(obj,candidates):
 for k in candidates:
  val=traverse(obj,k)
  if val is not None:return int(val),k
 return None,None

def fetch_metrics(cfg):
 request=urllib.request.Request(cfg['strata_url'],headers={'Accept':'application/json'})
 with urllib.request.urlopen(request,timeout=3) as r: return json.load(r)

def collector_once():
 ts=time.time();err=[]
 with LOCK,con() as c:
  cfg=settings(c)
  try:gpu=gpu_read()
  except Exception as e:gpu=[];err.append('nvidia-smi: '+str(e)[:160])
  try:
   cp=cpu_read(); prev=state(c,'cpu_prev'); setstate(c,'cpu_prev',cp)
   usage=max(0,min(1,1-(cp[0]-prev[0])/(cp[1]-prev[1]))) if prev and cp[1]>prev[1] else 0
  except Exception as e:usage=0;err.append('CPU: '+str(e)[:160])
  prev=state(c,'last_sample')
  # Missing intervals are deliberately not interpolated beyond 2 sample periods.
  delta=max(0,min(ts-prev['ts'],float(cfg['sample_seconds'])*2)) if prev else 0
  gpu_valid=bool(gpu) and all(x['watts'] is not None for x in gpu)
  if not gpu_valid:err.append('GPU power unavailable: system energy/cost sampling paused')
  gpu_w=sum(x['watts'] for x in gpu if x['watts'] is not None)
  cpu_w=float(cfg['cpu_idle_w'])+usage*(float(cfg['cpu_busy_w'])-float(cfg['cpu_idle_w']))
  system_w=(gpu_w+cpu_w+float(cfg['board_other_w']))/max(0.5,float(cfg['psu_efficiency']))
  gpu_e=0;oldgpu=prev.get('gpus',{}) if prev else {}
  for x in gpu:
   old=oldgpu.get(x['uuid']); watt=x['watts']
   energy=max(0,(watt+old)/2*delta/3600000) if old is not None and watt is not None else 0
   gpu_e+=energy
   c.execute('INSERT INTO gpus VALUES(?,?,?,?,?,?,?,?,?)',(ts,x['uuid'],x['name'],x['idx'],watt,x['util'],x['mem_used'],x['mem_total'],energy))
  sys_e=(system_w+prev['system_w'])/2*delta/3600000 if prev and gpu_valid and prev.get('gpu_valid') else 0
  setstate(c,'last_sample',dict(ts=ts,system_w=system_w,gpu_valid=gpu_valid,gpus={x['uuid']:x['watts'] for x in gpu}))
  i_delta=o_delta=cached_delta=0;ok=0
  try:
   metrics=fetch_metrics(cfg)
   i,ip=find_tokens(metrics,[cfg['input_path']]+PATHS_IN)
   o,op=find_tokens(metrics,[cfg['output_path']]+PATHS_OUT)
   cached,_=find_tokens(metrics,['totals.reused'])
   if i is None and o is None:err.append('Strata: token counters not found; configure JSON paths')
   else:
    ok=1
    for name,val in [('input',i),('output',o),('cached',cached)]:
     if val is None:continue
     old=state(c,'strata_'+name)
     # Reset means establish a new baseline; avoid attributing totals to a previous sampling window.
     gain=max(0,val-old) if old is not None and val>=old else 0
     if name=='input':i_delta=gain
     elif name=='output':o_delta=gain
     else:cached_delta=gain
     setstate(c,'strata_'+name,val)
    setstate(c,'strata_detected',{'input':ip,'output':op})
  except Exception as e:err.append('Strata: '+str(e)[:160])
  c.execute('INSERT INTO samples(ts,cpu_usage,gpu_w,system_w,gpu_kwh_delta,system_kwh_delta,strata_ok,input_delta,output_delta,error,cached_delta) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ts,usage,gpu_w,system_w if gpu_valid else None,gpu_e,sys_e,ok,i_delta,o_delta,'; '.join(err),cached_delta))

def aggregate(c,period):
 since={'24h':time.time()-86400,'7d':time.time()-604800,'30d':time.time()-2592000,'all':0}.get(period,time.time()-86400)
 r=c.execute('SELECT COALESCE(SUM(gpu_kwh_delta),0) gpu_kwh, COALESCE(SUM(system_kwh_delta),0) system_kwh,COALESCE(SUM(input_delta),0) inputs,COALESCE(SUM(output_delta),0) outputs,COALESCE(SUM(cached_delta),0) cached,COUNT(*) n FROM samples WHERE ts>=?',(since,)).fetchone()
 cfg=settings(c)
 return dict(r)|dict(energy_cost=r['system_kwh']*float(cfg['electricity_price']),api_equivalent=(r['inputs']*float(cfg['api_input_per_million'])+r['outputs']*float(cfg['api_output_per_million']))/1e6,period=period)

def snapshot(period):
 with LOCK,con() as c:
  cfg=settings(c);agg=aggregate(c,period)
  last=c.execute('SELECT * FROM samples ORDER BY ts DESC LIMIT 1').fetchone()
  gpu=[]
  if last:
   gpu=[dict(x) for x in c.execute('SELECT * FROM gpus WHERE ts=? ORDER BY idx',(last['ts'],))]
  since={'24h':time.time()-86400,'7d':time.time()-604800,'30d':time.time()-2592000,'all':0}.get(period,time.time()-86400)
  rows=c.execute('SELECT ts,gpu_w,system_w,input_delta,output_delta,system_kwh_delta FROM samples WHERE ts>=? ORDER BY ts',(since,)).fetchall()
  # Graph bucketing caps payload for long histories.
  n=max(1,math.ceil(len(rows)/400));chart=[]
  for off in range(0,len(rows),n):
   group=rows[off:off+n]
   chart.append(dict(ts=group[-1]['ts'],gpu_w=sum(r['gpu_w'] for r in group)/len(group),system_w=sum(r['system_w'] for r in group)/len(group),input=sum(r['input_delta'] for r in group),output=sum(r['output_delta'] for r in group),kwh=sum(r['system_kwh_delta'] for r in group)))
  per_gpu=[dict(r) for r in c.execute('SELECT uuid,MAX(name) name, SUM(kwh_delta) kwh,MAX(watts) peak FROM gpus WHERE ts>=? GROUP BY uuid',(since,))]
  return dict(config=cfg,totals=agg,latest=dict(last) if last else None,gpus=gpu,per_gpu=per_gpu,chart=chart,detected=state(c,'strata_detected'))

class Handler(BaseHTTPRequestHandler):
 def answer(self,data,status=200):
  raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  p=urlparse(self.path)
  if p.path=='/api/data':return self.answer(snapshot(parse_qs(p.query).get('period',['24h'])[0]))
  if p.path=='/api/health':return self.answer({'status':'ok'})
  if p.path=='/':
   raw=HTML.read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
  self.send_error(404)
 def do_POST(self):
  if urlparse(self.path).path!='/api/settings':return self.send_error(404)
  # Reject cross-origin browser requests, require JSON; localhost SSH tunnel is intended access.
  origin=self.headers.get('Origin','');host=self.headers.get('Host','')
  if origin and urlparse(origin).netloc!=host:return self.answer({'error':'origin mismatch'},403)
  if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.answer({'error':'JSON required'},415)
  try:
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<10000:raise ValueError('invalid length')
   data=json.loads(self.rfile.read(size))
   with LOCK,con() as c:
    for k,v in data.items():
     if k not in DEFAULT:continue
     if isinstance(DEFAULT[k],(int,float)):
      v=float(v)
      if not math.isfinite(v) or v<0 or v>100000:raise ValueError('Invalid '+k)
     elif not isinstance(v,str) or len(v)>1000:raise ValueError('Invalid '+k)
     if k=='currency' and v not in ('EUR','USD','GBP','PLN','UAH','CHF','CZK','SEK','NOK','DKK'):raise ValueError('Unsupported currency')
     if k=='strata_url' and (not v.startswith(('http://127.0.0.1:','http://localhost:'))):raise ValueError('Strata URL must be loopback (127.0.0.1 or localhost)')
     if k=='psu_efficiency' and not 0.5<=v<=1:raise ValueError('PSU efficiency must be 0.5–1')
     if k=='sample_seconds' and not 2<=v<=60:raise ValueError('Sample seconds 2–60')
     c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,json.dumps(v)))
   return self.answer({'ok':True})
  except Exception as e:return self.answer({'error':str(e)},400)
 def log_message(self,fmt,*args):pass

def run():
 init()
 def worker():
  while True:
   try:collector_once()
   except Exception as e:print('collector error:',e,flush=True)
   with con() as c:secs=float(settings(c)['sample_seconds'])
   time.sleep(secs)
 threading.Thread(target=worker,daemon=True).start()
 host=os.environ.get('AI_DASH_HOST','127.0.0.1');port=int(os.environ.get('AI_DASH_PORT','8092'))
 print(f'Dashboard http://{host}:{port}',flush=True)
 ThreadingHTTPServer((host,port),Handler).serve_forever()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('command',nargs='?',default='serve',choices=['serve','report','sample']);parser.add_argument('--period',default='24h');args=parser.parse_args()
 init()
 if args.command=='sample':collector_once();print(json.dumps(snapshot(args.period)['latest'],indent=2))
 elif args.command=='report':print(json.dumps(snapshot(args.period)['totals'],indent=2))
 else:run()
