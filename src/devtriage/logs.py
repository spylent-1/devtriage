import re


def parse_log(text: str) -> dict:
    exceptions, frames = [], []
    for number, line in enumerate(text.splitlines(), 1):
        exc = re.search(r"(?:Caused by:\s*)?([\w.$]+(?:Exception|Error))(?::\s*(.*))?", line)
        if exc:
            exceptions.append({"type": exc[1], "message": exc[2] or "", "line": number})
        frame = re.search(r"\bat\s+([\w.$]+)\(([^():]+):(\d+)\)", line)
        if frame:
            frames.append({"symbol": frame[1], "file": frame[2], "line": int(frame[3]), "log_line": number})
    return {"exceptions": exceptions, "frames": frames,
            "timestamps": re.findall(r"\d{4}-\d\d-\d\d[T ][\d:.+Z-]+", text)[:10],
            "correlation_ids": re.findall(r"(?:traceId|requestId|correlationId)[=: ]+([\w-]+)", text)[:20],
            "truncated": bool(exceptions and not frames)}
