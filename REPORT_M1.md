# COMP 3005 Project 2 — Module 1 Report

## How the measurements were obtained

Run `PYTHONPATH=. python tools/measure_m1.py` from the repository root. This writes `measurements_m1/capacity.csv`, `policies_SYNTHETIC.csv`, and `scan_cost.csv`. Page experiments use the actual storage engine. Replacement experiments use `BufferPool(TraceDisk(), B, policy)` and an explicit known page-reference sequence. Tests cover the instructor's page example and **exact** worked buffer trace separately.

**Important dataset limitation:** Only the Module 1 PDF was supplied, not the five instructor-published trace input files. The 40 policy measurements below are generated **synthetic traces**, NOT the five official trace measurements. The specified sequential 80-page scan is reproduced exactly from the PDF description. Replace the synthetic inputs with the Brightspace trace files as soon as they are available; the engine's `storage trace` command accepts the official files directly.

## 1. Records per page

All samples are ASCII and use exactly the field lengths listed. The formula from the assignment is `floor(4088 / (L + 4))`, with `L` the encoded record length and 4 bytes for its slot entry.

| Schema | Record length L | Computed | Measured on first data page |
|---|---:|---:|---:|
| `a:INT,b:INT,c:INT,d:INT` | 16 | 204 | 204 |
| `a:INT,b:VARCHAR(10),c:INT` with `'bob'` | 13 | 240 | 240 |
| `a:INT,b:VARCHAR(200),c:INT` with 180 `x` characters | 190 | 21 | 21 |

**Difference:** None. Each first page reaches exactly the predicted capacity before the next insert creates a second data page. This is expected because no deletions occur, all records in each experiment have the same encoded length, and the calculation includes the slot directory. For variable-length data of mixed sizes the single-L capacity formula would no longer predict a universal row count.

## 2. Replacement policies

The instructor's **published worked trace** `1,2,3,1,4,2`, B=3, unpinned clean pages, produced:

| Policy | Hits | Misses | Evictions | Page reads | Page writes |
|---|---:|---:|---:|---:|---:|
| LRU | 1 | 5 | 2 | 5 | 0 |
| CLOCK | 2 | 4 | 1 | 4 | 0 |

These are the exact expected results in the M1 PDF and are covered by automatic tests.

### Five controlled replacement workloads (synthetic stand-ins)

The rows below correspond to the generated input sequences described in `tools/measure_m1.py`, not to the instructor's five trace files. Hit rate is hits divided by requests.

| Trace | Policy | Frames B | Requests | Hits | Misses | Evictions | Hit rate |
|---|---|---:|---:|---:|---:|---:|---:|
| synthetic_1_worked | LRU | 4 | 6 | 2 | 4 | 0 | 33.3% |
| synthetic_1_worked | LRU | 16 | 6 | 2 | 4 | 0 | 33.3% |
| synthetic_1_worked | LRU | 64 | 6 | 2 | 4 | 0 | 33.3% |
| synthetic_1_worked | LRU | 256 | 6 | 2 | 4 | 0 | 33.3% |
| synthetic_1_worked | CLOCK | 4 | 6 | 2 | 4 | 0 | 33.3% |
| synthetic_1_worked | CLOCK | 16 | 6 | 2 | 4 | 0 | 33.3% |
| synthetic_1_worked | CLOCK | 64 | 6 | 2 | 4 | 0 | 33.3% |
| synthetic_1_worked | CLOCK | 256 | 6 | 2 | 4 | 0 | 33.3% |
| synthetic_2_hotset | LRU | 4 | 1200 | 0 | 1200 | 1196 | 0.0% |
| synthetic_2_hotset | LRU | 16 | 1200 | 1188 | 12 | 0 | 99.0% |
| synthetic_2_hotset | LRU | 64 | 1200 | 1188 | 12 | 0 | 99.0% |
| synthetic_2_hotset | LRU | 256 | 1200 | 1188 | 12 | 0 | 99.0% |
| synthetic_2_hotset | CLOCK | 4 | 1200 | 0 | 1200 | 1196 | 0.0% |
| synthetic_2_hotset | CLOCK | 16 | 1200 | 1188 | 12 | 0 | 99.0% |
| synthetic_2_hotset | CLOCK | 64 | 1200 | 1188 | 12 | 0 | 99.0% |
| synthetic_2_hotset | CLOCK | 256 | 1200 | 1188 | 12 | 0 | 99.0% |
| synthetic_3_seq80x10 | LRU | 4 | 800 | 0 | 800 | 796 | 0.0% |
| synthetic_3_seq80x10 | LRU | 16 | 800 | 0 | 800 | 784 | 0.0% |
| synthetic_3_seq80x10 | LRU | 64 | 800 | 0 | 800 | 736 | 0.0% |
| synthetic_3_seq80x10 | LRU | 256 | 800 | 720 | 80 | 0 | 90.0% |
| synthetic_3_seq80x10 | CLOCK | 4 | 800 | 0 | 800 | 796 | 0.0% |
| synthetic_3_seq80x10 | CLOCK | 16 | 800 | 0 | 800 | 784 | 0.0% |
| synthetic_3_seq80x10 | CLOCK | 64 | 800 | 0 | 800 | 736 | 0.0% |
| synthetic_3_seq80x10 | CLOCK | 256 | 800 | 720 | 80 | 0 | 90.0% |
| synthetic_4_skew | LRU | 4 | 1000 | 802 | 198 | 194 | 80.2% |
| synthetic_4_skew | LRU | 16 | 1000 | 802 | 198 | 182 | 80.2% |
| synthetic_4_skew | LRU | 64 | 1000 | 802 | 198 | 134 | 80.2% |
| synthetic_4_skew | LRU | 256 | 1000 | 920 | 80 | 0 | 92.0% |
| synthetic_4_skew | CLOCK | 4 | 1000 | 801 | 199 | 195 | 80.1% |
| synthetic_4_skew | CLOCK | 16 | 1000 | 801 | 199 | 183 | 80.1% |
| synthetic_4_skew | CLOCK | 64 | 1000 | 801 | 199 | 135 | 80.1% |
| synthetic_4_skew | CLOCK | 256 | 1000 | 920 | 80 | 0 | 92.0% |
| synthetic_5_mixed | LRU | 4 | 2000 | 21 | 1979 | 1975 | 1.1% |
| synthetic_5_mixed | LRU | 16 | 2000 | 80 | 1920 | 1904 | 4.0% |
| synthetic_5_mixed | LRU | 64 | 2000 | 1369 | 631 | 567 | 68.5% |
| synthetic_5_mixed | LRU | 256 | 2000 | 1819 | 181 | 0 | 91.0% |
| synthetic_5_mixed | CLOCK | 4 | 2000 | 21 | 1979 | 1975 | 1.1% |
| synthetic_5_mixed | CLOCK | 16 | 2000 | 63 | 1937 | 1921 | 3.1% |
| synthetic_5_mixed | CLOCK | 64 | 2000 | 1357 | 643 | 579 | 67.8% |
| synthetic_5_mixed | CLOCK | 256 | 2000 | 1819 | 181 | 0 | 91.0% |

**Sequential-flooding example:** At B=64, scanning 80 distinct pages ten times (`0..79` repeated ten times) gives LRU **0 hits / 800 requests**. The final 64 pages of one pass replace the initial 64 pages, so the next pass begins with misses and evicts the previous pass's remaining pages before reusing them. CLOCK also has zero hits for this input. The exact input sequence is generated in code, so this result is reproducible. In a general-purpose system I would ship **CLOCK** for its inexpensive reference-bit bookkeeping and comparable broad behavior, while recognizing it cannot eliminate sequential flooding. Neither policy is universally better.

## 3. Sequential scan I/O

A test heap was constructed with a directory page (page 0) and **500 physical data pages**, each with a live tuple. Every run used a fresh buffer pool to avoid warm-cache effects. Results:

| Buffer B | Tuples scanned | Total file pages | Page reads | Page writes |
|---|---:|---:|---:|---:|
| 2 | 500 | 501 | 501 | 0 |
| 8 | 500 | 501 | 501 | 0 |
| 64 | 500 | 501 | 501 | 0 |

The result is stable across B: 500 data pages plus one directory page are read once each. There is no reduction from a larger buffer because this is a **cold single-pass sequential scan** with no revisited pages. There are no writes because the scan only reads records. This is consistent with the required expectation of approximately 500 reads.

## Limitations and next verification

- Run the **actual five trace files** supplied on Brightspace; current report's generated trace table cannot substitute for those measurements.
- Verify official hidden traces against the exact counter rules; two hidden inputs are unknown.
- The M1 standalone interface is working, but later modules (executor, parser, optimizer) are not implemented by this checkpoint.

## Reading and impact on the design

- Hellerstein, Stonebraker & Hamilton, *Architecture of a Database System* (2007), https://dsf.berkeley.edu/papers/fntdb07-architecture.pdf: supports layering the disk manager behind the buffer and heap APIs. The measurements deliberately use the same heap implementation as the CLI rather than reading files directly during scans.
- Pavlo, *CMU 15-445 Lecture 06: Buffer Pools* (2024), https://15445.courses.cs.cmu.edu/fall2024/notes/06-bufferpool.pdf: highlights the difference between page residency and page I/O and the role of pin counts. This motivated separate hit/miss/eviction/read/write measurements and a test that pinned pages are never evicted.
