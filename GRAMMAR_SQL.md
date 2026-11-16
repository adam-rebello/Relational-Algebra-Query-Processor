# Module 3 — SQL Grammar (EBNF)

The lexer is hand-written in `sql_frontend/compiler.py`. Keywords are case-insensitive; identifiers retain their spelling and are case-sensitive. Identifiers start with a letter or underscore, followed by letters/digits/underscores. Single-quoted strings escape quotes by doubling them. `--` starts a line comment. Integer literals may have a leading sign. `<=`, `>=`, and `<>` are scanned as single operators.

```ebnf
file          = statement, { ";", statement }, [ ";" ] ;
statement     = create | insert | query ;
create        = "CREATE", "TABLE", ident, "(", coldef, { ",", coldef }, ")" ;
coldef        = ident, ( "INT" | "VARCHAR", "(", uint, ")" ) ;
insert        = "INSERT", "INTO", ident, "VALUES", "(", literal, { ",", literal }, ")" ;
query         = select_block, { setop, select_block } ;
setop         = "UNION", [ "ALL" ] | "INTERSECT" | "EXCEPT" ;
select_block  = "SELECT", [ "DISTINCT" ], select_list,
                "FROM", table_ref, { ",", table_ref | "JOIN", table_ref, "ON", condition },
                [ "WHERE", condition ],
                [ "GROUP", "BY", col_list, [ "HAVING", condition ] ],
                [ "ORDER", "BY", sort_list ],
                [ "LIMIT", uint ]
              | "(", query, ")" ;
select_list   = "*" | select_item, { ",", select_item } ;
select_item   = ( column | aggregate ), [ "AS", ident ] ;
aggregate     = ( "COUNT" | "SUM" | "AVG" | "MIN" | "MAX" ), "(", ( column | "*" ), ")" ;
table_ref     = ident, [ [ "AS" ], ident ] | "(", query, ")", "AS", ident ;
col_list      = column, { ",", column } ;
sort_list     = column, [ "ASC" | "DESC" ], { ",", column, [ "ASC" | "DESC" ] } ;
condition     = disjunction ;
disjunction   = conjunction, { "OR", conjunction } ;
conjunction   = negation, { "AND", negation } ;
negation      = [ "NOT" ], ( comparison | "(", condition, ")" ) ;
comparison    = operand, ( "=" | "<>" | "<" | "<=" | ">" | ">=" ), operand ;
operand       = column | literal ;
column        = ident, [ ".", ident ] ;
literal       = signed_integer | quoted_string ;
```

**Precedence:** NOT binds tighter than AND, which binds tighter than OR. Parentheses override. `UNION`, `INTERSECT`, and `EXCEPT` have equal precedence and associate to the left, matching the module document rather than mainstream SQL's varying set-operator precedence.

**Implementation boundaries:** The implementation scans conditions as token sequences for their original placement, resolves their column names and checks comparison types; it does **not** yet construct a complete condition-expression AST enforcing every nested logical edge case. The grammar above describes the target language rather than claiming fully implemented expression parsing. `HAVING` without `GROUP BY` is accepted if the query aggregates, matching the documented grouping semantics; the sketch EBNF shows the simpler grouped form.
