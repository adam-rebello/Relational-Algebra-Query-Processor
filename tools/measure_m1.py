"""Reproducible M1 experiments. Generated traces are NOT instructor trace files.

Run: python tools/measure_m1.py --output measurements_m1
"""
import argparse
import csv
import math
import struct
from pathlib import Path
from tempfile import TemporaryDirectory

from storage_engine.core import (
    BufferPool, DirectoryPage, DiskManager, HeapFile, SlottedPage,
    TraceDisk, encode_record, parse_schema,
)


def write_csv(path, headings, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(headings);w.writerows(rows)


def capacity_measurements(path):
    specs=[('four_int','a:INT,b:INT,c:INT,d:INT',[1,2,3,4]),
           ('short_varchar','a:INT,b:VARCHAR(10),c:INT',[1,'bob',3]),
           ('long_varchar','a:INT,b:VARCHAR(200),c:INT',[1,'x'*180,3])]
    rows=[]
    with TemporaryDirectory() as tmp:
        for name,schema_text,values in specs:
            schema=parse_schema(schema_text)
            length=len(encode_record(schema,values))
            computed=4088//(length+4)
            heap=HeapFile(Path(tmp)/f'{name}.db',schema,frames=2)
            for i in range(computed+1):
                heap.insert(values)
            page=heap.pool.fetch_page(1)
            measured=SlottedPage(page.data).slot_count
            heap.pool.unpin_page(1)
            rows.append((name,schema_text,length,computed,measured,
                         heap.disk.num_pages()-1))
            heap.close()
    write_csv(path,('schema','definition','record_bytes','predicted_first_page_records',
                    'measured_first_page_records','data_pages'),rows)
    return rows


def test_traces():
    # Five reproducible reference-like workloads; replace with instructor traces
    # when the published input files become available.
    return {
        'synthetic_1_worked': [1,2,3,1,4,2],
        'synthetic_2_hotset': [i%12 for i in range(1200)],
        'synthetic_3_seq80x10': list(range(80))*10,
        'synthetic_4_skew': [0 if i%5 else (i//5)%80 for i in range(1000)],
        'synthetic_5_mixed': [i%21 if i%3 else (i*13)%181 for i in range(2000)],
    }


def policy_measurements(path):
    rows=[]
    for trace_name,values in test_traces().items():
        for policy in ('lru','clock'):
            for B in (4,16,64,256):
                p=BufferPool(TraceDisk(),B,policy)
                for page in values:
                    p.fetch_page(page);p.unpin_page(page)
                stats=p.stats()
                rows.append((trace_name,policy,B,len(values),stats['hits'],
                             stats['misses'],stats['evictions'],stats['reads'],
                             stats['writes'],f"{stats['hits']/len(values):.6f}"))
    write_csv(path,('trace','policy','frames','requests','hits','misses','evictions',
                    'reads','writes','hit_rate'),rows)
    return rows


def scan_measurements(path):
    with TemporaryDirectory() as tmp:
        file=Path(tmp)/'R.db'
        disk=DiskManager(file)
        assert disk.allocate_page()==0
        directory=DirectoryPage.initialize(bytearray(4096),0)
        schema=parse_schema('a:INT,b:VARCHAR(5)')
        for i in range(500):
            page_id=disk.allocate_page()
            raw=bytearray(4096)
            data_page=SlottedPage.initialize(raw,page_id)
            data_page.insert(encode_record(schema,[i,'x']))
            disk.write_page(page_id,raw)
            directory.add(page_id,data_page.free_space)
        disk.write_page(0,directory.data)
        rows=[]
        for B in (2,8,64):
            heap=HeapFile(file,schema,frames=B)
            output_count=sum(1 for _ in heap.scan())
            stats=heap.pool.stats()
            rows.append((B,output_count,heap.disk.num_pages(),stats['reads'],stats['writes']))
            heap.close()
    write_csv(path,('frames','rows_scanned','file_pages','page_reads','page_writes'),rows)
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='measurements_m1')
    args=parser.parse_args()
    out=Path(args.output)
    capacity=capacity_measurements(out/'capacity.csv')
    policies=policy_measurements(out/'policies_SYNTHETIC.csv')
    scans=scan_measurements(out/'scan_cost.csv')
    print('Page capacities:',capacity)
    print('500-page scans:',scans)
    print('Trace rows:',len(policies))


if __name__ == '__main__':
    main()
