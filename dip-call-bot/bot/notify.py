import requests


def post_discord(url, text, limit=1900):
    """Posts text in chunks split on line breaks. Returns True if every chunk was accepted."""
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    ok = True
    for c in chunks:
        try:
            r = requests.post(url, json={"content": c.rstrip()}, timeout=20)
            ok &= r.status_code < 300
        except Exception:  # noqa: BLE001
            ok = False
    return ok
