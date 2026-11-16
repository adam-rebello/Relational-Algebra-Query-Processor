"""Temporary page files for M2. Every temporary read/write uses M1 DiskManager.

Page layout: uint16 number of records, then [uint16 length, record bytes]...
A reader holds at most one 4096-byte page; a writer holds one output page.
"""
import struct
import tempfile
from pathlib import Path
from storage_engine.core import DiskManager, encode_record, decode_record, PAGE_SIZE

def encode_temp_record(schema, row):
    """Encode intermediate rows; REAL is allowed only in executor temp files."""
    if len(schema) != len(row):
        raise ValueError('Temporary row length does not match schema')
    output = bytearray()
    for column, value in zip(schema, row):
        if column[1] == 'REAL':
            output.extend(struct.pack('<d', float(value)))
        else:
            output.extend(encode_record([column], [value]))
    return bytes(output)


def decode_temp_record(schema, data):
    """Decode the executor-only REAL field without changing Module 1 formats."""
    result = []
    offset = 0
    for column in schema:
        kind = column[1]
        if kind == 'REAL':
            length = 8
            value = struct.unpack_from('<d', data, offset)[0]
        elif kind == 'INT':
            length = 4
            value = decode_record([column], data[offset:offset+length])[0]
        else:
            length = 2 + struct.unpack_from('<H', data, offset)[0]
            value = decode_record([column], data[offset:offset+length])[0]
        result.append(value)
        offset += length
    if offset != len(data):
        raise ValueError('Temporary record has trailing bytes')
    return result

class SpillFile:
    def __init__(self, schema):
        self.schema = [[f'c{i}', *col[1:]] for i,col in enumerate(schema)]
        handle = tempfile.NamedTemporaryFile(prefix='m2_', suffix='.db', delete=False)
        self.path = Path(handle.name)
        handle.close()
        self.disk = DiskManager(self.path)
        self.reads = self.writes = 0
    def writer(self): return SpillWriter(self)
    def reader(self): return SpillReader(self)
    def remove(self):
        self.reads += self.disk.reads
        self.writes += self.disk.writes
        self.path.unlink(missing_ok=True)
    @property
    def pages(self): return self.disk.num_pages()

class SpillWriter:
    def __init__(self, file):
        self.file = file
        self.data = bytearray(PAGE_SIZE)
        self.pos = 2
        self.count = 0
        self.closed = False
    def append(self, row):
        payload = encode_temp_record(self.file.schema, row)
        if len(payload) + 4 > PAGE_SIZE: raise ValueError('temporary record exceeds page capacity')
        if self.pos + len(payload) + 2 > PAGE_SIZE: self._flush()
        struct.pack_into('<H', self.data, self.pos, len(payload))
        self.pos += 2
        self.data[self.pos:self.pos + len(payload)] = payload
        self.pos += len(payload)
        self.count += 1
    def _flush(self):
        if not self.count: return
        struct.pack_into('<H', self.data, 0, self.count)
        page_id = self.file.disk.allocate_page()
        self.file.disk.write_page(page_id, self.data)
        self.data = bytearray(PAGE_SIZE)
        self.pos, self.count = 2, 0
    def close(self):
        if not self.closed:
            self._flush()
            self.closed = True

class SpillReader:
    def __init__(self, file):
        self.file = file
        self.page = -1
        self.data = None
        self.pos = 2
        self.left = 0
        self.closed = False
    def next(self):
        if self.closed: return None
        while self.left == 0:
            self.page += 1
            if self.page >= self.file.pages: return None
            self.data = self.file.disk.read_page(self.page)
            self.left = struct.unpack_from('<H',self.data,0)[0]
            self.pos = 2
        length = struct.unpack_from('<H', self.data, self.pos)[0]
        self.pos += 2
        row = decode_temp_record(self.file.schema, bytes(self.data[self.pos:self.pos + length]))
        self.pos += length
        self.left -= 1
        return row
    def close(self):
        self.data = None
        self.closed = True
