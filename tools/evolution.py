#!/usr/bin/env python3
"""Reconstructed C#/Rust table evolution: golden, generative and all-pairs tests."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from evolution_scaffold import ROOT, paths, sync

ROOT_FIELDS = [
    {'tableId','tableName','title','stringValues','numericValues'},
    {'columns','rows','styleMatrix'}, {'sparseOverride','sparseOverrideTypes'},
    {'stylebook','fontConfig'},
    {'imageManager','cellBackgroundImageRefs','cellIds','dataBarScale','cellDataBars','captureTokens'},
    {'columnPriority','rowPriority','hiddenColumns','hiddenRows'},
]


def encode(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def semantic(value):
    # JSON numbers compare by value; booleans remain distinct. No float tolerance.
    if isinstance(value,bool): return ('boolean',value)
    if isinstance(value,(int,float)): return ('number',value)
    if isinstance(value,dict): return ('object',tuple(sorted((k,semantic(v)) for k,v in value.items())))
    if isinstance(value,list): return ('array',tuple(semantic(v) for v in value))
    return (type(value).__name__,value)


def project(table,level):
    """Reference release policy for VALID tables; golden fixtures anchor this policy.

    This does not validate inputs or call either language implementation.
    """
    out=copy.deepcopy(table);lost=[]
    if level>=3 and any(k in out for k in ['allStylesLight','allStylesDark','allStylesExtra','themes']):
        return {'ok':False,'error':'forbidden-key'}
    def prune(obj,keys,extra,path):
        for k in list(obj):
            if (k not in keys and not extra) or (k in keys and obj[k] is None):
                del obj[k];lost.append(path+'/'+k.replace('~','~0').replace('/','~1'))
    prune(out,set.union(*ROOT_FIELDS[:level+1]),level>=3,'')
    if level>=1:
        for name,keys,expr in [('columns',{'id','header','typeHint','width','alignment'},'widthExpr'),('rows',{'id','header','height'},'heightExpr')]:
            if level==5:keys=keys|{expr,'hidden'}
            for i,item in enumerate(out.get(name,[])):
                prune(item,keys,level==5,f'/{name}/{i}')
    if level>=2:
        keys={'rowIndex','colIndex','rowSpan','colSpan','value','valueNumeric','styleKey','typeRef','formula','formatString'}
        if level>=4:keys|={'imageRef','imageAlt','imageFit','imageZoomable','videoRef','posterRef','videoControls','videoMuted','videoLoop','videoFit','mathTex','mathAst'}
        for group,items in out.get('sparseOverride',{}).items():
            for i,item in enumerate(items):
                prune(item,keys,level==5,'/sparseOverride/'+group.replace('~','~0').replace('/','~1')+f'/{i}')
    return {'ok':True,'table':out,'lost':sorted(lost)}


def random_cases(seed,count):
    rng=random.Random(seed)
    for i in range(count):
        nr,nc=rng.randint(1,8),rng.randint(1,8)
        table={'tableId':f'random-{seed}-{i}',
               'stringValues':[[rng.choice([None,'','café','日本語','🦀','<>&', 'line\nbreak']) for _ in range(nc)]for _ in range(nr)],
               'numericValues':[[rng.choice([None,0,rng.randint(-1000000,1000000),rng.randint(-10000,10000)/4])for _ in range(nc)]for _ in range(nr)],
               'columns':[{'header':f'C{c}','width':'120px','widthExpr':{'op':'max','children':[{'value':120},{'symbol':'content'}]},'futureNested':i}for c in range(nc)],
               'sparseOverride':{'cells':[{'rowIndex':0,'colIndex':0,'formula':'SUM(A1:A2)','formatString':'0.00','futureCell':{'seed':seed}}]},
               'stylebook':{'money':{'weight':rng.choice([400,600,700]),'numFormat':'#,##0.00','align':'decimal'}},
               'hiddenColumns':rng.sample(range(nc),rng.randint(0,nc)),
               'futureRoot':{'revision':i,'nested':{'themes':'legal here'}}}
        yield {'id':f'random-{i}','table':table,'expected':[project(table,l)for l in range(6)]}
        malformed=copy.deepcopy(table)
        if i%2:
            malformed['numericValues'][0].append(1)
            error='grid-shape'
        else:
            malformed['numericValues'][0][0]=True
            error='cell-type'
        yield {'id':f'random-invalid-{i}','table':malformed,'expected':[{'ok':False,'error':error}for _ in range(6)]}


def mutation_audit(args,report):
    """Compile deliberately faulty copies and prove golden tests catch both languages."""
    mutation_root=args.report/'mutations'
    cellbase=('horizontal',json.loads((ROOT/'evolution/profiles.json').read_text())['profiles'][-1]['version'])
    original_cs,original_rs,_=paths(ROOT,*cellbase)
    mutant_cs,mutant_rs,_=paths(mutation_root,*cellbase)
    for source,target,ignored in [(original_cs,mutant_cs,{'bin','obj'}),(original_rs,mutant_rs,{'target'})]:
        target.mkdir(parents=True,exist_ok=True)
        for f in source.rglob('*'):
            rel=f.relative_to(source)
            if not f.is_file() or any(p in ignored for p in rel.parts):continue
            dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
    csharp=mutant_cs/'Adapter.cs';rust=mutant_rs/'src/main.rs'
    changes=[(csharp,'key=="numericValues" ? Num(value) : Str(value)', 'key=="numericValues" ? (Num(value) || value!.ToJsonString()=="true") : Str(value)'),
             (rust,'v.as_f64().is_some_and(f64::is_finite)}else{v.is_string()}', '(v.as_f64().is_some_and(f64::is_finite) || v==&Value::Bool(true))}else{v.is_string()}')]
    for path,before,after in changes:
        text=path.read_text(encoding='utf-8')
        if text.count(before)!=1:raise ValueError('Mutation no longer matches its target: '+str(path))
        path.write_text(text.replace(before,after),encoding='utf-8')
    expected={'ok':False,'error':'cell-type'}
    for language in ['csharp','rust']:
        exe=build(mutation_root,(*cellbase,language),args.framework,args.configuration,args.report)
        actual=batch(exe,['{"numericValues":[[true]]}'])[0]
        # A surviving mutant fails the harness. This is deliberately a passing meta-test.
        report.check('mutation-kill',language+'/boolean-as-number',semantic(actual)!=semantic(expected),True,{'mutantOutput':actual})


def transfer_expected(case,table,level):
    # A newer reader may validate a previously opaque, malformed extension.
    # Negative goldens state that acceptance boundary explicitly.
    golden=case['expected'][level]
    if not golden.get('ok') and 'table' in case and semantic(table)==semantic(case['table']):
        return golden
    return project(table,level)


def command(cmd,env=None,data=None,timeout=300):
    p=subprocess.run([str(x)for x in cmd],input=data,text=True,encoding='utf-8',errors='strict',capture_output=True,timeout=timeout,env=env)
    if p.returncode:raise RuntimeError(f'{cmd}\n{p.stdout}\n{p.stderr}')
    return p.stdout


def build(root,cell,framework,configuration,report,refresh_locks=False):
    layout,version,language=cell;csharp,rust,_=paths(root,layout,version)
    env=os.environ.copy()
    env['DOTNET_CLI_TELEMETRY_OPTOUT']='1'
    if language=='csharp':
        output=csharp/'bin'/framework/configuration
        log=command(['dotnet','build',csharp/'Table.csproj','-c',configuration,f'-p:DemoFramework={framework}','-o',output],env=env)
        exe=['dotnet',str(output/'Table.dll')]
    else:
        cargo=os.environ.get('CARGO')or shutil.which('cargo')or 'cargo'
        if refresh_locks:
            command([cargo,'generate-lockfile','--manifest-path',rust/'Cargo.toml'],env=env)
        args=[cargo,'build','--locked','--manifest-path',rust/'Cargo.toml','--target-dir',rust/'target']
        if configuration=='Release':args.append('--release')
        log=command(args,env=env)
        exe=[str(rust/'target'/('release'if configuration=='Release'else'debug')/('table-demo.exe'if os.name=='nt'else'table-demo'))]
    (report/'builds'/('-'.join(cell)+'.log')).write_text(log,encoding='utf-8')
    return exe


def batch(exe,requests):
    output=command(exe,data=''.join(r+'\n'for r in requests))
    lines=output.splitlines()
    if len(lines)!=len(requests):raise AssertionError(f'Expected {len(requests)} responses, got {len(lines)}')
    return [json.loads(line)for line in lines]


class Report:
    def __init__(self,path):
        self.path=path;self.suite=ET.Element('testsuite',name='reconstructed-table-evolution');self.failures=[];self.counts={}
        path.mkdir(parents=True,exist_ok=True);(path/'builds').mkdir(exist_ok=True)
    def check(self,group,name,actual,expected,context=None):
        self.counts[group]=self.counts.get(group,0)+1
        case=ET.SubElement(self.suite,'testcase',name=name,classname=group)
        if semantic(actual)!=semantic(expected):
            failure={'group':group,'name':name,'actual':actual,'expected':expected,'context':context}
            self.failures.append(failure)
            ET.SubElement(case,'failure',message='Mismatch').text=encode(failure)
            if len(self.failures)<=10:print('FAIL',group,name,flush=True)
    def finish(self,metadata):
        self.suite.set('tests',str(len(self.suite)));self.suite.set('failures',str(len(self.failures)))
        ET.ElementTree(self.suite).write(self.path/'junit.xml',encoding='utf-8',xml_declaration=True)
        summary={**metadata,'checks':len(self.suite),'failures':len(self.failures),'groups':self.counts}
        (self.path/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        (self.path/'failures.json').write_text(json.dumps(self.failures,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(summary,indent=2),flush=True)
        return 1 if self.failures else 0


def run(args):
    report=Report(args.report);start=time.time()
    metadata={'reconstructed':True,'seed':args.seed,'samples':args.samples,'framework':args.framework,'configuration':args.configuration,'platform':sys.platform}
    try:
        metadata['toolchains']={'dotnet_sdk':command(['dotnet','--version']).strip(),
                                'cargo':command([os.environ.get('CARGO')or shutil.which('cargo')or 'cargo','--version']).strip()}
        metadata['templates_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in (ROOT/'evolution/templates').iterdir()if p.is_file()}
        drift=sync(check=True)
        if drift:raise ValueError('Generated snapshot drift; run tools/evolution_scaffold.py: '+str(drift[:5]))
        profiles=json.loads((ROOT/'evolution/profiles.json').read_text(encoding='utf-8'))['profiles']
        versions=[p['version']for p in profiles];metadata['versions']=versions
        cells=list(itertools.product(['horizontal','vertical'],versions,['csharp','rust']))
        fixed=json.loads((ROOT/'evolution/fixtures/corpus.json').read_text(encoding='utf-8'))
        if not fixed or len({f['id']for f in fixed})!=len(fixed):raise ValueError('Empty or duplicate fixture corpus')
        cases=fixed+list(random_cases(args.seed,args.samples))
        metadata['fixture_sha256']=hashlib.sha256((ROOT/'evolution/fixtures/corpus.json').read_bytes()).hexdigest()
        metadata['fixed_fixtures']=len(fixed);metadata['implementations']=len(cells)
        metadata['generated_valid']=args.samples;metadata['generated_invalid']=args.samples
        executables={}
        with ThreadPoolExecutor(max_workers=args.jobs)as pool:
            futures={pool.submit(build,ROOT,cell,args.framework,args.configuration,args.report,args.refresh_locks):cell for cell in cells}
            for f in as_completed(futures):
                cell=futures[f]
                try:
                    executables[cell]=f.result();report.check('build','/'.join(cell),True,True)
                    print('Built','/'.join(cell),flush=True)
                except Exception as e:report.check('build','/'.join(cell),str(e),'successful build')
        if len(executables)!=len(cells):raise RuntimeError('Not all required adapters built; coverage incomplete')
        results={}
        for cell in cells:
            level=versions.index(cell[1]);name='/'.join(cell)
            # Each physical layout/version uses its own frozen fixture copy.
            _,_,testdir=paths(ROOT,cell[0],cell[1])
            local=json.loads((testdir/'corpus.json').read_text(encoding='utf-8'))
            report.check('fixture-integrity',name,local,fixed)
            requests=[c['raw']if 'raw'in c else encode(c['table'])for c in cases]
            outputs=batch(executables[cell],requests);results[cell]=outputs
            for c,out in zip(cases,outputs):report.check('golden'if c in fixed else'generative',name+'/'+c['id'],out,c['expected'][level],{'input':c.get('raw',c.get('table'))})
            valid=[(c,out)for c,out in zip(cases,outputs)if out.get('ok')]
            repeated=batch(executables[cell],[encode(out['table'])for _,out in valid])
            reordered=batch(executables[cell],[encode(dict(reversed(list(out['table'].items()))))for _,out in valid])
            for (c,out),again,permuted in zip(valid,repeated,reordered):
                want={'ok':True,'table':out['table'],'lost':[]}
                report.check('idempotence',name+'/'+c['id'],again,want)
                report.check('key-order',name+'/'+c['id'],permuted,want)
            print('Verified local',name,flush=True)
        # Compare all four independent bindings for every release, not just one chosen oracle.
        for version in versions:
            peers=[c for c in cells if c[1]==version]
            for a,b in itertools.combinations(peers,2):
                for case,x,y in zip(cases,results[a],results[b]):
                    report.check('language-layout', '/'.join(a)+' -> '+'/'.join(b)+'/'+case['id'],x,y)
        # Every directed source/destination version, language and layout combination.
        matrix=[]
        for destination in cells:
            requests=[];jobs=[]
            level=versions.index(destination[1])
            for source in cells:
                for c,out in zip(fixed,results[source]):
                    if out.get('ok'):
                        requests.append(encode(out['table']));jobs.append((source,c,out))
            consumed=batch(executables[destination],requests)
            bounce={source:[]for source in cells}
            for (source,c,out),actual in zip(jobs,consumed):
                expected=transfer_expected(c,out['table'],level)
                name='/'.join(source)+' -> '+'/'.join(destination)+'/'+c['id']
                report.check('all-version-pairs',name,actual,expected)
                if actual.get('ok') and expected.get('ok'):
                    bounce[source].append((c,actual,expected))
                    if actual['lost']:matrix.append({'source':source,'destination':destination,'case':c['id'],'removed':actual['lost']})
            # A -> B -> A exposes irreversible downgrade loss; never pretend it restores data.
            for source,items in bounce.items():
                if not items:continue
                returned=batch(executables[source],[encode(actual['table'])for _,actual,_ in items])
                for (c,actual,expected),back in zip(items,returned):
                    wanted=project(expected['table'],versions.index(source[1]))
                    report.check('roundtrip-ABA','/'.join(source)+' -> '+'/'.join(destination)+' -> '+source[1]+'/'+c['id'],back,wanted)
            print('Verified all producers ->','/'.join(destination),flush=True)
        (args.report/'compatibility-losses.json').write_text(json.dumps(matrix,indent=2)+'\n')
        # A through all six versions; covers cumulative upgrade and downgrade paths.
        for lane in itertools.product(['horizontal','vertical'],['csharp','rust']):
            for order,label in [(versions,'upgrade-chain'),(versions[::-1],'downgrade-chain')]:
                corpus=[c for c in fixed if c['expected'][versions.index(order[0])].get('ok')]
                current=[c['expected'][versions.index(order[0])]['table']for c in corpus]
                for version in order:
                    expected=[transfer_expected(c,t,versions.index(version))for c,t in zip(corpus,current)]
                    actual=batch(executables[(lane[0],version,lane[1])],[encode(t)for t in current])
                    for c,a,e in zip(corpus,actual,expected):report.check(label,'/'.join(lane)+'/'+version+'/'+c['id'],a,e)
                    good=[(c,e['table'])for c,e in zip(corpus,expected)if e.get('ok')]
                    corpus=[c for c,_ in good];current=[t for _,t in good]
        mutation_audit(args,report)
    except Exception as e:
        report.check('harness','completion',str(e),'complete required coverage')
    metadata['seconds']=round(time.time()-start,2)
    return report.finish(metadata)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=int,default=1000)
    parser.add_argument('--seed',type=int,default=20260908)
    parser.add_argument('--framework',choices=['net8.0','net10.0'],default='net8.0')
    parser.add_argument('--configuration',choices=['Debug','Release'],default='Release')
    parser.add_argument('--jobs',type=int,default=3)
    parser.add_argument('--report',type=Path,default=ROOT/'reports/evolution')
    parser.add_argument('--refresh-locks',action='store_true',help='Explicitly regenerate Cargo locks before building')
    args=parser.parse_args()
    if args.samples<1 or args.jobs<1:parser.error('samples and jobs must be positive')
    raise SystemExit(run(args))
