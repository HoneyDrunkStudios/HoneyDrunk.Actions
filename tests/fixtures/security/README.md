# CodeQL extension-rule regression fixture

`codeql-extensions.sarif` reproduces the rule layout from the
[NovOutbox scheduled security run](https://github.com/HoneyDrunkStudios/HoneyDrunk.NovOutbox/actions/runs/38838777598)
(CodeQL artifact 12020497205, October 16, 2026).

The driver has no rules; extension 0 has 164 descriptors. All 17 results use
`rule.index` and `rule.toolComponent.index`. The fixture retains original rule
IDs, indices and the referenced rules' severity metadata. Unreferenced rules
retain only their IDs. Source locations, snippets and result messages are
removed or replaced with placeholder text.

Expected counts: 15 low, 1 moderate, 1 high, 0 critical, 0 unknown. The high
finding has security severity 7.5. The existing caller threshold controls high
findings; unknown severity, malformed references and critical findings still
block independently of that threshold.
