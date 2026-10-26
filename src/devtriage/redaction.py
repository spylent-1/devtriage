import re


def redact(text: str) -> str:
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", text)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:password|passwd|secret|api[_-]?key|access[_-]?token|token)\s*[\"']?\s*[:=]\s*[\"']?)[^\s\"',;}]+", r"\1[REDACTED]", text)
    return re.sub(r"(://[^\s:/]+:)[^\s@]+@", r"\1[REDACTED]@", text)


def redact_data(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_data(x) for x in value]
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.fullmatch(r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|authorization)", k)
                else redact_data(v) for k, v in value.items()}
    return value
