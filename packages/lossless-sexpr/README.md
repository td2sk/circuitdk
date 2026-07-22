# circuitdk-lossless-sexpr

`circuitdk-lossless-sexpr` provides a small, lossless concrete syntax tree for S-expressions.
Parsing and rendering an unchanged document preserves its source text byte for byte, including
whitespace, comments, number formatting, and unknown syntax.

The distribution is maintained as part of CircuitDK, but the Python package can be used
independently.

## Installation

```console
uv add circuitdk-lossless-sexpr
```

## Usage

```python
from lossless_sexpr import TextEdit, apply_edits, parse

source = '(property "Value" "10 k" (at 1 2))'
document = parse(source)

value = document.lists("property")[0].atom(2)
assert value is not None

updated = apply_edits(source, [TextEdit(value.span, '"47 k"')])
assert updated == '(property "Value" "47 k" (at 1 2))'
```

Overlapping edits are rejected, and parse errors include source locations. The library deliberately
contains no KiCad or circuit-specific semantics.
