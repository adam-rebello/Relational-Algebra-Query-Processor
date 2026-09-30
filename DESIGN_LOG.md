# DESIGN_LOG.md

## Session 1 - Grammar and Initial Design

I started by breaking the project into the tokenizer, parser, parse tree, relation model, evaluator, tests, and performance tools. I decided to use a hand-written tokenizer and recursive-descent parser because the assignment specifically does not allow parser generators or regular expressions.

I also worked out the operator precedence before implementing the parser. Union and minus are handled at the lowest relational level, intersect is above them, join and times are above intersect, and unary operators such as select, project, and rename bind the strongest.

One issue I found while discussing the tokenizer with AI was that an early approach treated words such as union as permanently reserved keywords. That would have caused valid cases such as select[union=3](R) to fail when an attribute happens to have the same name as a keyword. I changed the design so the tokenizer produces WORD tokens and the parser decides from context whether a word is acting as an operator or an identifier.

## Session 2 - Tokenizer, Parser, and Parse Tree

I implemented the tokenizer manually with character-by-character scanning. It supports identifiers, numbers, strings, punctuation, comparison operators, comments, and source positions. Multi-character operators such as >=, <=, and != use maximal munch.

I then implemented the recursive-descent parser using a separate function for each precedence level. I used loops for left-associative operators such as union and minus instead of directly translating left-recursive grammar rules.

I added a printable parse tree and checked it using nested queries such as:

project[Name](select[Age>30](Employees))

The grammar tests were also useful for confirming that A minus B minus C groups from the left and that condition precedence follows not, then and, then or.

## Session 3 - Relation Model and Operators

I implemented the Relation, Attribute, and tuple classes and then added the relational operators in the evaluator. Relations use set semantics, so duplicate tuples are not inserted.

One problem caused by an earlier AI-generated version of copy_schema() was that copied attributes lost or changed their original relation qualifiers. This caused qualified attribute lookup to fail later during joins. I found the problem through semantic tests and changed copy_schema() so that it preserves the qualifier stored on each Attribute.

I also decided that projecting the same attribute more than once is treated as a schema error. This behaviour is documented and tested.

## Session 4 - Join and Self-Join Debugging

The join operator was implemented as a nested-loop theta join. For every pair of tuples, the join condition is evaluated and the join comparison counter is increased exactly once.

Another AI-generated join revision initially handled qualified attributes incorrectly. In particular, expressions involving renamed relations and self-joins could not always determine whether an attribute belonged to the left or right operand.

I found this when the required qualified join and self-join semantic tests failed. I rewrote join operand resolution so it searches the left and right schemas separately and checks the stored relation qualifier. After that correction, the full test suite passed with 32 tests.

## Session 5 - Error Handling and Command-Line Interface

I added separate error categories for lexical errors, syntax errors, unknown names, schema problems, and type errors.

The command-line program catches these errors and prints a readable message instead of exposing a Python stack trace.

I tested the tree mode with:

python ra.py --tree "project[Name](select[Age>30](Employees))"

I also tested evaluation using a relation data file and checked normal results, projection, selection, and empty results.

## Session 6 - Performance Testing

I created separate benchmark tools for join, select/project, and match-rate experiments.

The join benchmark used the required sizes from 1,000 up to 64,000 tuples on each side. The nested-loop join showed quadratic growth and the largest measured case, 64,000 by 64,000, performed 4,096,000,000 comparisons and took 8712.435958 seconds.

An early AI suggestion was to run all large benchmark sizes together before checking smaller cases. After seeing how quickly the runtime increased, I changed the process so results were saved incrementally and the largest runs were handled separately. This made it much less likely that completed measurements would be lost if a long run was interrupted.

For selection, I originally benchmarked select[a>=0](R), which caused every tuple to be copied into the output. This made the timing much larger because duplicate checking and result construction were included. I changed the benchmark to select[a<0](R). Every input tuple is still examined, so the selection counter remains correct, but no result tuples are inserted. This gives a cleaner measurement of the selection scan.

The select and project measurements were approximately linear, while the join measurements were approximately quadratic. The log-log slopes were about 1.00 for select, 1.00 for project, and 2.04 for join.

I also varied the join match rate at 4,000 tuples per relation. Every run still performed 16,000,000 comparisons, while runtime increased as the result size increased. This confirmed that the nested-loop algorithm always checks every pair regardless of how many pairs actually match.

## Session 7 - Final Review

I finished the required tests, performance experiments, grammar document, report, README, and design log.

The main AI mistakes or incomplete suggestions that I had to identify and correct during the project were:

1. Treating relational keywords as permanently reserved tokens instead of allowing contextual identifiers.
2. Changing or losing attribute relation qualifiers when copying schemas.
3. Incorrect qualified attribute lookup in joins and self-joins.
4. Suggesting an impractical benchmark workflow before checking the growth rate of the nested-loop implementation.
5. Using a selection benchmark that included large result-construction costs instead of isolating the tuple scan.

These issues were found through required test cases, failed semantic behaviour, and performance measurements rather than accepting generated code without checking it.