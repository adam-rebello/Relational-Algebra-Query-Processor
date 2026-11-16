"""Module 3 SQL front end. No regular expressions or parser generators.

The lexer/parser build small SQL structures; Compiler performs catalog-based name
resolution and turns them into canonical logical plan JSON trees.
"""
from dataclasses import dataclass
import json

KEYWORDS = set('SELECT DISTINCT FROM WHERE GROUP BY HAVING ORDER ASC DESC LIMIT JOIN ON AS UNION ALL INTERSECT EXCEPT CREATE TABLE INSERT INTO VALUES AND OR NOT COUNT SUM AVG MIN MAX INT VARCHAR'.split())
AGGS = {'COUNT','SUM','AVG','MIN','MAX'}
CLAUSES = {'WHERE','GROUP','HAVING','ORDER','LIMIT','UNION','INTERSECT','EXCEPT'}

class SQLError(Exception):
    def __init__(self, category, message, line=1, col=1):
        self.category, self.message, self.line, self.col = category,message,line,col
        super().__init__(f'error: {category}: {message} at line {line}, column {col}')

@dataclass
class Token:
    val: str
    kind: str
    line: int
    col: int

def tokenize(s):
    out=[]; i=0; line=1; col=1
    def adv(c):
        nonlocal line,col
        if c=='\n': line+=1; col=1
        else: col+=1
    while i<len(s):
        c=s[i]; l,p=line,col
        if c.isspace(): adv(c);i+=1;continue
        if s.startswith('--',i):
            while i<len(s) and s[i]!='\n':adv(s[i]);i+=1
            continue
        if c.isalpha() or c=='_':
            j=i+1
            while j<len(s) and (s[j].isalnum() or s[j]=='_'):j+=1
            v=s[i:j]; kind='KEYWORD' if v.upper() in KEYWORDS else 'IDENT'
            out.append(Token(v.upper() if kind=='KEYWORD' else v,kind,l,p))
        elif c.isdigit() or (c in '+-' and i+1<len(s) and s[i+1].isdigit()):
            j=i+1
            while j<len(s) and s[j].isdigit():j+=1
            v=s[i:j];kind='NUMBER'
            out.append(Token(v,kind,l,p))
        elif c=="'":
            j=i+1; chars=[]
            while j<len(s):
                if s[j]=="'":
                    if j+1<len(s) and s[j+1]=="'":chars.append("'");j+=2;continue
                    j+=1;break
                chars.append(s[j]);j+=1
            else:raise SQLError('lexical','unterminated string',l,p)
            v="'"+''.join(chars).replace("'","''")+"'";kind='STRING'
            out.append(Token(v,kind,l,p))
        elif s[i:i+2] in ('<=','>=','<>'):
            j=i+2;v=s[i:j];kind='SYMBOL';out.append(Token(v,kind,l,p))
        elif c in '(),;.*=<>':
            j=i+1;v=c;kind='SYMBOL';out.append(Token(v,kind,l,p))
        else:raise SQLError('lexical',f'unknown character {c!r}',l,p)
        for ch in s[i:j]:adv(ch)
        i=j
    out.append(Token('<EOF>','EOF',line,col))
    return out

class Parser:
    def __init__(self,s):self.t=tokenize(s);self.i=0
    def peek(self):return self.t[self.i].val
    def tok(self):return self.t[self.i]
    def take(self): t=self.t[self.i];self.i+=1;return t
    def accept(self,v):
        if self.peek()==v:self.i+=1;return True
        return False
    def expect(self,v):
        if not self.accept(v):self.error(f'expected {v}, found {self.peek()}')
    def error(self,m):
        t=self.tok();raise SQLError('syntax',m,t.line,t.col)
    def identifier(self):
        t=self.tok()
        if t.kind!='IDENT':self.error('expected identifier')
        return self.take().val
    def column(self):
        a=self.identifier()
        if self.accept('.'):return a+'.'+self.identifier()
        return a
    def aggregate(self):
        f=self.take().val;self.expect('(')
        col='*' if self.accept('*') else self.column()
        self.expect(')')
        return ('agg',f.lower(),col)
    def select_item(self):
        if self.peek() in AGGS:item=self.aggregate()
        else:item=('col',self.column())
        alias=None
        if self.accept('AS'):alias=self.identifier()
        return (item,alias)
    def table_ref(self):
        if self.accept('('):
            q=self.query();self.expect(')');self.expect('AS')
            return {'query':q,'alias':self.identifier()}
        name=self.identifier();alias=None
        if self.accept('AS'):alias=self.identifier()
        elif self.tok().kind=='IDENT':alias=self.identifier()
        return {'table':name,'alias':alias}
    def raw_condition(self,stop):
        start=self.i;depth=0
        while True:
            v=self.peek()
            if v=='<EOF>':break
            if depth==0 and v in stop:break
            if v=='(':depth+=1
            if v==')':
                if depth==0:break
                depth-=1
            self.take()
        if depth!=0:self.error('unbalanced parentheses')
        if start==self.i:self.error('expected condition')
        return self.t[start:self.i]
    def block(self):
        if self.accept('('):
            q=self.query();self.expect(')');return q
        self.expect('SELECT');distinct=self.accept('DISTINCT')
        if self.accept('*'):items=[(('star',),None)]
        else:
            items=[self.select_item()]
            while self.accept(','):items.append(self.select_item())
        self.expect('FROM');refs=[self.table_ref()];links=[]
        while self.peek() in {',','JOIN'}:
            if self.accept(','):links.append(('cross',None,self.table_ref()))
            else:
                self.expect('JOIN');r=self.table_ref();self.expect('ON')
                c=self.raw_condition({'JOIN',',','WHERE','GROUP','HAVING','ORDER','LIMIT','UNION','INTERSECT','EXCEPT',';',')'})
                links.append(('join',c,r))
        where=group=having=order=limit=None
        if self.accept('WHERE'):where=self.raw_condition({'GROUP','HAVING','ORDER','LIMIT','UNION','INTERSECT','EXCEPT',';',')'})
        if self.accept('GROUP'):
            self.expect('BY');group=[self.column()]
            while self.accept(','):group.append(self.column())
        if self.accept('HAVING'):having=self.raw_condition({'ORDER','LIMIT','UNION','INTERSECT','EXCEPT',';',')'})
        if self.accept('ORDER'):
            self.expect('BY');order=[]
            while True:
                c=self.column();direction=self.take().val.lower() if self.peek() in ('ASC','DESC') else 'asc'
                order.append([c,direction])
                if not self.accept(','):break
        if self.accept('LIMIT'):
            if self.tok().kind!='NUMBER':self.error('LIMIT requires a number')
            limit=int(self.take().val)
            if limit<0:self.error('LIMIT must be non-negative')
        return dict(kind='select',items=items,distinct=distinct,refs=refs,links=links,where=where,group=group,having=having,order=order,limit=limit)
    def query(self):
        left=self.block()
        while self.peek() in {'UNION','INTERSECT','EXCEPT'}:
            op=self.take().val.lower()
            if op=='union' and self.accept('ALL'):op='union_all'
            right=self.block();left={'kind':'set','op':op,'left':left,'right':right}
        return left
    def statement(self):
        if self.accept('CREATE'):
            self.expect('TABLE');name=self.identifier();self.expect('(');schema=[]
            while True:
                col=self.identifier();typ=self.take().val
                if typ=='VARCHAR':self.expect('(')
                if typ=='VARCHAR':
                    if self.tok().kind!='NUMBER':self.error('VARCHAR length must be integer')
                    size=int(self.take().val);self.expect(')');typeval=['VARCHAR',size]
                    if not 1<=size<=255:self.error('VARCHAR length outside 1..255')
                elif typ=='INT':typeval=['INT']
                else:self.error('invalid column type')
                schema.append([col,*typeval])
                if not self.accept(','):break
            self.expect(')');return {'kind':'create','name':name,'schema':schema}
        if self.accept('INSERT'):
            self.expect('INTO');name=self.identifier();self.expect('VALUES');self.expect('(');values=[]
            while True:
                t=self.tok()
                if t.kind not in ('NUMBER','STRING'):self.error('expected literal')
                self.take();values.append(int(t.val) if t.kind=='NUMBER' else t.val[1:-1].replace("''","'"))
                if not self.accept(','):break
            self.expect(')');return {'kind':'insert','table':name,'values':values}
        return self.query()
    def parse(self):
        result=[]
        while self.peek()!='<EOF>':
            result.append(self.statement())
            if self.peek()!='<EOF>':self.expect(';')
            while self.accept(';'):pass
        if not result:self.error('empty SQL')
        return result

class Compiler:
    def __init__(self,catalog):self.catalog=catalog
    def table_schema(self,name):
        if name not in self.catalog:raise SQLError('name',f'unknown table {name}')
        return [(c[0],c[1]) for c in self.catalog[name]['schema']]
    def resolve(self,name,scope,aliases=None):
        aliases=aliases or {}
        if name in aliases:return aliases[name]
        if '.' in name:
            table,col=name.split('.',1)
            if table not in scope:raise SQLError('name',f'unknown table or alias {table}')
            matches=[(c,t) for c,t in scope[table] if c==col]
            if not matches:raise SQLError('name',f'unknown column {name}')
            return f'{table}.{col}',matches[0][1]
        matches=[(alias,t) for alias,sch in scope.items() for col,t in sch if col==name]
        if not matches:raise SQLError('name',f'unknown column {name}')
        if len(matches)>1:raise SQLError('ambiguity',f'column {name} is ambiguous: '+', '.join(a+'.'+name for a,_ in matches))
        a,t=matches[0];return a+'.'+name,t
    def condition(self,toks,scope,aliases=None,allow_aggs=False):
        if toks is None:return None
        aliases=aliases or {};out=[];i=0
        def atom(t):
            if t.kind=='STRING':return t.val,'VARCHAR'
            if t.kind=='NUMBER':return t.val,'INT'
            return None,None
        # Validate column names, references, and all comparison operand pairs.
        operands=[]
        while i<len(toks):
            t=toks[i];v=t.val
            if v in AGGS:
                if not allow_aggs:raise SQLError('aggregate','aggregate not permitted in WHERE or JOIN ON',t.line,t.col)
                if i+3>=len(toks) or toks[i+1].val!='(':raise SQLError('syntax','invalid aggregate',t.line,t.col)
                k=i+2
                if toks[k].val=='*':arg='*';k+=1
                else:
                    arg=toks[k].val;k+=1
                    if k+1<len(toks) and toks[k].val=='.':arg+='.'+toks[k+1].val;k+=2
                if k>=len(toks) or toks[k].val!=')':raise SQLError('syntax','invalid aggregate',t.line,t.col)
                key=f'{v.lower()}_{arg.replace(".","_").replace("*","star")}'
                if key not in aliases:raise SQLError('aggregate',f'aggregate {v}({arg}) not in select list',t.line,t.col)
                name,typ=aliases[key];out.append(name);operands.append(typ);i=k+1;continue
            if t.kind=='IDENT':
                name=v
                if i+2<len(toks) and toks[i+1].val=='.':name+='.'+toks[i+2].val;i+=2
                resolved,typ=self.resolve(name,scope,aliases)
                out.append(resolved);operands.append(typ)
            elif t.kind in ('STRING','NUMBER'):
                a,typ=atom(t);out.append(a);operands.append(typ)
            elif v in ('=','<>','<','<=','>','>='):
                if not operands:raise SQLError('syntax','missing left operand',t.line,t.col)
                left_type=operands.pop();right_t=toks[i+1] if i+1<len(toks) else None
                if right_t is None:raise SQLError('syntax','missing right operand',t.line,t.col)
                right_type=None
                if right_t.kind in ('NUMBER','STRING'):right_type='INT' if right_t.kind=='NUMBER' else 'VARCHAR'
                elif right_t.kind=='IDENT':
                    nm=right_t.val
                    if i+3<len(toks) and toks[i+2].val=='.':nm+='.'+toks[i+3].val
                    _,right_type=self.resolve(nm,scope,aliases)
                if right_type and left_type!=right_type:raise SQLError('type',f'comparison between {left_type} and {right_type}',t.line,t.col)
                out.append(v)
            else:
                out.append(v)
                if v in ('AND','OR'):operands.clear()
            i+=1
        # Whitespace around comparison and boolean operators, no whitespace around dots.
        return ' '.join(out).replace('( ','(').replace(' )',')')
    def ref(self,ref):
        if 'table' in ref:
            table=ref['table'];sch=self.table_schema(table)
            alias=ref['alias'] or table
            node={'op':'scan','table':table}
            if ref['alias']:node={'op':'rename','to':alias,'child':node}
            return node,alias,sch
        sub,sch=self.compile_query(ref['query'])
        alias=ref['alias']
        # sub output qualified names are discarded on rename.
        return {'op':'rename','to':alias,'child':sub},alias,[(n.split('.')[-1],t) for n,t in sch]
    def compile_query(self,q):
        if q['kind']=='set':
            l,ls=self.compile_query(q['left']);r,rs=self.compile_query(q['right'])
            if len(ls)!=len(rs) or any(a[1]!=b[1] for a,b in zip(ls,rs)):
                raise SQLError('schema','set operation inputs have incompatible schemas')
            return {'op':q['op'],'left':l,'right':r},ls
        if q['kind']!='select':raise SQLError('schema','only SELECT queries produce logical plans')
        node,alias,sch=self.ref(q['refs'][0]);scope={alias:sch}
        for kind,cond,ref in q['links']:
            r,ra,rs=self.ref(ref)
            if ra in scope:raise SQLError('name',f'duplicate alias {ra}')
            combined=dict(scope);combined[ra]=rs
            if kind=='join':node={'op':'join','condition':self.condition(cond,combined),'left':node,'right':r}
            else:node={'op':'cross','left':node,'right':r}
            scope=combined
        if q['where']:node={'op':'select','condition':self.condition(q['where'],scope),'child':node}
        group=[self.resolve(x,scope)[0] for x in (q['group'] or [])]
        aggregating=q['group'] is not None or any(x[0][0]=='agg' for x in q['items'])
        output=[];aggs=[];agg_aliases={};used_aliases={}
        for item,alias_name in q['items']:
            if item[0]=='star':
                if aggregating:raise SQLError('aggregate','SELECT * not allowed with GROUP BY')
                output.extend([(f'{a}.{col}',typ) for a,sch in scope.items() for col,typ in sch]);continue
            if item[0]=='col':
                name,typ=self.resolve(item[1],scope)
                if aggregating and name not in group:raise SQLError('aggregate',f'non-grouped column {name} in SELECT')
                display=alias_name or name
                output.append((display,typ))
                if alias_name:used_aliases[alias_name]=(name,typ)
            else:
                _,func,arg=item
                if arg=='*':
                    if func!='count':raise SQLError('aggregate',f'{func}(*) not allowed')
                    raw='*';typ='INT'
                else:raw,typ=self.resolve(arg,scope)
                if func in ('sum','avg') and typ!='INT':raise SQLError('type',f'{func.upper()} requires INT')
                name=alias_name or f'{func}_{raw.replace(".","_").replace("*","star")}'
                aggs.append([func,raw,name]);outtype='REAL' if func=='avg' else ('INT' if func in ('count','sum') else typ)
                output.append((name,outtype));used_aliases[name]=(name,outtype)
                agg_aliases[f'{func}_{arg.replace(".","_").replace("*","star")}']=(name,outtype)
        if aggregating:
            node={'op':'group_by','keys':group,'aggregates':aggs,'child':node}
        if q['having']:
            if not aggregating:raise SQLError('aggregate','HAVING requires grouping or aggregates')
            # HAVING sees grouped columns and aggregate output names.
            hscope={a:[(c,t) for c,t in sch if f'{a}.{c}' in group] for a,sch in scope.items()}
            hscope['_aggregates']=[(n,t) for n,t in output if '.' not in n]
            halias=dict(agg_aliases)
            for n,t in output:halias[n]=(n,t)
            node={'op':'select','condition':self.condition(q['having'],hscope,halias,True),'child':node}
        node={'op':'project','columns':[n for n,t in output],'child':node}
        if q['distinct'] and not aggregating:node={'op':'distinct','child':node}
        if q['order']:
            keys=[]
            for key,direction in q['order']:
                if key in used_aliases:name=key
                else:name=self.resolve(key,scope)[0]
                keys.append([name,direction])
            node={'op':'sort','keys':keys,'child':node}
        if q['limit'] is not None:node={'op':'limit','count':q['limit'],'child':node}
        return node,output
    def compile(self,ast):
        result=[]
        for statement in ast:
            if statement['kind']=='select' or statement['kind']=='set':
                result.append(self.compile_query(statement)[0])
            elif statement['kind']=='insert':
                sch=self.table_schema(statement['table'])
                if len(sch)!=len(statement['values']):
                    raise SQLError('schema','INSERT value count does not match table columns')
                for (col,typ),val in zip(sch,statement['values']):
                    if (typ=='INT') != isinstance(val,int):
                        raise SQLError('type',f'INSERT value for {col} has wrong type')
                result.append(statement)
            else:result.append(statement)
        return result[0] if len(result)==1 else result
