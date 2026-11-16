# COMP 3005 Project 2 — Module 1 Design

## Design goal

Store actual records in disk files, with a fixed 4096-byte page size. `storage_engine/core.py` contains disk and page operations; `storage.py` is only the CLI. No part of the storage engine uses a database library.

## Data files and addressing

Each table uses `<name>.db`; metadata uses `catalog.db`. There is **no file header outside the pages**. Page numbers are zero-based **within a file**. The first page of a table is a directory page. A record identifier (RID) is `(data_page_id, slot_number)`; the table identity is provided by the HeapFile instance. All multi-byte integers use **little-endian** byte order.

A `DiskManager` reads/writes exactly 4096 bytes at offset `4096 * page_id`, and counts each explicit read and write. Allocating a page appends 4096 zero bytes; counter increments are reserved for explicit `read_page` / `write_page` operations, so creation itself is not treated as a page-buffer miss.

## Record format

Records consist only of encoded fields, in schema order. There is no record header or NULL bitmap.

| Type | Bytes |
|---|---|
| `INT` | signed, four-byte two's-complement, little-endian |
| `VARCHAR(n)` | two-byte unsigned length L followed by L UTF-8 **bytes**; `L <= n <= 255` |

For schema `a:INT,b:VARCHAR(5),c:INT`, row `(42, 'bob', 7)` is exactly 13 bytes:

```
2a 00 00 00    03 00 62 6f 62    07 00 00 00
    a                b                  c
```

## Slotted data page (exact byte layout)

```
                   4096 bytes
   +----------------------------------------+
 0 | page_id            uint32 (bytes 0..3) |
 4 | slot_count         uint16 (bytes 4..5) |
 6 | free_end           uint16 (bytes 6..7) |
 8 | slot 0: offset,length (two uint16s)    |
12 | slot 1: offset,length                ...|
   |              ...                       |
   |  free space grows/shrinks here         |
   |              ...                       |
   |  record bytes (newest toward the front)|
4096 +----------------------------------------+
```

Free space is `free_end - (8 + 4 * slot_count)`. Each insert needs `record_length + 4` bytes. New records are written backward from the end of the page; slots grow forward. Deletion sets the slot to `(0,0)`. Slot positions never move or get reused, so RIDs remain stable. **We do not implement compaction**: deleted record bytes are not made available for future inserts, exactly as allowed by the spec. The free-space directory retains the *usable contiguous* byte count, not the total bytes left by deleted records.

### Actual on-disk example

Created using `storage create-table` and `storage load` from `examples/m1_example.csv` (schema `a INT, b VARCHAR(20), c INT`). A hex dump of the beginning of **R.db page 1**:

```
page offset 0: 01 00 00 00 04 00 c3 0f
               ^ page id 1  ^ 4 slots ^ free_end 4035
page offset 8: f3 0f 0d 00  e6 0f 0d 00
               slot 0 (4083,13); slot 1 (4070,13)
page offset16: d9 0f 0d 00  c3 0f 16 00
               slot 2 (4057,13); slot 3 (4035,22)
```

For this page: `free_space = 4035 - (8 + 4*4) = 4011`. Record 0 begins at byte 4083, and its 13 bytes encode `(42,'bob',7)` as shown above. `storage layout --page 1` prints these exact offsets.

### Instructor's slot example

| Action | `slot_count` | `free_end` | free bytes |
|---|---:|---:|---:|
| Empty | 0 | 4096 | 4088 |
| Insert 13 bytes | 1 | 4083 | 4071 |
| Insert 20 bytes | 2 | 4063 | 4047 |
| Insert 13 bytes | 3 | 4050 | 4030 |
| Delete slot 1 | 3 | 4050 | 4030 |

These exact values are checked in `tests/test_storage_engine.py`.

## Directory pages and heap free-space strategy

Each table's page 0 is a directory page. Directory pages form a linked list.

| Offset | Size | Field |
|---|---:|---|
| 0 | 4 | directory `page_id` |
| 4 | 4 | `next_directory`, `0xffffffff` if none |
| 8 | 2 | `entry_count` |
| 10 + 6*i | 6 | data `page_id` (uint32), usable `free_bytes` (uint16) |

Capacity is `floor((4096 - 10) / 6) = 681` entries per directory page. `HeapFile.insert()` walks entries in page order using **first fit**. The directory prevents scanning every data page to discover space. A full directory gets a new linked directory page. `get()` fetches its data page using the RID; `delete()` marks the slot dead and leaves the directory free-byte count unchanged, because deletion does not reclaim record space.

`HeapFile.scan()` is a Python generator that walks directory entries and visits only live slots. A scan holds at most **one directory and one data page pinned**, and yields records one at a time. It does not load the entire relation into a list. Early termination closes the generator to release pins. Scans therefore require at least two frames.

## Buffer pool and memory budget

The buffer pool maintains exactly B frame positions, a page-table mapping to frame indices, and one pin count and dirty flag per resident page. An already-resident fetch is a hit, increments pin count, and updates the replacement-policy metadata. A cache miss reads from the disk manager; a frame replacement counts an eviction only when a real resident page is displaced. Evicting a pinned page is forbidden. Dirty frames are written only on replacement or flush. `unpin_page` of an unpinned page is an error.

- **LRU:** use a monotonic access counter, choose the least recently accessed *unpinned* frame (deterministic frame-index tie break).
- **CLOCK:** reference bit set on every fetch; a clock-hand sweep clears reference bits, skips pinned frames, and selects the first unpinned reference-bit-zero frame. Newly loaded pages begin with reference bit 1, and the hand advances.

### Budget scope

Each CLI command uses file-local pools only **sequentially**: catalog lookup and table access do not hold two full pools simultaneously. `.close()` flushes and releases all resident frames before another file pool is opened. The heap scan holds no more than 2 frames pinned at a time. `--frames` sets the table buffer limit, not an allowance to materialize tuples. Trace commands use a synthetic `TraceDisk` that counts reads without requiring physical trace pages.

**Counter definitions:** `hits` = fetches of already-resident pages, `misses` = page reads, `evictions` = misses that replaced a resident page, `reads` = actual disk manager page reads, `writes` = actual page writes. The scan's JSON stats measure the table heap pool. Catalog lookups are separate, and occur before heap scan; this is an explicit choice documented here.

## Catalog page format

`catalog.db` is also a sequence of 4096-byte slotted pages with the same 8-byte header and four-byte slot entries as data pages. Each live slot contains a **UTF-8 JSON metadata record** of a table: `name`, ordered `schema`, file path, `first_page`, `num_pages` and `num_tuples`. New versions are append-only records. Loading the catalog scans all slotted pages and uses the latest entry per table name. This means catalog updates never overwrite earlier bytes. JSON was chosen because the M4 statistics can later be included as additional fields without changing the page format. The catalog itself is fetched through its buffer pool, not read as a sidecar text file.

## Deliberately deferred choices

No compaction; no overflow pages; no transactional rollback of a partially successful CSV load; no concurrent writes; no global shared pool across simultaneously active files. The CLI coordinates catalog and heap access sequentially to maintain the specified B-page bound. These are scope limits, not claims of full SQL engine functionality.

## Reading and design influence

1. Joseph M. Hellerstein, Michael Stonebraker, and James Hamilton, *Architecture of a Database System* (2007): https://dsf.berkeley.edu/papers/fntdb07-architecture.pdf — influenced the separation of persistence, catalog, and query-facing layers. Without this boundary, later execution operators would directly touch files.
2. Andy Pavlo, *CMU 15-445/645 Lecture 06: Buffer Pools* (2024): https://15445.courses.cs.cmu.edu/fall2024/notes/06-bufferpool.pdf — informed the explicit page-table, pin-count, and dirty-frame design. I check for an unpinned victim before any eviction, and account for page reads separately from frame accesses.

The byte offsets, exact replacement trace, and counter conventions follow the supplied **COMP 3005 Module 1 specification** where its requirements are more precise than general references.
