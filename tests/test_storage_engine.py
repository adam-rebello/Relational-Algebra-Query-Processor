"""M1 storage engine contract and regression tests."""
import json
import struct
import subprocess
import sys

import pytest

from storage_engine.core import (
    PAGE_SIZE, BufferPool, Catalog, DirectoryPage, DiskManager, HeapFile,
    SlottedPage, StorageError, TraceDisk, decode_record, encode_record,
    parse_schema,
)


def test_exact_page_layout():
    p = SlottedPage.initialize(bytearray(PAGE_SIZE), 3)
    assert (p.slot_count, p.free_end, p.free_space) == (0, 4096, 4088)
    for i, data, wanted in [(0, b'a'*13, (1,4083,4071)),
                            (1, b'b'*20, (2,4063,4047)),
                            (2, b'c'*13, (3,4050,4030))]:
        assert p.insert(data) == i
        assert (p.slot_count, p.free_end, p.free_space) == wanted
    p.delete(1)
    assert (p.slot_count, p.free_end, p.free_space, p.slot(1)) == (3,4050,4030,(0,0))
    assert p.get(0) == b'a'*13
    with pytest.raises(StorageError, match='Deleted rid'):
        p.get(1)
    with pytest.raises(StorageError, match='Deleted rid'):
        p.delete(1)
    with pytest.raises(StorageError, match='Invalid rid'):
        p.get(20)


def test_240_fixed_length_records():
    p = SlottedPage.initialize(bytearray(PAGE_SIZE), 1)
    for index in range(240):
        assert p.insert(bytes(13)) == index
    assert p.insert(bytes(13)) is None
    assert p.slot_count == 240


@pytest.mark.parametrize('policy,expected', [('lru',(1,5,2)),('clock',(2,4,1))])
def test_instructor_trace(policy, expected):
    pool = BufferPool(TraceDisk(),3,policy)
    for page_id in (1,2,3,1,4,2):
        pool.fetch_page(page_id)
        pool.unpin_page(page_id)
    s = pool.stats()
    assert (s['hits'],s['misses'],s['evictions']) == expected
    assert s['reads'] == s['misses']
    assert s['writes'] == 0


@pytest.mark.parametrize('policy', ['clock','lru'])
def test_pin_rejects_evict_and_double_unpin(policy):
    disk = TraceDisk()
    p = BufferPool(disk,2,policy)
    p.fetch_page(1)
    p.fetch_page(2)
    with pytest.raises(StorageError, match='no unpinned frame'):
        p.fetch_page(3)
    assert disk.reads == 2
    p.unpin_page(2)
    p.fetch_page(3)
    p.unpin_page(3)
    with pytest.raises(StorageError, match='pin count'):
        p.unpin_page(3)
    assert 1 in p.page_table


def test_dirty_write_counter_and_flush():
    pool = BufferPool(TraceDisk(),1,'lru')
    pool.fetch_page(2)
    pool.unpin_page(2,True)
    pool.fetch_page(3)
    assert pool.stats()['writes'] == 1
    pool.unpin_page(3,True)
    pool.flush_all()
    assert pool.stats()['writes'] == 2
    pool.flush_all()
    assert pool.stats()['writes'] == 2


def test_record_encodings():
    schema = parse_schema('a:INT,b:VARCHAR(5),c:INT')
    record = encode_record(schema, [42,'bob',7])
    assert record == bytes.fromhex('2a0000000300626f6207000000')
    assert decode_record(schema,record) == [42,'bob',7]
    assert decode_record([['x','VARCHAR',8]],encode_record([['x','VARCHAR',8]],['é'])) == ['é']
    for vals in ([2**32,'ok',1], ['no','ok',1], [1,'toolong',2]):
        with pytest.raises(StorageError):
            encode_record(schema, vals)


def test_disk_manager_exact_pages(tmp_path):
    disk = DiskManager(tmp_path/'R.db')
    assert disk.allocate_page() == 0
    assert disk.allocate_page() == 1
    assert (tmp_path/'R.db').stat().st_size == 8192
    p = bytearray(PAGE_SIZE)
    struct.pack_into('<i',p,0,-42)
    disk.write_page(1,p)
    assert disk.read_page(1)[:4] == bytes.fromhex('d6ffffff')
    assert (disk.reads,disk.writes) == (1,1)


def test_heap_insert_scan_delete_reopen(tmp_path):
    schema = parse_schema('id:INT,name:VARCHAR(20)')
    path = tmp_path/'Students.db'
    heap = HeapFile(path,schema,frames=2)
    rids = [heap.insert([i, f'user{i}']) for i in range(320)]
    assert rids[0] == (1,0)
    assert heap.disk.num_pages() > 2
    assert heap.get(rids[10]) == [10,'user10']
    heap.delete(rids[10])
    with pytest.raises(StorageError,match='Deleted rid'):
        heap.get(rids[10])
    live = list(heap.scan())
    assert len(live) == 319
    assert all(frame is None or frame.pin_count == 0 for frame in heap.pool.frames)
    heap.close()
    second = HeapFile(path,schema,frames=2)
    assert len(list(second.scan())) == 319
    for rid, row in list(second.scan()):
        second.delete(rid)
    assert list(second.scan()) == []
    second.close()


def test_catalog_persists_and_updates(tmp_path):
    catalog = Catalog(tmp_path,frames=2)
    schema = parse_schema('x:INT')
    catalog.create_table('R',schema)
    catalog.update_table('R',num_tuples=12,num_pages=3)
    assert catalog.get_table('R')['num_tuples'] == 12
    with pytest.raises(StorageError, match='already exists'):
        catalog.create_table('R',schema)
    catalog.close()
    reopened = Catalog(tmp_path,frames=2)
    assert reopened.get_table('R')['schema'] == schema
    assert reopened.get_table('R')['num_pages'] == 3
    reopened.close()


def test_directory_page_capacity():
    page = DirectoryPage.initialize(bytearray(PAGE_SIZE),0)
    assert DirectoryPage.MAX_ENTRIES == 681
    for i in range(681):
        page.add(i+1,4088)
    assert page.count == 681
    with pytest.raises(StorageError,match='Directory is full'):
        page.add(682,4088)


def run_cli(*args, cwd=None):
    from pathlib import Path
    return subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]/'storage.py'), *map(str,args)],
                          capture_output=True,text=True,cwd=cwd)


def test_cli_end_to_end(tmp_path):
    db=tmp_path/'db'
    csvfile=tmp_path/'rows.csv'
    csvfile.write_text('42,bob,7\n43,"hello, world",8\n42,bob,7\n',encoding='utf-8')
    create=run_cli('create-table','--db',db,'--name','R','--schema','a:INT,b:VARCHAR(20),c:INT')
    assert create.returncode == 0, create.stderr
    load=run_cli('load','--db',db,'--table','R','--file',csvfile)
    assert load.returncode == 0, load.stderr
    scan=run_cli('scan','--db',db,'--table','R','--frames','2','--json')
    assert scan.returncode == 0,scan.stderr
    data=json.loads(scan.stdout)
    assert data['rows'] == [[42,'bob',7],[43,'hello, world',8],[42,'bob',7]]
    assert set(data['stats']) == {'hits','misses','evictions','reads','writes'}
    assert json.loads(run_cli('scan','--db',db,'--table','R','--frames','2','--limit','1','--json').stdout)['rows']==[[42,'bob',7]]
    assert json.loads(run_cli('layout','--db',db,'--table','R','--page','1').stdout)['slot_count']==3
    assert json.loads(run_cli('scan','--db',db,'--table','R','--frames','2','--json').stdout)['stats'] == data['stats']


def test_cli_bad_csv_line(tmp_path):
    db=tmp_path/'db'
    assert run_cli('create-table','--db',db,'--name','R','--schema','a:INT,b:VARCHAR(3)').returncode==0
    file=tmp_path/'bad.csv';file.write_text('1,ok\n2,too-long\n')
    result=run_cli('load','--db',db,'--table','R','--file',file)
    assert result.returncode != 0
    assert 'line 2' in result.stderr and 'b' in result.stderr
    scan=json.loads(run_cli('scan','--db',db,'--table','R','--json').stdout)
    assert scan['rows']==[[1,'ok']]


def test_heap_directory_chain_over_681_data_pages(tmp_path):
    schema = [[f'x{i}', 'VARCHAR', 255] for i in range(15)]
    values = ['x'*255]*15  # only one record fits each page
    heap = HeapFile(tmp_path/'Wide.db',schema,frames=2)
    for _ in range(683):
        heap.insert(values)
    assert heap.layout(0)['entry_count'] == 681
    assert heap.layout(682)['kind'] == 'directory'
    assert len(list(heap.scan())) == 683
    heap.close()


def test_buffer_pool_close_rejects_pins_and_frees_frames():
    pool = BufferPool(TraceDisk(),2,'clock')
    pool.fetch_page(1)
    with pytest.raises(StorageError,match='pinned'):
        pool.close()
    pool.unpin_page(1,True)
    pool.close()
    assert all(frame is None for frame in pool.frames)
    assert pool.stats()['writes']==1
