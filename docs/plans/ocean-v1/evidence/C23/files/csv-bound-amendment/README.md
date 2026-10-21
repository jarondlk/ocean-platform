# CSV allocation-bound amendment

Independent review found that the original quoted-field grammar check did not
bound separators, field sizes or row totals before `csv.reader` allocated a
record. Post-parser shape checks rejected overwide CSV, but too late to prevent
that allocation. The original local95-case and coverage evidence remains
immutable and is not relabelled as final-source acceptance.

The revised prepass bounds each decoded field to16,384 UTF-8 bytes, each record
to128 fields, data rows to100,000 and data cells to1,000,000 before invoking
`csv.reader`. It rejects malformed quote/record structure first. Doubled quotes
count as one decoded byte, quoted LF/CRLF remain field bytes, and a trailing
record separator creates no spurious empty row. The parser's existing later
shape/cell checks remain as a second boundary and must agree with the prepass.

Targeted tests guard `csv.reader` so it cannot be reached for delimiter bombs,
oversized unquoted/quoted fields, excessive rows or excessive cells. Positive
cases check exact-bound doubled quotes, multibyte Unicode, quoted CRLF and
multiline quoted records. The new source/test pins, actual targeted commands,
logs and source-before/after snapshots are in `verification.json`.

This changes only the file validator and its test file. No format is broadened:
PNG remains the explicit strict subset that rejects ancillary chunks and may
reject default plotting-library PNG metadata. No Python analysis, runtime,
container, VM, cloud service or scientific result is executed or approved.
Root's combined source-pinned local run must bind all final component sources.
