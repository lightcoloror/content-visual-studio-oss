"""Thin local review feedback adapter. Synthetic preview only; no ledger writes.

Reuse outcome_feedback_link and platform_metrics_intake. Codex / GPT-6 Astra.
"""
from __future__ import annotations
import argparse,hashlib,hmac,json,math,os,secrets,sys,time
from datetime import datetime,timezone
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,HTTPServer
from urllib.parse import urlsplit
# This bounded local entrypoint never needs numerical-library parallelism.
for _key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS','BLIS_NUM_THREADS'):
    os.environ[_key]='1'
import human_voice_review as review
import serve as preview

# Public adaptation: explicit common workspace and registered native Owners.
# Import/--help neither loads another Owner nor starts a service.
W = None
_REGISTRY = None

def configure_workspace(root, registry=None):
    global W, _REGISTRY
    from registered_self_media import load_module
    resolved = Path(root).expanduser().resolve(strict=True)
    selected = Path(registry).expanduser().resolve() if registry else resolved/'tool-registry.json'
    owner = load_module('outcome_feedback_link', selected)
    native_metrics = load_module('platform_metrics_intake', selected)
    require(Path(owner.W).resolve() == resolved and Path(native_metrics.ROOT).resolve().parent == resolved,
            'workspace_owner_layout_mismatch')
    W, _REGISTRY = resolved, selected
    return resolved

class _NativeOwner:
    def __init__(self, name): self.name = name
    def __getattr__(self, name):
        require(W is not None and _REGISTRY is not None, 'workspace_root_required')
        from registered_self_media import load_module
        return getattr(load_module(self.name, _REGISTRY), name)

link = _NativeOwner('outcome_feedback_link')
metrics = _NativeOwner('platform_metrics_intake')

def now():return datetime.now(timezone.utc).isoformat()
def require(ok,code):
    if not ok:raise ValueError(code)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def exact(p,obj):
    link.persist(Path(p).parent,{Path(p).name:link.text(obj)})
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def workspace(p):
    require(W is not None,'workspace_root_required');p=Path(p).resolve();require(p.is_relative_to(W) and p!=W,'path_outside_workspace');return p

def prepare(bundle_path,candidates,output,imports):
    output=workspace(output);review.output_root(str(output/'site'));bundle_path=workspace(bundle_path);b=read(bundle_path);review.validate_bundle(b)
    require(not b.get('media') and all(c.get('synthetic_only') for c in b['candidates'].values()),'synthetic_only_required')
    rows=[]
    for key,path in candidates.items():
        require(key in b['candidates'],'unknown_candidate');p=workspace(path);c=read(p)
        require('synthetic-only' in c.get('tags',[]),'synthetic_only_required')
        accounts=c.get('operating_refs',{}).get('account_ids',[]);require(len(accounts)==1,'single_bound_account_required')
        binding=link.binding_for(p.relative_to(W).as_posix(),sha(p),accounts[0])
        require(c['title']==b['candidates'][key]['title'],'candidate_title_drift')
        require(c['channels']['article']['platform_metadata'].get('review_binding')==b['candidates'][key]['binding'],'review_binding_missing_or_stale')
        rows.append({'key':key,'title':c['title'],'review_binding':b['candidates'][key]['binding'],'binding':binding})
    require(bool(rows),'no_candidates')
    sources=[]
    for key,(profile,path) in imports.items():
        p=workspace(path);require(p.suffix=='.csv','preview_csv_only')
        cfg=metrics.load_json(metrics.MAPPING_PATH)['export_profiles'].get(profile,{})
        require(cfg.get('compatibility_status')=='template_only','preview_template_only')
        require('synthetic' in p.name.lower(),'synthetic_filename_required')
        value=metrics.build_intake({profile:p},now())
        sources.append({'key':key,'profile':profile,'path':str(p),'sha256':sha(p),'label':p.name,'rows':len(value['records'])})
    config={'schema_version':'content-feedback-preview.v1','synthetic_only':True,'bundle_sha256':b['bundle_sha256'],
        'bundle_path':str(bundle_path),'candidates':rows,'imports':sources}
    exact(output/'config.json',config)
    review.build_page(b,output/'site',W)
    return config

def validate_config(config):
    require(config.get('schema_version')=='content-feedback-preview.v1' and config.get('synthetic_only') is True,'synthetic_only_required')
    b=read(workspace(config['bundle_path']));review.validate_bundle(b);require(b['bundle_sha256']==config['bundle_sha256'],'stale_review_page')
    review.verify_sources(b,W)
    for row in config['candidates']:
        binding=row['binding'];require(link.binding_for(binding['candidate']['ref'],binding['candidate']['sha256'],binding['account_id'])==binding,'candidate_binding_drift')
        c=link.bound(binding['candidate']);require('synthetic-only' in c.get('tags',[]),'synthetic_only_required')
        require(b['candidates'][row['key']]['binding']==row['review_binding'] and c['channels']['article']['platform_metadata']['review_binding']==row['review_binding'],'stale_candidate_version')
    for row in config['imports']:
        p=workspace(row['path']);require(p.suffix=='.csv' and 'synthetic' in p.name.lower(),'preview_csv_only')
        cfg=metrics.load_json(metrics.MAPPING_PATH)['export_profiles'].get(row['profile'],{})
        require(cfg.get('compatibility_status')=='template_only','preview_template_only')
    return b

def minutes(value):
    require(value is None or type(value) in (int,float) and math.isfinite(value) and 0<=value<=1440,'invalid_minutes')
    return value

def submit(config,payload,output):
    validate_config(config);output=workspace(output)
    require(set(payload)=={'key','version','action','reason','minutes','baseline_minutes'},'feedback_shape')
    row=next((r for r in config['candidates'] if r['key']==payload['key']),None);require(row is not None,'unknown_candidate')
    require(payload['version']==row['binding']['candidate']['sha256'],'stale_candidate_version')
    action=payload['action'];require(action in {'adopt','edit','reject'},'invalid_action')
    reason=payload['reason'];require(isinstance(reason,str) and len(reason)<=1000,'invalid_reason')
    duration=minutes(payload['minutes']);baseline=minutes(payload['baseline_minutes'])
    require(action=='edit' or duration is None and baseline is None,'effort_requires_edit')
    require(action!='edit' or bool(reason.strip()),'rework_reason_required')
    link.tracker.reject_sensitive_keys(payload);link.cycle.reject_obvious_sensitive_values(payload)
    identity={'input':payload,'binding':row['binding'],'review_binding':row['review_binding'],'adapter_sha256':sha(Path(__file__)),'link_sha256':sha(Path(link.__file__))}
    event_id=link.tracker.canonical_sha256(identity);root=output/'feedback'/event_id
    duplicate=(root/'result.json').exists()
    # Immutable submission makes retries and partially written evidence resumable.
    if (root/'submission.json').exists():
        entry=read(root/'submission.json');require(entry['identity']==identity,'submission_drift');stamp=entry['submitted_at']
    else:
        stamp=now();exact(root/'submission.json',{'identity':identity,'submitted_at':stamp})
    binding=row['binding'];ids={k:binding[k] for k in ('content_id','closure_run_id','account_id')}
    decision={'adopt':'adopted','edit':'adopted_with_edits','reject':'discarded'}[action]
    event={**ids,'decision':decision,'decided_at':stamp}
    exact(root/'decision-evidence.json',event)
    event.update(edits=[],evidence={'ref':(root/'decision-evidence.json').relative_to(W).as_posix(),'sha256':sha(root/'decision-evidence.json')},time_saved_minutes=None,rework_reason=reason or None)
    if action=='edit':
        edit={'measurement_kind':'manual_duration_report','duration_seconds':None if duration is None else duration*60,'category':'manual_revision','reason':reason,'reported_at':stamp}
        exact(root/'edit-evidence.json',{**ids,**edit})
        event['edits']=[{**edit,'evidence':{'ref':(root/'edit-evidence.json').relative_to(W).as_posix(),'sha256':sha(root/'edit-evidence.json')}}]
    request={'schema_version':'content-outcome-feedback-input.v1','data_classification':'synthetic-only','submitted_at':stamp,'binding':binding,'outcome':event,'publication':None,'observations':[],'native_requests':[]}
    exact(root/'request.json',request)
    link.prepare(root/'request.json',sha(root/'request.json'),root/'native')
    native=read(root/'native/review-packet.json')
    require(native['publication'] is None and not native['observation_windows'] and not native['scheduled_tasks'],'publication_authority_drift')
    result={'event_id':event_id,'key':row['key'],'title':row['title'],'candidate_sha256':binding['candidate']['sha256'],
        'candidate_version':row['review_binding']['candidate_version'],'decision':decision,'reason':reason or 'unknown',
        'modification_minutes':duration,'effort_source':'manual_report' if duration is not None else 'unknown',
        'baseline_minutes':baseline,'time_saved_minutes':baseline-duration if baseline is not None and duration is not None else None,
        'savings_source':'manual_report_comparison' if baseline is not None and duration is not None else 'unknown',
        'publication':None,'scheduled_tasks':[],'synthetic_only':True,'status':'candidate_only','duplicate':False,
        'review_packet':str(root/'native/review-packet.json'),'recorded_at':stamp}
    exact(root/'result.json',result);return {**result,'duplicate':duplicate}

def import_local(config,key,output):
    validate_config(config);row=next((r for r in config['imports'] if r['key']==key),None);require(row is not None,'unknown_import')
    p=workspace(row['path']);require(sha(p)==row['sha256'],'source_hash_drift')
    identity={'profile':row['profile'],'sha256':sha(p),'mapping_sha256':sha(metrics.MAPPING_PATH),'adapter_sha256':sha(Path(metrics.__file__))}
    ident=link.tracker.canonical_sha256(identity);root=workspace(output)/'imports'/ident
    duplicate=(root/'result.json').exists()
    if (root/'intake.json').exists():value=read(root/'intake.json');metrics.validate_intake(value)
    else:value=metrics.build_intake({row['profile']:p},now());exact(root/'intake.json',value)
    result={'import_id':ident,'duplicate':False,'compatibility_status':'template_only','source_grain':'account_day',
        'attribution_status':'not-attributed-to-content','records':value['records'],'warnings':value['warnings'],
        'publication':None,'scheduled_tasks':[],'intake_path':str(root/'intake.json')}
    exact(root/'result.json',result);return {**result,'duplicate':duplicate}

def history(output):
    return sorted((read(p) for p in (workspace(output)/'feedback').glob('*/result.json')),key=lambda r:r['recorded_at'])

def run_server(output,seconds):
    import psutil
    output=workspace(output);config=read(output/'config.json');validate_config(config)
    settings=preview.load_settings();require(settings['host']=='127.0.0.1','loopback_required')
    require(1<=seconds<=1800,'invalid_preview_timeout')
    port=int(settings['port']);require(1<=port<=65535,'invalid_preview_port');origin=f'http://127.0.0.1:{port}';token=secrets.token_urlsafe(32)
    allowed={'/','/index.html','/bundle.json','/review.js','/review.css','/feedback.js'}
    class Handler(preview.handler_for(output/'site',port)):
        def setup(self):
            super().setup();self.connection.settimeout(5)
        def valid_host(self):return self.headers.get('Host')==f'127.0.0.1:{port}'
        def respond(self,data,status=200):
            raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if not self.valid_host():return self.send_error(403)
            path=urlsplit(self.path).path
            if path=='/feedback/context':
                validate_config(config)
                return self.respond({'token':token,'candidates':[{'key':r['key'],'title':r['title'],'version':r['binding']['candidate']['sha256'],'candidate_version':r['review_binding']['candidate_version']} for r in config['candidates']],
                    'imports':[{'key':r['key'],'label':r['label']} for r in config['imports']],'history':history(output)})
            if path not in allowed:return self.send_error(404)
            super().do_GET()
        def do_HEAD(self):
            if not self.valid_host() or urlsplit(self.path).path not in allowed:return self.send_error(404)
            super().do_HEAD()
        def do_POST(self):
            if not self.valid_host() or self.headers.get('Origin')!=origin or not hmac.compare_digest(self.headers.get('X-Feedback-Token',''),token):return self.send_error(403)
            try:
                length=int(self.headers.get('Content-Length','0'));require(0<length<=16384,'invalid_body_size')
                require(self.headers.get('Content-Type')=='application/json','json_required');payload=json.loads(self.rfile.read(length))
                if self.path=='/feedback/submit':result=submit(config,payload,output)
                elif self.path=='/feedback/import':
                    require(set(payload)=={'key'},'import_shape');result=import_local(config,payload['key'],output)
                else:return self.send_error(404)
                self.respond(result)
            except (ValueError,KeyError,TypeError,OSError,link.tracker.TrackerError,link.cycle.CycleError,metrics.MetricsIntakeError) as e:
                self.respond({'error':getattr(e,'code',str(e))},400)
        def log_message(self,fmt,*args):
            with (output/'requests.log').open('a',encoding='utf-8') as f:f.write(f'{now()} {fmt%args}\n')
    proc=psutil.Process();life={'pid':os.getpid(),'creation_time':proc.create_time(),'executable':sys.executable,'argv':sys.argv,'host':'127.0.0.1','port':port,'started_at':now(),'scope':'owned server only; pre-existing Codex browser and transport shell excluded'}
    require(proc.num_threads()<=16 and proc.memory_info().rss<=2048*1048576,'resource_limit_before_listen')
    server=HTTPServer(('127.0.0.1',port),Handler);server.timeout=.15;samples=[];start=time.monotonic()
    try:
        (output/'lifecycle.json').write_text(link.text(life),encoding='utf-8');print(origin+'/index.html?feedback=1',flush=True)
        while time.monotonic()-start<seconds:
            marker=output/'stop-request.json'
            if marker.exists():
                stop=read(marker);require(stop=={'pid':proc.pid,'creation_time':proc.create_time()},'stop_identity_mismatch');life['stop_reason']='identity_bound_stop';break
            samples.append({'elapsed':time.monotonic()-start,'rss':proc.memory_info().rss,'threads':proc.num_threads(),'processes':1+len(proc.children(recursive=True))})
            require(samples[-1]['threads']<=16 and samples[-1]['rss']<=2048*1048576 and samples[-1]['processes']<=6,'resource_limit')
            server.handle_request()
        else:life['stop_reason']='timeout'
    except BaseException as e:
        life['stop_reason']='error';life['error']=type(e).__name__+': '+str(e);raise
    finally:
        server.server_close();life.update(server_closed=True,ended_at=now(),elapsed_seconds=time.monotonic()-start)
        life['peak_sampled']={key:max((s[key] for s in samples),default=0) for key in ('rss','threads','processes')}
        (output/'lifecycle.json').write_text(link.text(life),encoding='utf-8');(output/'resource-samples.json').write_text(link.text(samples),encoding='utf-8')

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace-root',type=Path,required=True);parser.add_argument('--tool-registry',type=Path);commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('prepare');p.add_argument('--bundle',type=Path,required=True);p.add_argument('--candidate',action='append',required=True,help='review-key=local-candidate.json');p.add_argument('--import-csv',action='append',default=[],help='key=profile=synthetic-file.csv');p.add_argument('--output',type=Path,required=True)
    s=commands.add_parser('serve-synthetic');s.add_argument('--output',type=Path,required=True);s.add_argument('--seconds',type=int,default=900)
    a=parser.parse_args(argv);configure_workspace(a.workspace_root,a.tool_registry)
    if a.command=='prepare':
        candidates=dict(v.split('=',1) for v in a.candidate);imports={v.split('=',2)[0]:tuple(v.split('=',2)[1:]) for v in a.import_csv}
        prepare(a.bundle,candidates,a.output,imports);print('prepared synthetic-only feedback preview')
    else:run_server(a.output,a.seconds)
if __name__=='__main__':main()
