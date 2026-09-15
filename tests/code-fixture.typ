// Permanent export coverage; never included in the manuscript.
#import "../code.typ": code-style
#set page(paper: "a4", margin: 22mm)
#set text(size: 11pt)
#show: code-style

// >>> BODY START
= Code blocks

Language tags enable syntax coloring. Inline `values.max()` stays in the
sentence.

```python
def normalize(values):
    # Keep indentation, quotes, and operators.
    message = "#s('missing') @not-a-citation <fig:missing>"
    return values / values.max()
```

```bash
uv run python analysis/scripts/gen_stats.py
```

```json
{"enabled": true, "threshold": 0.5, "labels": ["control", "treated"]}
```

Long lines wrap visually while the underlying text stays intact.

```python
message = "This deliberately long string tests visual wrapping while preserving every character of the original source text, including its spaces and punctuation."
```

Untagged blocks display literal text.

```
sample    observed    expected
control   1.02        1.00
```

An unknown language also remains readable.

```scaffold-unknown-language
unknown_language(value = "keep me")
```
// <<< BODY END
