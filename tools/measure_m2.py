"""Reproducible measurements on actual M1 heap files (no simulated I/O)."""
import csv
import math
import tempfile
from pathlib import Path
from storage_engine.core import Catalog, HeapFile
from execution_engine.core import build, nodes

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'measurements_m2'
OUT.mkdir(exist_ok=True)
SCHEMA=[['id','INT'],['payload','VARCHAR',200]]

def make_data(n):
    tmp=tempfile.TemporaryDirectory()
    db=Path(tmp.name)
    cat=Catalog(db,4)
    for table in ('R','S'):
        cat.create_table(table,SCHEMA)
    cat.close()
    for table in ('R','S'):
        heap=HeapFile(db/f'{table}.db', SCHEMA,4)
        for k in range(n):
            heap.insert([k, ('z' if table=='R' else 'y')*150])
        heap.close()
    return tmp,db

def run(db,plan,B):
    root=build(plan,str(db),B)
    count=0
    try:
        root.open()
        while root.next() is not None:
            count+=1
    finally:
        root.close()
    cumul={k:sum(node.counters()[k] for _,node in nodes(root)) for k in ('comparisons','page_reads','page_writes')}
    return count,cumul,root

def write(name,rows):
    with (OUT/name).open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)

join_rows=[]
for n in (40,180,600):
    tmp,db=make_data(n)
    # first page directory, following pages data.
    m=HeapFile(db/'R.db',SCHEMA,4)
    data_pages=m.disk.num_pages()-1
    m.close()
    for B in (4,16,64,256):
        for op in ('nested_loop_join','sort_merge_join','hash_join'):
            plan={'op':op,'condition':'R.id = S.id','left':{'op':'seqscan','table':'R'},'right':{'op':'seqscan','table':'S'}}
            count,stats,root=run(db,plan,B)
            assert count==n,(n,B,op,count)
            join_rows.append({'join':op,'rows_each':n,'frames':B,'M_pages':data_pages,'N_pages':data_pages,
                              'measured_reads':stats['page_reads'],'measured_writes':stats['page_writes'],
                              'comparisons':stats['comparisons'],
                              'BNL_textbook_reads':(data_pages+math.ceil(data_pages/(B-2))*data_pages) if op=='nested_loop_join' else ''})
    tmp.cleanup()
write('join_cost.csv',join_rows)

sort_rows=[]
for B,n in ((4,100),(4,300),(4,2200),(16,500),(16,2200),(64,2200)):
    tmp,db=make_data(n)
    heap=HeapFile(db/'R.db',SCHEMA,4);pages=heap.disk.num_pages()-1;heap.close()
    plan={'op':'sort','keys':[['R.id','desc']],'child':{'op':'seqscan','table':'R'}}
    count,stats,root=run(db,plan,B)
    assert count==n
    sort_rows.append({'frames':B,'rows':n,'input_pages':pages,'input_to_frames_ratio':round(pages/B,2),
                      'measured_passes':root.passes,'measured_reads':stats['page_reads'],
                      'measured_writes':stats['page_writes'],
                      'textbook_passes':1+math.ceil(math.log(max(1,math.ceil(pages/B)),B-1)) if pages>B else 1})
    tmp.cleanup()
write('sort_passes.csv',sort_rows)

# Overloaded hash partition with 40% shared key; verify no row-count overcount.
tmp=tempfile.TemporaryDirectory();db=Path(tmp.name)
c=Catalog(db,4)
for table in ('R','S'):c.create_table(table,SCHEMA)
c.close()
for table in ('R','S'):
    h=HeapFile(db/(table+'.db'),SCHEMA,4)
    for i in range(200):
        key=0 if i<80 else i
        h.insert([key,('x' if table=='R' else 'y')*150])
    h.close()
plan={'op':'hash_join','condition':'R.id = S.id','left':{'op':'seqscan','table':'R'},'right':{'op':'seqscan','table':'S'}}
n,st,root=run(db,plan,4)
assert n==80*80+120
write('hash_skew.csv',[{'frames':4,'rows_per_table':200,'skew_share':0.4,
                        'result_rows':n,'overflow_partitions':root.overflow_partitions,
                        'partition_pages':str(root.partition_sizes),'page_reads':st['page_reads'],'page_writes':st['page_writes'],
                        'comparisons':st['comparisons']}])
tmp.cleanup()
# Measure the same size under uniform, unique integer keys for comparison.
base_tmp,base_db=make_data(200)
normal_n,normal_st,normal_root=run(base_db,plan,4)
write('skew_vs_uniform.csv',[
    {'scenario':'uniform','rows_each':200,'result_rows':normal_n,'reads':normal_st['page_reads'],
     'writes':normal_st['page_writes'],'comparisons':normal_st['comparisons'],
     'overflow_partitions':normal_root.overflow_partitions},
    {'scenario':'40_percent_skew','rows_each':200,'result_rows':n,'reads':st['page_reads'],
     'writes':st['page_writes'],'comparisons':st['comparisons'],
     'overflow_partitions':root.overflow_partitions},
])
base_tmp.cleanup()
print('Recorded',len(join_rows),'join trials,',len(sort_rows),'sort trials, plus skew/uniform comparison.')
