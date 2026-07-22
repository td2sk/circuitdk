from __future__ import annotations


def unquote(raw: str) -> str:
    if len(raw) < 2 or not raw.startswith('"') or not raw.endswith('"'):
        raise ValueError("not a quoted string")
    result: list[str] = []
    index = 1
    while index < len(raw) - 1:
        char = raw[index]
        if char == "\\" and index + 1 < len(raw) - 1:
            index += 1
            escaped = raw[index]
            result.append({"n": "\n", "r": "\r", "t": "\t"}.get(escaped, escaped))
        else:
            result.append(char)
        index += 1
    return "".join(result)


def quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
