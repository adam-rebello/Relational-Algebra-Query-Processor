"""Disk-backed pages, slotted records, directory pages and buffer management.

All physical page I/O goes through DiskManager. Files contain only 4096-byte pages.
"""
import json
import struct
from dataclasses import dataclass
from pathlib import Path

PAGE_SIZE = 4096
INVALID_PAGE = 0xffffffff


class StorageError(Exception):
    pass


class DiskManager:
    """Fixed-page binary file with explicit read/write counters."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.reads = 0
        self.writes = 0
        if self.path.stat().st_size % PAGE_SIZE:
            raise StorageError(f"Corrupt page file: {self.path}")

    def num_pages(self):
        return self.path.stat().st_size // PAGE_SIZE

    def allocate_page(self):
        page_id = self.num_pages()
        with self.path.open('ab') as handle:
            handle.write(bytes(PAGE_SIZE))
        # Allocation creates an empty page; counters track explicit page read/write calls.
        return page_id

    def read_page(self, page_id):
        if not 0 <= page_id < self.num_pages():
            raise StorageError(f"Unknown page {page_id} in {self.path.name}")
        with self.path.open('rb') as handle:
            handle.seek(page_id * PAGE_SIZE)
            data = handle.read(PAGE_SIZE)
        self.reads += 1
        if len(data) != PAGE_SIZE:
            raise StorageError(f"Short read on page {page_id}")
        return bytearray(data)

    def write_page(self, page_id, data):
        if len(data) != PAGE_SIZE or not 0 <= page_id < self.num_pages():
            raise StorageError(f"Invalid page write: {page_id}")
        with self.path.open('r+b') as handle:
            handle.seek(page_id * PAGE_SIZE)
            handle.write(data)
        self.writes += 1


class TraceDisk:
    """Synthetic pages for trace testing, with the same DiskManager API."""
    def __init__(self):
        self.reads = self.writes = 0

    def read_page(self, page_id):
        if page_id < 0:
            raise StorageError(f"Negative page id: {page_id}")
        self.reads += 1
        return bytearray(PAGE_SIZE)

    def write_page(self, page_id, data):
        self.writes += 1

    def allocate_page(self):
        raise StorageError('TraceDisk does not allocate pages')


@dataclass
class Frame:
    page_id: int
    data: bytearray
    pin_count: int = 1
    dirty: bool = False
    ref: int = 1
    last_access: int = 0


class BufferPool:
    """Bounded buffer pool. Resident pages always occupy one of B frames."""
    def __init__(self, disk, frames=8, policy='lru'):
        if frames < 1:
            raise StorageError('Frame count must be positive')
        if policy.lower() not in ('lru', 'clock'):
            raise StorageError('Policy must be lru or clock')
        self.disk = disk
        self.capacity = frames
        self.policy = policy.lower()
        self.frames = [None] * frames
        self.page_table = {}
        self.clock_hand = 0
        self.tick = 0
        self.hits = self.misses = self.evictions = 0

    def _slot(self):
        """Choose a free frame or an unpinned victim deterministically."""
        if self.policy == 'lru':
            for i, frame in enumerate(self.frames):
                if frame is None:
                    return i
            eligible = [(frame.last_access, i) for i, frame in enumerate(self.frames)
                        if frame.pin_count == 0]
            if not eligible:
                raise StorageError('no unpinned frame available')
            return min(eligible)[1]

        # CLOCK uses the hand even when filling initially empty frames.
        swept = 0
        while swept <= 2 * self.capacity:
            i = self.clock_hand
            frame = self.frames[i]
            self.clock_hand = (i + 1) % self.capacity
            if frame is None:
                return i
            if frame.pin_count:
                swept += 1
                continue
            if frame.ref:
                frame.ref = 0
                swept += 1
                continue
            return i
        raise StorageError('no unpinned frame available')

    def _place(self, page_id, data, dirty):
        i = self._slot()
        victim = self.frames[i]
        if victim is not None:
            if victim.pin_count:
                raise StorageError('Attempted to evict pinned frame')
            if victim.dirty:
                self.disk.write_page(victim.page_id, victim.data)
            del self.page_table[victim.page_id]
            self.evictions += 1
        self.tick += 1
        frame = Frame(page_id, data, dirty=dirty, last_access=self.tick)
        self.frames[i] = frame
        self.page_table[page_id] = i
        return frame

    def fetch_page(self, page_id):
        if page_id in self.page_table:
            self.hits += 1
            frame = self.frames[self.page_table[page_id]]
            frame.pin_count += 1
            frame.ref = 1
            self.tick += 1
            frame.last_access = self.tick
            return frame
        # Reject a saturated pool BEFORE performing disk I/O.
        if all(frame is not None and frame.pin_count for frame in self.frames):
            raise StorageError('no unpinned frame available')
        # Select victim before read so failed reads do not modify policy state.
        # Directory/heap callers only request existing pages.
        data = self.disk.read_page(page_id)
        self.misses += 1
        return self._place(page_id, data, dirty=False)

    def unpin_page(self, page_id, is_dirty=False):
        if page_id not in self.page_table:
            raise StorageError(f'Cannot unpin page {page_id}: not resident')
        frame = self.frames[self.page_table[page_id]]
        if frame.pin_count == 0:
            raise StorageError(f'Cannot unpin page {page_id}: pin count already zero')
        frame.dirty |= bool(is_dirty)
        frame.pin_count -= 1

    def new_page(self):
        if all(frame is not None and frame.pin_count for frame in self.frames):
            raise StorageError('no unpinned frame available')
        page_id = self.disk.allocate_page()
        return self._place(page_id, bytearray(PAGE_SIZE), dirty=True)

    def flush_all(self):
        for frame in self.frames:
            if frame is not None and frame.dirty:
                self.disk.write_page(frame.page_id, frame.data)
                frame.dirty = False

    def stats(self):
        return dict(hits=self.hits, misses=self.misses,
                    evictions=self.evictions, reads=self.disk.reads,
                    writes=self.disk.writes)

    def close(self):
        """Flush and release resident frames before another file pool opens."""
        if any(frame is not None and frame.pin_count for frame in self.frames):
            raise StorageError('Cannot close buffer pool while pages are pinned')
        self.flush_all()
        self.frames = [None] * self.capacity
        self.page_table.clear()


class SlottedPage:
    """Header: uint32 page_id, uint16 slot_count, uint16 free_end.

    Slot i: uint16 offset, uint16 record_length. Dead slots are (0,0).
    """
    def __init__(self, data):
        self.data = data
        if len(data) != PAGE_SIZE:
            raise StorageError('Slotted pages must be 4096 bytes')

    @staticmethod
    def initialize(data, page_id):
        data[:] = bytes(PAGE_SIZE)
        struct.pack_into('<IHH', data, 0, page_id, 0, PAGE_SIZE)
        return SlottedPage(data)

    @property
    def page_id(self):
        return struct.unpack_from('<I', self.data, 0)[0]

    @property
    def slot_count(self):
        return struct.unpack_from('<H', self.data, 4)[0]

    @property
    def free_end(self):
        return struct.unpack_from('<H', self.data, 6)[0]

    @property
    def free_space(self):
        return self.free_end - (8 + 4 * self.slot_count)

    def slot(self, slot_no):
        if not 0 <= slot_no < self.slot_count:
            raise StorageError(f'Invalid rid ({self.page_id}, {slot_no})')
        return struct.unpack_from('<HH', self.data, 8 + slot_no * 4)

    def insert(self, record):
        length = len(record)
        if length > PAGE_SIZE - 8:
            raise StorageError('Record longer than 4088 bytes')
        if self.free_space < length + 4:
            return None
        start = self.free_end - length
        self.data[start:start + length] = record
        slot_no = self.slot_count
        struct.pack_into('<HH', self.data, 8 + 4 * slot_no, start, length)
        struct.pack_into('<HH', self.data, 4, slot_no + 1, start)
        return slot_no

    def get(self, slot_no):
        offset, length = self.slot(slot_no)
        if offset == 0:
            raise StorageError(f'Deleted rid ({self.page_id}, {slot_no})')
        return bytes(self.data[offset:offset + length])

    def delete(self, slot_no):
        self.get(slot_no)  # checks bounds and already-deleted records
        struct.pack_into('<HH', self.data, 8 + 4 * slot_no, 0, 0)

    def layout(self):
        return dict(page_id=self.page_id, slot_count=self.slot_count,
                    free_end=self.free_end, free_space=self.free_space,
                    slots=[{'slot': i, 'offset': self.slot(i)[0],
                            'length': self.slot(i)[1]} for i in range(self.slot_count)])


class DirectoryPage:
    """Header: uint32 page_id, uint32 next_directory, uint16 entry_count.

    Directory entry: uint32 data_page_id, uint16 free_bytes.
    """
    MAX_ENTRIES = (PAGE_SIZE - 10) // 6

    def __init__(self, data):
        self.data = data

    @staticmethod
    def initialize(data, page_id):
        data[:] = bytes(PAGE_SIZE)
        struct.pack_into('<IIH', data, 0, page_id, INVALID_PAGE, 0)
        return DirectoryPage(data)

    @property
    def page_id(self):
        return struct.unpack_from('<I', self.data, 0)[0]

    @property
    def next_page(self):
        return struct.unpack_from('<I', self.data, 4)[0]

    @next_page.setter
    def next_page(self, value):
        struct.pack_into('<I', self.data, 4, value)

    @property
    def count(self):
        return struct.unpack_from('<H', self.data, 8)[0]

    def entry(self, i):
        if not 0 <= i < self.count:
            raise StorageError('Invalid directory entry')
        return struct.unpack_from('<IH', self.data, 10 + i * 6)

    def add(self, page_id, free_bytes):
        if self.count >= self.MAX_ENTRIES:
            raise StorageError('Directory is full')
        struct.pack_into('<IH', self.data, 10 + self.count * 6, page_id, free_bytes)
        struct.pack_into('<H', self.data, 8, self.count + 1)

    def set_free(self, i, free_bytes):
        page_id, _ = self.entry(i)
        struct.pack_into('<IH', self.data, 10 + i * 6, page_id, free_bytes)

    def layout(self):
        return dict(page_id=self.page_id, next_dir_page=self.next_page,
                    entry_count=self.count,
                    entries=[dict(page_id=self.entry(i)[0], free_bytes=self.entry(i)[1])
                             for i in range(self.count)])


def parse_schema(text):
    """Parse a:INT,b:VARCHAR(20) without a parser generator or regex."""
    schema = []
    for col in text.split(','):
        if ':' not in col:
            raise StorageError(f'Invalid schema column: {col}')
        name, data_type = [part.strip() for part in col.split(':', 1)]
        if not name or not (name[0].isalpha() or name[0] == '_') or not all(
                c.isalnum() or c == '_' for c in name):
            raise StorageError(f'Invalid column name: {name}')
        upper = data_type.upper()
        if upper == 'INT':
            definition = [name, 'INT']
        elif upper.startswith('VARCHAR(') and upper.endswith(')'):
            try:
                max_length = int(upper[8:-1])
            except ValueError:
                raise StorageError(f'Invalid VARCHAR length: {data_type}') from None
            if not 1 <= max_length <= 255:
                raise StorageError('VARCHAR length must be from 1 to 255')
            definition = [name, 'VARCHAR', max_length]
        else:
            raise StorageError(f'Unknown type: {data_type}')
        if any(existing[0] == name for existing in schema):
            raise StorageError(f'Duplicate column: {name}')
        schema.append(definition)
    if not schema:
        raise StorageError('Schema must contain columns')
    return schema


def encode_record(schema, values):
    if len(schema) != len(values):
        raise StorageError(f'Expected {len(schema)} fields, got {len(values)}')
    data = bytearray()
    for definition, value in zip(schema, values):
        name, kind = definition[:2]
        if kind == 'INT':
            try:
                integer = int(value)
                if isinstance(value, str) and value.strip() != str(integer):
                    raise ValueError()
                data += struct.pack('<i', integer)
            except (ValueError, OverflowError, struct.error):
                raise StorageError(f"Column {name}: invalid INT {value!r}") from None
        else:
            if not isinstance(value, str):
                raise StorageError(f'Column {name}: VARCHAR must be text')
            encoded = value.encode('utf-8')
            if len(encoded) > definition[2]:
                raise StorageError(f'Column {name}: VARCHAR({definition[2]}) exceeded')
            data += struct.pack('<H', len(encoded)) + encoded
    return bytes(data)


def decode_record(schema, record):
    values = []
    position = 0
    for definition in schema:
        if definition[1] == 'INT':
            if position + 4 > len(record):
                raise StorageError('Truncated INT record')
            values.append(struct.unpack_from('<i', record, position)[0])
            position += 4
        else:
            if position + 2 > len(record):
                raise StorageError('Truncated VARCHAR length')
            length = struct.unpack_from('<H', record, position)[0]
            position += 2
            if length > definition[2] or position + length > len(record):
                raise StorageError('Invalid VARCHAR record length')
            values.append(record[position:position + length].decode('utf-8'))
            position += length
    if position != len(record):
        raise StorageError('Record has trailing bytes')
    return values


class HeapFile:
    """Heap with page 0 directory and first-fit directory-based insertion."""
    def __init__(self, path, schema, frames=8, policy='lru'):
        self.disk = DiskManager(path)
        self.pool = BufferPool(self.disk, frames, policy)
        self.schema = schema
        self.name = Path(path).stem
        if self.disk.num_pages() == 0:
            frame = self.pool.new_page()
            DirectoryPage.initialize(frame.data, frame.page_id)
            self.pool.unpin_page(frame.page_id, True)
            self.pool.flush_all()

    def insert(self, values):
        record = encode_record(self.schema, values)
        if len(record) > 4088:
            raise StorageError(f'Table {self.name}: record longer than 4088 bytes')
        dir_id = 0
        while True:
            frame = self.pool.fetch_page(dir_id)
            directory = DirectoryPage(frame.data)
            chosen = None
            for i in range(directory.count):
                page_id, free_bytes = directory.entry(i)
                if free_bytes >= len(record) + 4:
                    chosen = (page_id, i)
                    break
            next_dir = directory.next_page
            dir_count = directory.count
            self.pool.unpin_page(dir_id)
            if chosen:
                data_page, entry_no = chosen
                data_frame = self.pool.fetch_page(data_page)
                page = SlottedPage(data_frame.data)
                slot = page.insert(record)
                if slot is None:
                    self.pool.unpin_page(data_page)
                    raise StorageError('Free-space directory is out of sync')
                free_bytes = page.free_space
                self.pool.unpin_page(data_page, True)
                frame = self.pool.fetch_page(dir_id)
                DirectoryPage(frame.data).set_free(entry_no, free_bytes)
                self.pool.unpin_page(dir_id, True)
                return (data_page, slot)
            if next_dir != INVALID_PAGE:
                dir_id = next_dir
                continue
            if dir_count == DirectoryPage.MAX_ENTRIES:
                # Leave the existing directory unpinned to keep the B=2 bound.
                new_dir = self.pool.new_page()
                new_dir_id = new_dir.page_id
                DirectoryPage.initialize(new_dir.data, new_dir_id)
                self.pool.unpin_page(new_dir_id, True)
                previous = self.pool.fetch_page(dir_id)
                DirectoryPage(previous.data).next_page = new_dir_id
                self.pool.unpin_page(dir_id, True)
                dir_id = new_dir_id

            new_frame = self.pool.new_page()
            data_page = new_frame.page_id
            page = SlottedPage.initialize(new_frame.data, data_page)
            slot = page.insert(record)
            free_bytes = page.free_space
            self.pool.unpin_page(data_page, True)
            frame = self.pool.fetch_page(dir_id)
            DirectoryPage(frame.data).add(data_page, free_bytes)
            self.pool.unpin_page(dir_id, True)
            return (data_page, slot)

    def get(self, rid):
        page_id, slot = rid
        frame = self.pool.fetch_page(page_id)
        try:
            return decode_record(self.schema, SlottedPage(frame.data).get(slot))
        finally:
            self.pool.unpin_page(page_id)

    def delete(self, rid):
        page_id, slot = rid
        frame = self.pool.fetch_page(page_id)
        try:
            SlottedPage(frame.data).delete(slot)
        finally:
            self.pool.unpin_page(page_id, True)
        # No space reclaimed; directory's free_bytes is unchanged.

    def scan(self):
        """Yield (rid, row) with <= one directory and one data page pinned."""
        dir_id = 0
        while dir_id != INVALID_PAGE:
            directory_frame = self.pool.fetch_page(dir_id)
            try:
                directory = DirectoryPage(directory_frame.data)
                next_dir = directory.next_page
                for i in range(directory.count):
                    data_page, _ = directory.entry(i)
                    frame = self.pool.fetch_page(data_page)
                    try:
                        page = SlottedPage(frame.data)
                        for slot in range(page.slot_count):
                            if page.slot(slot)[0] != 0:
                                yield (data_page, slot), decode_record(self.schema, page.get(slot))
                    finally:
                        self.pool.unpin_page(data_page)
            finally:
                self.pool.unpin_page(dir_id)
            dir_id = next_dir

    def layout(self, page_id):
        frame = self.pool.fetch_page(page_id)
        try:
            # Determine whether this page belongs to the directory chain.
            directory_ids = set()
            current = 0
            while current != INVALID_PAGE:
                directory_ids.add(current)
                d_frame = self.pool.fetch_page(current) if current != page_id else frame
                current = DirectoryPage(d_frame.data).next_page
                if d_frame is not frame:
                    self.pool.unpin_page(d_frame.page_id)
            if page_id in directory_ids:
                return {'kind': 'directory', **DirectoryPage(frame.data).layout()}
            return {'kind': 'data', **SlottedPage(frame.data).layout()}
        finally:
            self.pool.unpin_page(page_id)

    def close(self):
        self.pool.close()


class Catalog:
    """Append-only JSON metadata records stored in slotted catalog.db pages.

    Latest record for each name wins. Catalog pages are read through a buffer pool.
    """
    def __init__(self, db_dir, frames=8):
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.disk = DiskManager(self.db_dir / 'catalog.db')
        self.pool = BufferPool(self.disk, max(1, frames))
        if self.disk.num_pages() == 0:
            frame = self.pool.new_page()
            SlottedPage.initialize(frame.data, frame.page_id)
            self.pool.unpin_page(frame.page_id, True)
            self.pool.flush_all()

    def list_tables(self):
        latest = {}
        for page_id in range(self.disk.num_pages()):
            frame = self.pool.fetch_page(page_id)
            page = SlottedPage(frame.data)
            try:
                for slot in range(page.slot_count):
                    if page.slot(slot)[0]:
                        obj = json.loads(page.get(slot).decode('utf-8'))
                        latest[obj['name']] = obj
            finally:
                self.pool.unpin_page(page_id)
        return latest

    def get_table(self, name):
        info = self.list_tables().get(name)
        if info is None:
            raise StorageError(f'Unknown table: {name}')
        return info

    def _append(self, info):
        record = json.dumps(info, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(record) > 4088:
            raise StorageError('Catalog record too large')
        page_id = self.disk.num_pages() - 1
        frame = self.pool.fetch_page(page_id)
        page = SlottedPage(frame.data)
        if page.free_space < len(record) + 4:
            self.pool.unpin_page(page_id)
            frame = self.pool.new_page()
            page = SlottedPage.initialize(frame.data, frame.page_id)
        page.insert(record)
        self.pool.unpin_page(frame.page_id, True)
        self.pool.flush_all()

    def create_table(self, name, schema):
        if name in self.list_tables():
            raise StorageError(f'Table already exists: {name}')
        if not name or not all(c.isalnum() or c == '_' for c in name):
            raise StorageError('Invalid table name')
        self._append(dict(name=name, schema=schema, file=f'{name}.db',
                          first_page=0, num_pages=1, num_tuples=0))

    def update_table(self, name, **changes):
        record = self.get_table(name)
        record.update(changes)
        self._append(record)

    def close(self):
        self.pool.close()
