"""Cost-based optimizer for the M3 logical plan and M2 physical plan contracts."""
import copy
import itertools
import json
import math
from pathlib import Path
from storage_engine.core import Catalog, HeapFile, DiskManager, DirectoryPage, INVALID_PAGE, PAGE_SIZE, encode_record
from execution_engine.core import SeqScan
from execution_engine.advanced import ExternalSort, SpillScan
from execution_engine.spill import SpillFile

class OptimizerError(Exception): pass

def ceil_pages(rows, width):
    return max(1, math.ceil(max(0, rows) * max(1, width) / PAGE_SIZE))

def sort_cost(pages, frames):
    pages=max(1, math.ceil(pages)); frames=max(3,frames)
    runs=max(1,math.ceil(pages/frames))
    passes=1 if runs==1 else 1+math.ceil(math.log(runs,frames-1))
    return 2*pages*(passes-1)+pages

def join_cost(algorithm,m,n,frames):
    m=max(1,math.ceil(m));n=max(1,math.ceil(n))
    if algorithm=='nested_loop_join':return m+math.ceil(m/(frames-2))*n
    if algorithm=='sort_merge_join':return sort_cost(m,frames)+sort_cost(n,frames)+m+n
    if algorithm=='hash_join':return 3*(m+n)
    raise OptimizerError('unsupported join algorithm '+algorithm)

def clean_condition(cond):return ' '.join(cond.replace('(', ' ( ').replace(')', ' ) ').split())

def conjunctions(cond):
    """Split only top-level AND; respect quoted strings and parentheses."""
    pieces=[]; depth=0; quote=False; start=0; i=0
    while i<len(cond):
        c=cond[i]
        if c=="'":
            if quote and i+1<len(cond) and cond[i+1]=="'":i+=2;continue
            quote=not quote
        elif not quote:
            if c=='(':depth+=1
            elif c==')':depth-=1
            elif depth==0 and cond[i:i+3].upper()=='AND' and (i==0 or not (cond[i-1].isalnum() or cond[i-1]=='_')) and (i+3==len(cond) or not (cond[i+3].isalnum() or cond[i+3]=='_')):
                pieces.append(cond[start:i].strip());start=i+3;i+=3;continue
        i+=1
    pieces.append(cond[start:].strip())
    return [p for p in pieces if p]

def references(expr):
    """Extract table.column references without regular expressions."""
    found=set();i=0;quote=False
    while i<len(expr):
        c=expr[i]
        if c=="'":
            if quote and i+1<len(expr) and expr[i+1]=="'":i+=2;continue
            quote=not quote;i+=1;continue
        if quote:i+=1;continue
        if c.isalpha() or c=='_':
            a=i;i+=1
            while i<len(expr) and (expr[i].isalnum() or expr[i]=='_'):i+=1
            name=expr[a:i]
            if i<len(expr) and expr[i]=='.':
                i+=1;b=i
                while i<len(expr) and (expr[i].isalnum() or expr[i]=='_'):i+=1
                if i>b:found.add(name+'.'+expr[b:i])
            continue
        i+=1
    return found

def relation_names(node):
    op=node['op']
    if op=='scan':return {node['table']}
    if op=='rename':return {node['to']}
    if 'left' in node:return relation_names(node['left'])|relation_names(node['right'])
    if 'child' in node:return relation_names(node['child'])
    return set()

def alias_of(ref):return ref.split('.',1)[0] if '.' in ref else ''

def simple_equality(cond):
    if not isinstance(cond,str):return None
    depth=0;pos=-1;quote=False
    for i,c in enumerate(cond):
        if c=="'":quote=not quote
        if quote:continue
        if c=='(':depth+=1
        elif c==')':depth-=1
        elif c=='=' and depth==0 and (i==0 or cond[i-1] not in '<>!') and (i+1==len(cond) or cond[i+1]!='='):
            if pos!=-1:return None
            pos=i
    if pos<0:return None
    a,b=(x.strip() for x in (cond[:pos],cond[pos+1:]))
    return a,b

def replace_qualifier(cond,old,new):
    return cond.replace(old+'.',new+'.')

def rewrite(plan, disabled=()):
    """Apply safe predicate rewrites repeatedly; preserve plan meaning and stable order."""
    disabled=set(disabled)
    def rec(node):
        node=copy.deepcopy(node);op=node['op']
        for key in ('child','left','right'):
            if key in node:node[key]=rec(node[key])
        if op=='select':
            child=node['child'];cond=node['condition']
            if 1 not in disabled:
                terms=conjunctions(cond)
                if len(terms)>1:
                    result=child
                    for term in reversed(terms):result={'op':'select','condition':term,'child':result}
                    return rec(result)
            if child['op'] in ('join','cross'):
                refs=references(cond);left=relation_names(child['left']);right=relation_names(child['right'])
                sides={alias_of(r) for r in refs}
                if 2 not in disabled and sides and sides<=left:
                    child['left']=rec({'op':'select','condition':cond,'child':child['left']});return child
                if 2 not in disabled and sides and sides<=right:
                    child['right']=rec({'op':'select','condition':cond,'child':child['right']});return child
                eq=simple_equality(cond)
                if 3 not in disabled and child['op']=='cross' and eq:
                    a,b=eq
                    if (alias_of(a) in left and alias_of(b) in right) or (alias_of(a) in right and alias_of(b) in left):
                        return {'op':'join','condition':cond,'left':child['left'],'right':child['right']}
            if child['op']=='rename' and 4 not in disabled:
                # Use source alias if exactly one base name is available.
                source=relation_names(child['child'])
                if len(source)==1:
                    original=next(iter(source));newcond=replace_qualifier(cond,child['to'],original)
                    child['child']=rec({'op':'select','condition':newcond,'child':child['child']});return child
            if child['op'] in ('union','union_all') and 4 not in disabled:
                l=child['left'];r=child['right']
                if len(relation_names(l))==1 and len(relation_names(r))==1:
                    la=next(iter(relation_names(l)));ra=next(iter(relation_names(r)))
                    prefix={alias_of(x) for x in references(cond)}
                    if len(prefix)==1:
                        p=next(iter(prefix))
                        child['left']=rec({'op':'select','condition':replace_qualifier(cond,p,la),'child':l})
                        child['right']=rec({'op':'select','condition':replace_qualifier(cond,p,ra),'child':r})
                        return child
            if child['op']=='group_by' and 5 not in disabled and references(cond)<=set(child['keys']) and references(cond):
                child['child']=rec({'op':'select','condition':cond,'child':child['child']});return child
        return node
    # Multiple passes find pushdowns previously masked by a transformation.
    result=rec(plan)
    for _ in range(4):
        nxt=rec(result)
        if nxt==result:break
        result=nxt
    return result

def _statistics_path(db,table):return Path(db)/f'_opt_stats_{table}.db'

def _write_stats(db,table,obj):
    """Stats payload in disk pages, catalog stores the page-file pointer."""
    if _read_stats(db,table)==obj:
        return  # ANALYZE with unchanged data must not grow the catalog.
    path=_statistics_path(db,table)
    payload=json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    if path.exists():path.unlink()
    disk=DiskManager(path)
    for i in range(0,len(payload),PAGE_SIZE):
        pid=disk.allocate_page(); page=payload[i:i+PAGE_SIZE]
        disk.write_page(pid,page.ljust(PAGE_SIZE,b'\0'))
    cat=Catalog(db)
    try:cat.update_table(table, stats_file=path.name,stats_size=len(payload))
    finally:cat.close()

def _read_stats(db,table,info=None):
    if info is None:
        cat=Catalog(db)
        try:info=cat.get_table(table)
        finally:cat.close()
    if not info.get('stats_file'):return None
    path=Path(db)/info['stats_file']
    if not path.exists():return None
    disk=DiskManager(path)
    return json.loads(b''.join(disk.read_page(i) for i in range(disk.num_pages()))[:info['stats_size']].decode('utf-8'))

def analyze(db,table,buckets=20,frames=8):
    if buckets<1 or frames<4:raise OptimizerError('buckets must be positive and frames >= 4')
    cat=Catalog(db)
    try:info=cat.get_table(table)
    finally:cat.close()
    schema=info['schema'];qualified=[[table+'.'+c[0],*c[1:]] for c in schema]
    source=SpillFile(qualified)
    w=source.writer();heap=HeapFile(Path(db)/info['file'],schema,frames=min(2,frames))
    n=0;size=0
    try:
        for _,row in heap.scan():
            w.append(row);n+=1;size+=len(encode_record(schema,row))
    finally:
        w.close();heap.close()
    # Count actual data pages from the on-disk directory rather than stale catalog totals.
    data_pages=0; directory_id=0
    heap_count=HeapFile(Path(db)/info['file'],schema,frames=min(2,frames))
    try:
        while directory_id!=INVALID_PAGE:
            frame=heap_count.pool.fetch_page(directory_id)
            try:
                directory=DirectoryPage(frame.data)
                data_pages+=directory.count
                directory_id=directory.next_page
            finally:heap_count.pool.unpin_page(frame.page_id)
    finally:heap_count.close()
    obj={'n_tuples':n,'n_pages':data_pages,'width':size/n if n else 0,'columns':{}}
    try:
        for j,col in enumerate(schema):
            op=ExternalSort(SpillScan(source,qualified),[[table+'.'+col[0],'asc']],frames)
            prev=object();ndv=0;count=0;lo=hi=None;hist=[];bucket_first=None;bucket_last=None;bucket_total=0;bucket_distinct=0
            target=max(1,math.ceil(n/buckets))
            try:
                op.open()
                while True:
                    row=op.next()
                    if row is None:break
                    val=row[j];count+=1
                    if count==1:lo=val
                    hi=val
                    if val!=prev:ndv+=1;prev=val
                    if bucket_total==0:bucket_first=val;bucket_distinct=0;last_in_bucket=object()
                    if val!=last_in_bucket:bucket_distinct+=1;last_in_bucket=val
                    bucket_last=val;bucket_total+=1
                    # Avoid cutting a duplicate run unless needed to keep k buckets.
                    if bucket_total>=target and len(hist)<buckets-1:
                        hist.append({'min':bucket_first,'max':bucket_last,'count':bucket_total,'ndv':bucket_distinct})
                        bucket_total=0
                if bucket_total:hist.append({'min':bucket_first,'max':bucket_last,'count':bucket_total,'ndv':bucket_distinct})
            finally:op.close()
            obj['columns'][col[0]]={'ndv':ndv,'min':lo,'max':hi,'hist':hist}
    finally:source.remove()
    _write_stats(db,table,obj)
    return obj

class Optimizer:
    def __init__(self,db,frames=32,disabled=()):
        if frames<4:raise OptimizerError('frames must be >= 4')
        self.db=db;self.frames=frames;self.disabled=disabled
        cat=Catalog(db)
        try:self.catalog=cat.list_tables()
        finally:cat.close()
        self.stats={t:_read_stats(db,t,info) for t,info in self.catalog.items()}
        self.last_dp=[]
        self.alias_map={}
    def table(self,table):
        if table not in self.catalog:raise OptimizerError('unknown table '+table)
        info=self.catalog[table];s=self.stats.get(table)
        return {'rows':max(1,(s or {}).get('n_tuples',info.get('num_tuples',1000) or 1000)),
                'pages':max(1,(s or {}).get('n_pages',info.get('num_pages',20)-1)),
                'width':max(1,(s or {}).get('width',sum(4 if c[1]=='INT' else 2+c[2]/2 for c in info['schema'])))}
    def colstat(self,col,alias_map=None):
        if '.' not in col:return None
        table,column=col.split('.',1)
        if alias_map is None:alias_map=self.alias_map
        table=alias_map.get(table,table)
        s=self.stats.get(table)
        return (s or {}).get('columns',{}).get(column)
    def selectivity(self,cond,alias_map=None):
        cond=cond.strip()
        terms=conjunctions(cond)
        if len(terms)>1:return math.prod(self.selectivity(x,alias_map) for x in terms)
        u=cond.upper()
        if u.startswith('NOT '):return 1-self.selectivity(cond[4:].strip(),alias_map)
        for sep in (' OR ',):
            if sep in u:
                a,b=cond.split(sep,1) if sep in cond else (cond[:u.index(sep)],cond[u.index(sep)+len(sep):])
                x=self.selectivity(a,alias_map);y=self.selectivity(b,alias_map)
                return x+y-x*y
        for op in ('<>','<=','>=','=','<','>'):
            if op in cond:
                l,r=map(str.strip,cond.split(op,1));s=self.colstat(l,alias_map)
                if not s:
                    return 0.1 if op!='=' else 0.1
                try:
                    v=(r[1:-1].replace("''","'") if r.startswith("'") else int(r))
                except ValueError:return 1/max(1,s.get('ndv',10)) if op=='=' else 0.1
                if op=='<>':return 1-self.selectivity(l+' = '+r,alias_map)
                if op=='=':
                    h=next((x for x in s['hist'] if x['min']<=v<=x['max']),None)
                    if h:return min(1,h['count']/max(1,sum(x['count'] for x in s['hist'])*h['ndv']))
                    return 0 if s['hist'] else 1/max(1,s['ndv'])
                n=sum(x['count'] for x in s['hist'])
                if not n:return 0.1
                accum=0
                for h in s['hist']:
                    a,b=h['min'],h['max']
                    if (op in ('<','<=') and b<v) or (op in ('>','>=') and a>v):accum+=h['count']
                    elif a<=v<=b:
                        try:
                            fraction=(v-a)/(b-a) if b!=a else (0.5 if v==a else 0)
                            accum+=h['count']*(fraction if op in ('<','<=') else 1-fraction)
                        except TypeError:accum+=h['count']*0.5
                return max(0,min(1,accum/n))
        return 0.1
    def join_rows(self,left,right,condition,alias_map=None):
        eq=simple_equality(condition)
        if eq and '.' in eq[0] and '.' in eq[1]:
            a=self.colstat(eq[0],alias_map);b=self.colstat(eq[1],alias_map)
            if a and b:return max(1,math.ceil(left['rows']*right['rows']/max(1,a['ndv'],b['ndv'])))
        return max(1,math.ceil(left['rows']*right['rows']*0.1))
    def _physical(self,n):
        op=n['op']
        if op=='scan':
            t=self.table(n['table'])
            return {'op':'seqscan','table':n['table']},dict(t,cost=t['pages'],schema=[[n['table']+'.'+c[0],*c[1:]] for c in self.catalog[n['table']]['schema']])
        if op=='rename':
            # Rename is a logical alias; executor has no rename operation.
            child,stat=self._physical(n['child']);alias=n['to'];old=[x[0] for x in stat['schema']]
            stat['schema']=[[alias+'.'+x[0].split('.')[-1],*x[1:]] for x in stat['schema']]
            # Add a physical rename node; Module 2 must support it (see integration patch).
            return {'op':'rename','to':alias,'child':child},stat
        if op=='sort' and n['child']['op']=='project':
            projected=set(n['child']['columns'])
            if any(key[0] not in projected for key in n['keys']):
                # Sort original rows before dropping ORDER BY columns.
                return self._physical({'op':'project','columns':n['child']['columns'],
                    'child':{'op':'sort','keys':n['keys'],'child':n['child']['child']}})
        if op in ('select','project','sort','limit','distinct','group_by'):
            child,s=self._physical(n['child']);s=dict(s);plan={'child':child}
            if op=='select':
                fraction=self.selectivity(n['condition']);s['rows']=max(1,math.ceil(s['rows']*fraction));plan.update(op='filter',condition=n['condition'])
            elif op=='project':
                cols=n['columns'];previous={x[0]:x for x in s['schema']}
                s['schema']=[previous.get(x,[x,'INT']) for x in cols]
                s['width']=sum(4 if c[1]=='INT' else 8 if c[1]=='REAL' else 2+c[2]/2 for c in s['schema'])
                plan.update(op='project',columns=cols)
            elif op=='sort':
                s['cost']+=sort_cost(s['pages'],self.frames);plan.update(op='sort',keys=n['keys'])
            elif op=='limit':s['rows']=min(s['rows'],n['count']);plan.update(op='limit',n=n['count'])
            elif op=='distinct':s['cost']+=sort_cost(s['pages'],self.frames);plan.update(op='distinct',mode='sort')
            elif op=='group_by':
                s['cost']+=sort_cost(s['pages'],self.frames)
                s['rows']=max(1,min(s['rows'],s['rows']*0.1));plan.update(op='group_by',mode='sort',keys=n['keys'],aggregates=n['aggregates'])
                s['schema']=[[c,*next((x[1:] for x in s['schema'] if x[0]==c),['INT'])] for c in n['keys']]+[[a[2] if len(a)>2 else a[0]+'_'+a[1].replace('.','_'),'REAL' if a[0]=='avg' else 'INT'] for a in n['aggregates']]
            s['pages']=ceil_pages(s['rows'],s['width'])
            return plan,s
        if op in ('join','cross'):
            return self._dp(n)
        left,ls=self._physical(n['left']);right,rs=self._physical(n['right']);s=dict(ls)
        s['cost']+=rs['cost']
        return {'op':op,'left':left,'right':right},s
    def _projection_pushdown(self,node):
        """Prune unused columns at join leaves, keeping every join/filter key."""
        node=copy.deepcopy(node)
        for k in ('child','left','right'):
            if k in node:node[k]=self._projection_pushdown(node[k])
        if node['op']!='project' or node['child']['op'] not in ('join','cross') or 6 in self.disabled:
            return node
        required=set(node['columns'])
        def collect(n):
            if 'condition' in n:required.update(references(n['condition']))
            for k in ('child','left','right'):
                if k in n:collect(n[k])
        collect(node['child'])
        def prune(n):
            if n['op'] in ('join','cross'):
                n['left']=prune(n['left']);n['right']=prune(n['right']);return n
            if n['op'] in ('sort','group_by','distinct','project','limit'):
                return n
            # Do not insert a projection below a filter: first evaluate the
            # predicate, then discard unneeded columns.
            p,s=self._physical(n)
            available=[c[0] for c in s['schema']]
            keep=[x for x in available if x in required]
            if keep and len(keep)<len(available):
                return {'op':'project','columns':keep,'child':n}
            return n
        node['child']=prune(node['child'])
        return node

    def plan(self,logical):
        self.alias_map={}
        def gather(n):
            if n['op']=='rename' and n['child']['op']=='scan':self.alias_map[n['to']]=n['child']['table']
            for k in ('child','left','right'):
                if k in n:gather(n[k])
        gather(logical)
        self.last_dp=[]
        rewritten=self._projection_pushdown(rewrite(logical,self.disabled))
        physical,stats=self._physical(rewritten)
        return physical
    def _estimate_physical(self,p):
        """Estimated rows/pages/I/O and displayed schema at every physical node."""
        op=p['op']
        if op=='seqscan':
            t=self.table(p['table'])
            return {**t,'cost':t['pages'],'schema':[[p['table']+'.'+c[0],*c[1:]] for c in self.catalog[p['table']]['schema']]}
        if 'child' in p:
            child=self._estimate_physical(p['child']);s=dict(child)
            if op=='rename':
                s['schema']=[[p['to']+'.'+c[0].split('.')[-1],*c[1:]] for c in s['schema']]
            elif op=='filter':s['rows']=max(1,math.ceil(s['rows']*self.selectivity(p['condition'])))
            elif op=='project':
                lookup={x[0]:x for x in s['schema']}
                s['schema']=[lookup[x] for x in p['columns'] if x in lookup]
                s['width']=sum(4 if c[1]=='INT' else 8 if c[1]=='REAL' else 2+c[2]/2 for c in s['schema'])
            elif op=='sort':s['cost']+=sort_cost(s['pages'],self.frames)
            elif op=='distinct':s['cost']+=sort_cost(s['pages'],self.frames)
            elif op=='group_by':
                s['cost']+=sort_cost(s['pages'],self.frames)
                s['rows']=max(1,math.ceil(s['rows']*0.1))
                lookup={c[0]:c for c in child['schema']}
                s['schema']=[lookup[x] for x in p['keys'] if x in lookup]
                for a in p['aggregates']:
                    typ='REAL' if a[0]=='avg' else 'INT'
                    if a[0] in ('min','max') and a[1] in lookup:typ=lookup[a[1]][1]
                    col=a[2] if len(a)==3 else a[0]+'_'+a[1].replace('.','_').replace('*','star')
                    s['schema'].append([col,typ])
            elif op=='limit':s['rows']=min(s['rows'],p['n'])
            s['pages']=ceil_pages(s['rows'],s['width'])
            return s
        l=self._estimate_physical(p['left']);r=self._estimate_physical(p['right'])
        if op in ('nested_loop_join','hash_join','sort_merge_join'):
            width=l['width']+r['width'];n=self.join_rows(l,r,p['condition'])
            cost=l['cost']+r['cost']+join_cost(op,l['pages'],r['pages'],self.frames)
            return dict(rows=n,pages=ceil_pages(n,width),width=width,cost=cost,schema=l['schema']+r['schema'])
        return dict(l, cost=l['cost']+r['cost'],rows=l['rows']+r['rows'])

    def explain(self,logical):
        physical=self.plan(logical)
        lines=[]
        def emit(p,depth=0):
            s=self._estimate_physical(p)
            detail=p['op']
            if p['op']=='seqscan':detail+=' '+p['table']
            if 'condition' in p:detail+=' ('+p['condition']+')'
            lines.append('  '*depth+f'{detail}  est_rows={s["rows"]}  est_cost={s["cost"]:.2f}')
            for k in ('child','left','right'):
                if k in p:emit(p[k],depth+1)
        emit(physical)
        return '\n'.join(lines)

    def _flatten_joins(self,node):
        """Collect only contiguous join/cross trees; avoid crossing blocking boundaries."""
        leaves=[];predicates=[]
        def walk(n):
            if n['op'] in ('join','cross'):
                walk(n['left']);walk(n['right'])
                if n.get('condition'):predicates.extend(conjunctions(n['condition']))
            else:leaves.append(n)
        walk(node)
        return leaves,predicates

    def _dp(self,node):
        leaves,preds=self._flatten_joins(node)
        if not 2<=len(leaves)<=6:return self._physical_regular(node)
        aliases=[relation_names(x) for x in leaves]
        if any(len(x)!=1 for x in aliases) or len(set().union(*aliases))!=len(leaves):
            return self._physical_regular(node)
        known=[next(iter(x)) for x in aliases]
        base=[]
        for leaf in leaves:
            p,s=self._physical(leaf)
            base.append((p,s))
        dp={};rows=[]
        for i,name in enumerate(known):
            p,s=base[i];dp[frozenset({i})]=(p,s)
            rows.append({'subset':[name], 'order':name,'algorithm':'scan', 'cost':round(s['cost'],3), 'rows':s['rows'], 'pages':s['pages']})
        for k in range(2,len(leaves)+1):
            for combo in itertools.combinations(range(len(leaves)),k):
                group=frozenset(combo);choices=[]
                for idx in combo:
                    left_set=group-{idx}
                    if left_set not in dp:continue
                    lp,ls=dp[left_set];rp,rs=base[idx]
                    leftnames={known[j] for j in left_set};rightname=known[idx]
                    related=[p for p in preds if
                             ({alias_of(x) for x in references(p)}&leftnames) and
                             rightname in {alias_of(x) for x in references(p)}]
                    if not related:continue
                    cond=' AND '.join(related)
                    eq=all(simple_equality(x) is not None for x in related)
                    algorithms=['nested_loop_join','hash_join','sort_merge_join'] if eq else ['nested_loop_join']
                    for alg in algorithms:
                        cost=ls['cost']+rs['cost']+join_cost(alg,ls['pages'],rs['pages'],self.frames)
                        newrows=self.join_rows(ls,rs,related[0])
                        width=ls['width']+rs['width']
                        stats={'rows':newrows,'pages':ceil_pages(newrows,width),'width':width,'cost':cost,'schema':ls['schema']+rs['schema']}
                        p={'op':alg,'condition':cond,'left':lp,'right':rp}
                        order='+'.join(known[j] for j in sorted(left_set))+' → '+rightname
                        choices.append((cost,alg,idx,p,stats,order))
                if not choices:
                    # No connecting edge in this subset. Prefer a connected subset;
                    # disconnected queries fall back to original order.
                    continue
                winner=min(choices,key=lambda x:(x[0],x[1],x[2]))
                _,alg,_,p,stats,order=winner
                dp[group]=(p,stats)
                rows.append({'subset':[known[j] for j in combo],'order':order,'algorithm':alg,
                             'cost':round(stats['cost'],3),'rows':stats['rows'],'pages':stats['pages']})
        self.last_dp=rows
        final=frozenset(range(len(leaves)))
        if final not in dp:return self._physical_regular(node)
        return dp[final]

    def _physical_regular(self,node):
        """Fallback for an unsupported/disconnected join tree."""
        l,ls=self._physical(node['left']);r,rs=self._physical(node['right'])
        cond=node.get('condition')
        if not cond:cond='1 = 1' # Cartesian product via always-true nested-loop predicate
        algos=['nested_loop_join'] if cond=='1 = 1' or simple_equality(cond) is None else ['nested_loop_join','hash_join','sort_merge_join']
        alg=min(algos,key=lambda a:(join_cost(a,ls['pages'],rs['pages'],self.frames),a))
        width=ls['width']+rs['width'];n=self.join_rows(ls,rs,cond)
        return {'op':alg,'condition':cond,'left':l,'right':r},dict(rows=n,pages=ceil_pages(n,width),width=width,cost=ls['cost']+rs['cost']+join_cost(alg,ls['pages'],rs['pages'],self.frames),schema=ls['schema']+rs['schema'])

    def dp_table(self,logical):
        self.plan(logical)
        return self.last_dp
