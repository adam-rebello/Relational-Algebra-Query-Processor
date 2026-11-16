# DESIGN_LOG.md

More recent milestones working periods are below intial project submission.
## Session 1 - Grammar and Initial Design Septemeber 22nd, 2026

I started by breaking the project into the tokenizer, parser, parse tree, relation model, evaluator, tests, and performance tools. I decided to use a hand-written tokenizer and recursive-descent parser because the assignment specifically does not allow parser generators or regular expressions.

I also worked out the operator precedence before implementing the parser. Union and minus are handled at the lowest relational level, intersect is above them, join and times are above intersect, and unary operators such as select, project, and rename bind the strongest.

One issue I found while discussing the tokenizer with AI was that an early approach treated words such as union as permanently reserved keywords. That would have caused valid cases such as select[union=3](R) to fail when an attribute happens to have the same name as a keyword. I changed the design so the tokenizer produces WORD tokens and the parser decides from context whether a word is acting as an operator or an identifier.

## Session 2 - Tokenizer, Parser, and Parse Tree Septemebr 23rd, 2026

I implemented the tokenizer manually with character-by-character scanning. It supports identifiers, numbers, strings, punctuation, comparison operators, comments, and source positions. Multi-character operators such as >=, <=, and != use maximal munch.

I then implemented the recursive-descent parser using a separate function for each precedence level. I used loops for left-associative operators such as union and minus instead of directly translating left-recursive grammar rules.

I added a printable parse tree and checked it using nested queries such as:

project[Name](select[Age>30](Employees))

The grammar tests were also useful for confirming that A minus B minus C groups from the left and that condition precedence follows not, then and, then or.

## Session 3 - Relation Model and Operators September 24th, 2026 

I implemented the Relation, Attribute, and tuple classes and then added the relational operators in the evaluator. Relations use set semantics, so duplicate tuples are not inserted.

One problem caused by an earlier AI-generated version of copy_schema() was that copied attributes lost or changed their original relation qualifiers. This caused qualified attribute lookup to fail later during joins. I found the problem through semantic tests and changed copy_schema() so that it preserves the qualifier stored on each Attribute.

I also decided that projecting the same attribute more than once is treated as a schema error. This behaviour is documented and tested.

## Session 4 - Join and Self-Join Debugging September 25th, 2026

The join operator was implemented as a nested-loop theta join. For every pair of tuples, the join condition is evaluated and the join comparison counter is increased exactly once.

Another AI-generated join revision initially handled qualified attributes incorrectly. In particular, expressions involving renamed relations and self-joins could not always determine whether an attribute belonged to the left or right operand.

I found this when the required qualified join and self-join semantic tests failed. I rewrote join operand resolution so it searches the left and right schemas separately and checks the stored relation qualifier. After that correction, the full test suite passed with 32 tests.

## Session 5 - Error Handling and Command-Line Interface Septemeber 26th, 2026

I added separate error categories for lexical errors, syntax errors, unknown names, schema problems, and type errors.

The command-line program catches these errors and prints a readable message instead of exposing a Python stack trace.

I tested the tree mode with:

python ra.py --tree "project[Name](select[Age>30](Employees))"

I also tested evaluation using a relation data file and checked normal results, projection, selection, and empty results.

## Session 6 - Performance Testing September 29th, 2026

I created separate benchmark tools for join, select/project, and match-rate experiments.

The join benchmark used the required sizes from 1,000 up to 64,000 tuples on each side. The nested-loop join showed quadratic growth and the largest measured case, 64,000 by 64,000, performed 4,096,000,000 comparisons and took 8712.435958 seconds.

An early AI suggestion was to run all large benchmark sizes together before checking smaller cases. After seeing how quickly the runtime increased, I changed the process so results were saved incrementally and the largest runs were handled separately. This made it much less likely that completed measurements would be lost if a long run was interrupted.

For selection, I originally benchmarked select[a>=0](R), which caused every tuple to be copied into the output. This made the timing much larger because duplicate checking and result construction were included. I changed the benchmark to select[a<0](R). Every input tuple is still examined, so the selection counter remains correct, but no result tuples are inserted. This gives a cleaner measurement of the selection scan.

The select and project measurements were approximately linear, while the join measurements were approximately quadratic. The log-log slopes were about 1.00 for select, 1.00 for project, and 2.04 for join.

I also varied the join match rate at 4,000 tuples per relation. Every run still performed 16,000,000 comparisons, while runtime increased as the result size increased. This confirmed that the nested-loop algorithm always checks every pair regardless of how many pairs actually match.

## Session 7 - Final Review September 30th, 2026 

I finished the required tests, performance experiments, grammar document, report, README, and design log.

The main AI mistakes or incomplete suggestions that I had to identify and correct during the project were:

1. Treating relational keywords as permanently reserved tokens instead of allowing contextual identifiers.
2. Changing or losing attribute relation qualifiers when copying schemas.
3. Incorrect qualified attribute lookup in joins and self-joins.
4. Suggesting an impractical benchmark workflow before checking the growth rate of the nested-loop implementation.
5. Using a selection benchmark that included large result-construction costs instead of isolating the tuple scan.

These issues were found through required test cases, failed semantic behaviour, and performance measurements rather than accepting generated code without checking it.

# COMP 3005 – Bonus Project 2
## Module 1: Storage Engine and Buffer Pool — Design Log

### Entry 1 – Initial Planning and Reviewing Project 1
**Date:** [Nov 2nd, 2026]

I started by going through the requirements for Bonus Project 2 and comparing them with my previous relational algebra processor. Since Project 1 mainly worked with relations stored in memory, I needed to figure out how to build the storage layer without affecting the original code.

I decided to keep the relational algebra components and build the new storage engine separately. This would make it easier to test the new features while keeping the old functionality working.

I also reviewed the module requirements, especially the fixed page size, record formats, and memory restrictions, since these were important for the rest of the implementation.

### Entry 2 – Record Encoding and Slotted Pages
**Date:** [Nov 3rd, 2026]

I worked on storing records using the formats provided in the assignment. Each page is 4096 bytes, with integers stored using 4 bytes and strings stored with a length prefix.

For the page layout, I used a slot directory that grows forward from the page header, while the actual record data is stored backward from the end of the page.

One thing I had to pay attention to was how deletion works. Instead of removing a slot or reusing its number, I marked it as deleted. This keeps existing record IDs valid and follows the required page structure.

I checked the page layout against the worked example to make sure the offsets and free-space values matched.

### Entry 3 – Heap File and Catalog Implementation
**Date:** [Nov 4th, 2026]

After working on the page structure, I moved on to the heap file and catalog.

The heap file uses directory pages to keep track of the available space in each data page. This allows the program to find somewhere to insert a record without searching through every data page.

I also worked on the catalog, which stores information about the tables, including their names, schemas, and number of records.

I kept the storage components separate so the rest of the database system could eventually use them.

### Entry 4 – Buffer Pool and Replacement Policies
**Date:** [Nov 5th, 2026]

The next part was implementing the buffer pool with a fixed number of frames.

I added pin counts to track which pages are currently being used and dirty flags to identify pages that need to be written back to disk.

I implemented both LRU and CLOCK replacement policies. LRU removes the least recently used unpinned page, while CLOCK uses reference bits and a rotating pointer to select a page for replacement.

I tested both policies using the assignment's example trace:

`1 2 3 1 4 2`

With three frames, the results matched the expected values:

- LRU: 1 hit, 5 misses, 2 evictions.
- CLOCK: 2 hits, 4 misses, 1 eviction.

This helped confirm that the replacement logic was following the specification.

### Entry 5 – Command-Line Interface and Debugging
**Date:** [Nov 6th, 2026]

Once the main storage components were implemented, I worked on making them accessible through the command-line interface.

The required commands included creating tables, loading CSV files, scanning records, displaying page layouts, and running buffer replacement traces.

While reviewing the implementation, I noticed that some earlier AI-assisted suggestions focused on the storage classes without covering every required command-line operation.

I corrected this by adding the missing command functionality and testing the commands individually.

Another issue I reviewed was memory usage. Using separate buffer pools for catalog and table operations could potentially exceed the frame limit. I adjusted the command flow so catalog resources were released before opening the heap-file buffer pool.

These changes helped keep the implementation consistent with the module requirements.

### Entry 6 – Relational Algebra Compatibility
**Date:** [Nov 6th, 2026]

I also reviewed how the original relational algebra processor would connect with the new database system.

One difference was duplicate handling. Bonus Project 1 used set semantics, where duplicate tuples were removed, but SQL generally uses bag semantics.

I added support for preserving duplicate tuples while keeping the original set-based behaviour available for compatibility.

This was important for the later modules, especially the execution engine and SQL front end.

### Entry 7 – Testing and Verification
**Date:** [Nov 7th, 2026]

After completing the main implementation, I ran the original Bonus Project 1 tests along with the new storage engine tests.

The combined suite passed 51 tests, including the original 32 tests.

I also checked the important requirements from the Module 1 specification, including the slotted-page example, buffer replacement counters, record operations, and command-line functionality.

The goal was to make sure the implementation followed the exact required behaviour rather than simply returning the expected data.

### Entry 8 – Measurements, Documentation, and Final Review
**Date:** [Nov 7th, 2026]

For the final part of Module 1, I organized the design documentation and measurement results.

The design document explains the page layout, record encoding, heap file structure, catalog, and buffer pool implementation.

The measurement report includes page-capacity calculations, buffer replacement results, and scan measurements.

The official Brightspace trace files were not used for the replacement-policy measurements, so I identified those results as synthetic workloads rather than presenting them as the official traces.

Looking back, the main challenge was making sure the low-level details were correct. Small differences in page offsets, replacement order, or counter calculations could affect the grading results.

This module also provided a foundation for the next stage of the project, where the execution engine will need to read tuples through the buffer pool instead of relying on relations stored entirely in memory.
