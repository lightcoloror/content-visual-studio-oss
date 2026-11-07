"""Existing test setup projected to public-only sources and a native Main copy."""
import copy,json,os,shutil,subprocess,sys
from pathlib import Path
S=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(S/'scripts'))
import feedback_intake as f


def initialize(work,main_source):
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    main=work/'self-media-creation-system'
    # Main is a workspace edition: include its tracked shared validators too.
    names=[n for n in subprocess.check_output(['git','-C',str(main_source),'ls-files','-z']).decode().split('\0') if n]
    for name in names:
        out=work/name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes((Path(main_source)/name).read_bytes())
    registry=work/'tool-registry.json'
    registry.write_text(json.dumps({'tools':{'content-creation-system':{
        'self_media_path':str(main),'runtime_main':{'repositories':{'self':{'path':str(main)}}}}}}),encoding='utf-8')
    shutil.copytree(S/'fixtures/minimal-review',work/'fixtures/minimal-review')
    shutil.copytree(S/'fixtures/feedback-intake',work/'fixtures/feedback-intake')
    os.environ['CONTENT_STUDIO_REVIEW_WORKSPACE']=str(work)
    f.configure_workspace(work,registry)
    return work


def create(root):
    root=Path(root);source=root/'sources';source.mkdir(parents=True,exist_ok=True)
    b=f.review.build_bundle(f.read(f.W/'fixtures/minimal-review/request.json'),f.W)
    b['review_id']='synthetic-feedback-low-friction-v1';b.pop('bundle_sha256');b['bundle_sha256']=f.review.digest(b)
    bundle=source/'bundle.json';f.exact(bundle,b)
    base=f.read(S/'fixtures/feedback-intake/candidate-template.json');candidates={}
    for key in ('fiction-a','fiction-b'):
        c=copy.deepcopy(base);c['content_id']='synthetic-feedback-'+key;c['title']=b['candidates'][key]['title']
        c['channels']['article']['title']=c['title'];c['channels']['article']['platform_metadata']['review_binding']=b['candidates'][key]['binding']
        body=next(a['text'] for a in b['artifacts'].values() if a['candidate_id']==key)
        c['composition']['canonical_body']=body;c['composition']['canonical_summary']=c['title'];c['intent']['topic']=c['title']
        p=source/(key+'.json');f.exact(p,c);candidates[key]=p
    imports={'wechat':('wechat_official_template_v1',f.W/'fixtures/feedback-intake/synthetic-wechat-template.v1.csv')}
    return f.prepare(bundle,candidates,root,imports)


if 'TEST_TMP_ROOT' in os.environ and 'CONTENT_STUDIO_PUBLIC_MAIN_ROOT' in os.environ:
    # Only a new explicit test root; never infer a private sibling or real outputs.
    initialize(Path(os.environ['TEST_TMP_ROOT'])/f'feedback-native-workspace-{os.getpid()}',
               Path(os.environ['CONTENT_STUDIO_PUBLIC_MAIN_ROOT']))
