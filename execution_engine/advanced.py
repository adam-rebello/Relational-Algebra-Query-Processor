"""Disk-backed sorting and blocking execution operators for Module 2."""
import heapq
import math
from .spill import SpillFile, encode_temp_record
from .core import Operator, Unary, PlanError, column_index, relation_for_schema, check_condition
from src.condition_api import parse_condition, evaluate_condition

class _Rev:
    def __init__(self, value): self.value = value
    def __lt__(self, other): return other.value < self.value
    def __eq__(self, other): return self.value == other.value

def _value_key(value):
    return value.encode('utf-8') if isinstance(value,str) else value

def _sort_key(row, indexes, dirs):
    return tuple((_Rev(_value_key(row[i])) if d == 'desc' else _value_key(row[i])) for i,d in zip(indexes,dirs))

class ExternalSort(Unary):
    """Pass 0 writes runs of <= B pages; later passes merge <=B-1 runs.
    Final pass streams directly through next, without materializing its output.
    """
    def __init__(self, child, keys, frames):
        super().__init__('sort', child)
        self.frames=frames
        self.keys=keys
        self.indexes=[column_index(child.schema,k[0]) for k in keys]
        self.dirs=[k[1].lower() for k in keys]
        self.files=[]
        self.readers=[]
        self.queue=[]
        self.single=None
        self.serial=0
        self.passes=0
    def _new_file(self):
        f=SpillFile(self.schema)
        self.files.append(f)
        return f
    def _merge(self, runs, writer=None):
        readers=[r.reader() for r in runs]
        heap=[]
        serial=0
        for i,reader in enumerate(readers):
            row=reader.next()
            if row is not None:
                heapq.heappush(heap, (_sort_key(row,self.indexes,self.dirs),serial,i,row))
                serial+=1
        try:
            while heap:
                _,_,i,row=heapq.heappop(heap)
                if writer is None: yield row
                else: writer.append(row)
                nxt=readers[i].next()
                if nxt is not None:
                    heapq.heappush(heap,(_sort_key(nxt,self.indexes,self.dirs),serial,i,nxt))
                    serial+=1
        finally:
            for reader in readers: reader.close()
    def open(self):
        self.files=[]
        self.child.open()
        runs=[]
        try:
            chunk=[]
            bytes_used=0
            from storage_engine.core import encode_record
            schema=[[f'c{i}',*c[1:]] for i,c in enumerate(self.schema)]
            while True:
                row=self.child.next()
                if row is None: break
                size=len(encode_temp_record(schema,row))+2
                if chunk and bytes_used+size > max(1,self.frames-3)*4096:
                    chunk.sort(key=lambda r: _sort_key(r,self.indexes,self.dirs))
                    f=self._new_file(); w=f.writer()
                    for entry in chunk: w.append(entry)
                    w.close(); runs.append(f)
                    chunk=[]; bytes_used=0
                chunk.append(row); bytes_used+=size
            if chunk:
                chunk.sort(key=lambda r: _sort_key(r,self.indexes,self.dirs))
                f=self._new_file(); w=f.writer()
                for entry in chunk: w.append(entry)
                w.close(); runs.append(f)
            self.passes=1 if runs else 0
        finally:
            self.child.close()
        if not runs:
            self.final=iter(())
        else:
            while len(runs)>self.frames-1:
                next_runs=[]
                for start in range(0,len(runs),self.frames-1):
                    group=runs[start:start+self.frames-1]
                    if len(group)==1:
                        next_runs.append(group[0]); continue
                    target=self._new_file(); writer=target.writer()
                    for _ in self._merge(group, writer): pass
                    writer.close(); next_runs.append(target)
                runs=next_runs
                self.passes+=1
            if len(runs)>1: self.passes+=1
            self.final=self._merge(runs)
        self.active=True
    def next(self):
        try: return self.emit(next(self.final))
        except StopIteration: return None
    def close(self):
        if hasattr(self,'final') and hasattr(self.final,'close'): self.final.close()
        for f in self.files:
            self.page_reads+=f.disk.reads
            self.page_writes+=f.disk.writes
            f.path.unlink(missing_ok=True)
        self.files=[]
        self.active=False

class Distinct(Unary):
    def __init__(self,child,mode,frames):
        super().__init__('distinct',child)
        self.mode=mode
        self.sorted=ExternalSort(child, [[c[0],'asc'] for c in child.schema],frames)
        self.children=[self.sorted]
        self.last=None
    def open(self):
        self.sorted.open();self.last=None;self.active=True
    def next(self):
        while True:
            row=self.sorted.next()
            if row is None:return None
            key=tuple(row)
            if key != self.last:
                self.last=key
                return self.emit(row)
    def close(self):self.sorted.close();self.active=False

class GroupBy(Unary):
    def __init__(self,child,keys,aggregates,mode,frames):
        super().__init__('group_by',child)
        self.key_names=keys
        self.key_indices=[column_index(child.schema,c) for c in keys]
        self.aggs=[]
        for a in aggregates:
            fun,col=a[0].lower(),a[1]
            i=None if col=='*' else column_index(child.schema,col)
            if fun not in ('count','sum','avg','min','max'):raise PlanError('Node group_by: unsupported aggregate')
            if fun!='count' and i is None:raise PlanError('Node group_by: only count accepts *')
            if fun in ('sum','avg') and child.schema[i][1]!='INT':raise PlanError('Node group_by: numeric aggregate requires INT')
            self.aggs.append((fun,col,i))
        self.schema=[child.schema[i] for i in self.key_indices]
        for j,(fun,col,i) in enumerate(self.aggs):
            name=aggregates[j][2] if len(aggregates[j])==3 else f'{fun}_{col.replace(".","_") if col!="*" else "star"}'
            typ=['INT'] if fun=='count' else (['VARCHAR',255] if i is not None and child.schema[i][1]=='VARCHAR' else ['INT'])
            if fun=='avg':typ=['REAL'] # calculated result, not an on-disk storage type
            self.schema.append([name,*typ])
        self.sorted=ExternalSort(child,[[c,'asc'] for c in keys],frames)
        self.children=[self.sorted]
        self.pending=None
        self.empty_emitted=False
    def open(self):
        self.sorted.open();self.pending=None;self.empty_emitted=False;self.active=True
    def _new_acc(self):return [[0,0,None] for _ in self.aggs]
    def _consume(self,acc,row):
        for x,(fun,col,i) in zip(acc,self.aggs):
            value=1 if i is None else row[i]
            x[0]+=1
            if fun in ('sum','avg'): x[1]+=value
            if fun in ('min','max'):
                if x[2] is None or (value<x[2] if fun=='min' else value>x[2]):x[2]=value
    def _finish(self,key,acc):
        values=[]
        for x,(fun,_,i) in zip(acc,self.aggs):
            if fun=='count':values.append(x[0])
            elif fun=='sum':values.append(x[1])
            elif fun=='avg':values.append(round(x[1]/x[0],4) if x[0] else None)
            else:values.append(x[2])
        return list(key)+values
    def next(self):
        row=self.pending if self.pending is not None else self.sorted.next()
        self.pending=None
        if row is None:
            if not self.key_indices and not self.empty_emitted:
                self.empty_emitted=True
                if any(fun!='count' for fun,_,_ in self.aggs):raise PlanError('Node group_by: undefined aggregate on empty input')
                return self.emit(self._finish((),self._new_acc()))
            return None
        key=tuple(row[i] for i in self.key_indices)
        acc=self._new_acc();self._consume(acc,row)
        while True:
            row=self.sorted.next()
            if row is None:break
            if tuple(row[i] for i in self.key_indices)!=key:
                self.pending=row;break
            self._consume(acc,row)
        self.empty_emitted=True
        return self.emit(self._finish(key,acc))
    def close(self):self.sorted.close();self.active=False

class SetOperation(Operator):
    """Set union/intersection/except using two disk-backed sorted streams.
    Sorted inputs are built sequentially; merge keeps one page from each.
    """
    def __init__(self,op,left,right,frames):
        super().__init__(op)
        if [x[1:] for x in left.schema] != [x[1:] for x in right.schema]:
            raise PlanError(f"Node '{op}': incompatible schemas")
        self.schema=left.schema
        self.left=Distinct(left,'sort',frames)
        self.right=Distinct(right,'sort',frames)
        self.children=[self.left,self.right]
        self.files=[]
    def open(self):
        self.files=[]
        for child in (self.left,self.right):
            f=SpillFile(self.schema);self.files.append(f)
            w=f.writer()
            try:
                child.open()
                while True:
                    row=child.next()
                    if row is None:break
                    w.append(row)
            finally:w.close();child.close()
        self.lr=self.files[0].reader();self.rr=self.files[1].reader()
        self.a=self.lr.next();self.b=self.rr.next()
        self.active=True
    def next(self):
        while self.a is not None or self.b is not None:
            if self.a is None:
                if self.name=='union':
                    r=self.b;self.b=self.rr.next();return self.emit(r)
                return None
            if self.b is None:
                if self.name in ('union','except'):
                    r=self.a;self.a=self.lr.next();return self.emit(r)
                return None
            ka=tuple(_value_key(v) for v in self.a)
            kb=tuple(_value_key(v) for v in self.b)
            self.comparisons+=1
            if ka==kb:
                r=self.a;self.a=self.lr.next();self.b=self.rr.next()
                if self.name!='except':return self.emit(r)
            elif ka<kb:
                r=self.a;self.a=self.lr.next()
                if self.name!='intersect':return self.emit(r)
            else:
                r=self.b;self.b=self.rr.next()
                if self.name=='union':return self.emit(r)
        return None
    def close(self):
        if hasattr(self,'lr'):self.lr.close();self.rr.close()
        for f in self.files:
            self.page_reads+=f.disk.reads;self.page_writes+=f.disk.writes
            f.path.unlink(missing_ok=True)
        self.files=[];self.active=False

class _DiskJoin(Operator):
    """Helpers for joins; temp tables are M1 DiskManager-backed slotted streams."""
    def __init__(self,name,left,right,condition,frames):
        super().__init__(name)
        self.left,self.right=left,right
        self.children=[left,right]
        self.frames=frames
        self.schema=left.schema+right.schema
        if len({x[0] for x in self.schema})!=len(self.schema):
            raise PlanError(f"Node '{name}': duplicate qualified column")
        self.condition=parse_condition(condition)
        self.relation=relation_for_schema(self.schema)
        check_condition(self.condition,self.schema)
        self.temp=[]
        self.result_iter=None
        self.left_key,self.right_key=self._eq_keys(condition)
    def _eq_keys(self,condition):
        bits=condition.strip().split('=')
        if len(bits)!=2:return None,None
        a,b=(x.strip() for x in bits)
        try:
            i=column_index(self.left.schema,a)
            j=column_index(self.right.schema,b)
            if self.left.schema[i][1:]!=self.right.schema[j][1:]:
                raise PlanError(f"Node '{self.name}': mismatched equality types")
            return i,j
        except PlanError:
            try:
                i=column_index(self.left.schema,b)
                j=column_index(self.right.schema,a)
                if self.left.schema[i][1:]!=self.right.schema[j][1:]:
                    raise PlanError(f"Node '{self.name}': mismatched equality types")
                return i,j
            except PlanError:
                return None,None
    def _file(self,schema):
        f=SpillFile(schema);self.temp.append(f);return f
    def _spool(self,child):
        f=self._file(child.schema);w=f.writer();child.open()
        try:
            while True:
                row=child.next()
                if row is None:break
                w.append(row)
        finally:
            w.close();child.close()
        return f
    def _pairs(self,r,s):
        self.comparisons+=1
        cand=r+s
        if evaluate_condition(self.condition,self.relation,cand):
            return cand
        return None
    def next(self):
        try:return self.emit(next(self.result_iter))
        except StopIteration:return None
    def close(self):
        if self.result_iter is not None and hasattr(self.result_iter,'close'):
            self.result_iter.close()
        for f in self.temp:
            self.page_reads+=f.disk.reads;self.page_writes+=f.disk.writes
            f.path.unlink(missing_ok=True)
        self.temp=[];self.active=False

class BlockNestedLoop(_DiskJoin):
    def __init__(self,left,right,condition,frames):
        super().__init__('nested_loop_join',left,right,condition,frames)
    def open(self):
        self.lf=self._spool(self.left);self.rf=self._spool(self.right)
        self.result_iter=self._produce()
        self.active=True
    def _produce(self):
        outer=self.lf.reader()
        try:
            while True:
                block=[];size=0
                from storage_engine.core import encode_record
                schema=self.lf.schema
                while size < (self.frames-2)*4096:
                    row=outer.next()
                    if row is None:break
                    block.append(row);size+=len(encode_temp_record(schema,row))+2
                if not block:break
                inner=self.rf.reader()
                try:
                    while True:
                        r=inner.next()
                        if r is None:break
                        for l in block:
                            candidate=self._pairs(l,r)
                            if candidate is not None:yield candidate
                finally:inner.close()
        finally:outer.close()

class SortMergeJoin(_DiskJoin):
    def __init__(self,left,right,condition,frames):
        super().__init__('sort_merge_join',left,right,condition,frames)
        if self.left_key is None:raise PlanError('Node sort_merge_join: equality column condition required')
    def open(self):
        self.lf=self._sorted_spool(self.left,self.left_key)
        self.rf=self._sorted_spool(self.right,self.right_key)
        self.result_iter=self._produce()
        self.active=True
    def _sorted_spool(self,child,index):
        sorter=ExternalSort(child,[[child.schema[index][0],'asc']],self.frames)
        f=self._file(child.schema);w=f.writer()
        try:
            sorter.open()
            while True:
                row=sorter.next()
                if row is None:break
                w.append(row)
        finally:
            w.close();sorter.close()
            self.page_reads+=sorter.page_reads
            self.page_writes+=sorter.page_writes
        return f
    def _produce(self):
        l=self.lf.reader();r=self.rf.reader()
        try:
            a=l.next();b=r.next()
            while a is not None and b is not None:
                ka=_value_key(a[self.left_key]);kb=_value_key(b[self.right_key]);self.comparisons+=1
                if ka<kb:a=l.next();continue
                if kb<ka:b=r.next();continue
                # Store just one equal-key run on disk: it may exceed the memory budget.
                same=self._file(self.right.schema);w=same.writer()
                while b is not None and _value_key(b[self.right_key])==ka:
                    w.append(b);b=r.next()
                w.close()
                while a is not None and _value_key(a[self.left_key])==ka:
                    scan=same.reader()
                    try:
                        while True:
                            rb=scan.next()
                            if rb is None:break
                            candidate=self._pairs(a,rb)
                            if candidate is not None:yield candidate
                    finally:scan.close()
                    a=l.next()
                # Release each duplicate-key run as soon as its group is done.
                # If the iterator closes early, _DiskJoin.close handles leftovers.
                self.page_reads+=same.disk.reads
                self.page_writes+=same.disk.writes
                same.path.unlink(missing_ok=True)
                self.temp.remove(same)
        finally:l.close();r.close()

class GraceHashJoin(_DiskJoin):
    def __init__(self,left,right,condition,frames):
        super().__init__('hash_join',left,right,condition,frames)
        if self.left_key is None:raise PlanError('Node hash_join: equality column condition required')
        self.partition_sizes=[]
        self.overflow_partitions=0
    def _hash(self,value):
        # Stable across Python processes; built-in hash() is salted for strings.
        from storage_engine.core import encode_record
        raw=str(value).encode('utf-8');h=2166136261
        for byte in raw:h=((h ^ byte)*16777619)&0xffffffff
        return h
    def open(self):
        p=self.frames-1
        self.lparts=[self._file(self.left.schema) for _ in range(p)]
        self.rparts=[self._file(self.right.schema) for _ in range(p)]
        for child,parts,index in ((self.left,self.lparts,self.left_key),(self.right,self.rparts,self.right_key)):
            source=self._spool(child)
            writers=[part.writer() for part in parts]
            rd=source.reader()
            try:
                while True:
                    row=rd.next()
                    if row is None:break
                    writers[self._hash(row[index])%p].append(row)
            finally:
                rd.close()
                for w in writers:w.close()
        self.partition_sizes=[(l.pages,r.pages) for l,r in zip(self.lparts,self.rparts)]
        self.result_iter=self._produce();self.active=True
    def _produce(self):
        from storage_engine.core import encode_record
        for lf,rf in zip(self.lparts,self.rparts):
            if lf.pages <= self.frames-2:
                # Partition fits in B-2 frames for the build table.
                table={}
                reader=lf.reader()
                try:
                    while True:
                        row=reader.next()
                        if row is None:break
                        table.setdefault(row[self.left_key],[]).append(row)
                finally:reader.close()
                probe=rf.reader()
                try:
                    while True:
                        row=probe.next()
                        if row is None:break
                        for left in table.get(row[self.right_key],[]):
                            cand=self._pairs(left,row)
                            if cand is not None:yield cand
                finally:probe.close()
            else:
                # Skew/overflow: block nested-loop fallback; never grow build hash beyond B.
                self.overflow_partitions+=1
                outer=lf.reader()
                try:
                    while True:
                        block=[];sz=0
                        while sz<(self.frames-2)*4096:
                            row=outer.next()
                            if row is None:break
                            block.append(row);sz+=len(encode_temp_record(lf.schema,row))+2
                        if not block:break
                        probe=rf.reader()
                        try:
                            while True:
                                right=probe.next()
                                if right is None:break
                                for left in block:
                                    cand=self._pairs(left,right)
                                    if cand is not None:yield cand
                        finally:probe.close()
                finally:outer.close()

class SpillScan(Operator):
    """Source for a temporary file; owns one input page at a time."""
    def __init__(self,file,schema):
        super().__init__('temp_scan')
        self.file=file;self.schema=schema
    def open(self):self.reader=self.file.reader();self.active=True
    def next(self):return self.emit(self.reader.next())
    def close(self):self.reader.close();self.active=False

class HashPartitioner(Unary):
    """Partition by a stable hash without holding more than B-1 output pages."""
    def __init__(self,child,keys,frames):
        super().__init__('hash_partition',child)
        self.keys=keys;self.indexes=[column_index(child.schema,k) for k in keys]
        self.frames=frames;self.temp=[]
    def _hash(self,values):
        h=2166136261
        for v in values:
            for byte in str(v).encode('utf-8')+b'\x00':h=((h^byte)*16777619)&0xffffffff
        return h
    def open(self):
        # Stage child output to one temp file: later partition scan needs only
        # one input page plus B-1 output pages (no live heap pool).
        source=SpillFile(self.schema);self.temp=[source]
        w=source.writer();self.child.open()
        try:
            while True:
                row=self.child.next()
                if row is None:break
                w.append(row)
        finally:w.close();self.child.close()
        self.parts=[SpillFile(self.schema) for _ in range(self.frames-1)]
        self.temp.extend(self.parts)
        ws=[f.writer() for f in self.parts]
        rd=source.reader()
        try:
            while True:
                row=rd.next()
                if row is None:break
                key=[row[i] for i in self.indexes]
                ws[self._hash(key)%(self.frames-1)].append(row)
        finally:
            rd.close()
            for writer in ws:writer.close()
        self.active=True
    def close(self):
        for f in self.temp:
            self.page_reads+=f.disk.reads;self.page_writes+=f.disk.writes
            f.path.unlink(missing_ok=True)
        self.temp=[];self.active=False

class HashDistinct(Unary):
    def __init__(self,child,frames):
        super().__init__('distinct',child)
        self.partition=HashPartitioner(child,[c[0] for c in child.schema],frames)
        self.children=[self.partition]
        self.frames=frames
    def open(self):
        self.partition.open();self.result=self._produce();self.active=True
    def _produce(self):
        from storage_engine.core import encode_record
        schema=[[f'c{i}',*c[1:]] for i,c in enumerate(self.schema)]
        for f in self.partition.parts:
            if f.pages<=self.frames-2:
                seen=set();r=f.reader()
                try:
                    while True:
                        row=r.next()
                        if row is None:break
                        key=tuple(row)
                        if key not in seen:seen.add(key);yield row
                finally:r.close()
            else:
                # Large/skewed partition: bounded external sorting fallback.
                op=Distinct(SpillScan(f,self.schema),'sort',self.frames)
                try:
                    op.open()
                    while True:
                        row=op.next()
                        if row is None:break
                        yield row
                finally:
                    op.close()
                    self.page_reads+=op.page_reads;self.page_writes+=op.page_writes
    def next(self):
        try:return self.emit(next(self.result))
        except StopIteration:return None
    def close(self):
        if hasattr(self,'result'):self.result.close()
        self.partition.close();self.active=False

class HashGroupBy(GroupBy):
    """Hash partitions first; aggregate each fitting partition in memory.
    Oversized/skewed partitions fall back to disk-backed sort grouping.
    """
    def __init__(self,child,keys,aggregates,frames):
        super().__init__(child,keys,aggregates,'hash',frames)
        self.partition=HashPartitioner(child,keys,frames)
        self.children=[self.partition]
    def open(self):
        self.partition.open();self.result=self._produce();self.active=True
    def _produce(self):
        if not any(f.pages for f in self.partition.parts) and not self.key_indices:
            if any(fun!='count' for fun,_,_ in self.aggs):raise PlanError('Node group_by: undefined aggregate on empty input')
            yield self._finish((),self._new_acc())
            return
        for f in self.partition.parts:
            if f.pages<=self.partition.frames-2:
                groups={};r=f.reader()
                try:
                    while True:
                        row=r.next()
                        if row is None:break
                        key=tuple(row[i] for i in self.key_indices)
                        if key not in groups:groups[key]=self._new_acc()
                        self._consume(groups[key],row)
                finally:r.close()
                for key in sorted(groups):yield self._finish(key,groups[key])
            else:
                op=GroupBy(SpillScan(f,self.partition.schema),self.key_names,
                           [[fn,col] for fn,col,_ in self.aggs],'sort',self.partition.frames)
                try:
                    op.open()
                    while True:
                        row=op.next()
                        if row is None:break
                        yield row
                finally:
                    op.close();self.page_reads+=op.page_reads;self.page_writes+=op.page_writes
    def next(self):
        try:return self.emit(next(self.result))
        except StopIteration:return None
    def close(self):
        if hasattr(self,'result'):self.result.close()
        self.partition.close();self.active=False
