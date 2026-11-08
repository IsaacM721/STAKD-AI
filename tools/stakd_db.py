#!/usr/bin/env python3
"""Stakd AI database helper for your own Claude sync. Signs in as YOU (env STAKD_EMAIL + STAKD_PASSWORD,
set as environment secrets, never pasted in chat) and reads/writes only your own space users/{your uid}/...

  stakd_db.py get COLLECTION DOC_ID
  stakd_db.py list COLLECTION
  stakd_db.py set COLLECTION DOC_ID '<json>'      (replace)
  stakd_db.py update COLLECTION DOC_ID '<json>'   (merge top-level fields)
  stakd_db.py delete COLLECTION DOC_ID
Collections: entries (savings ledger), spend (spending), prestamos (loans), config/main, spendMeta/sync ...
Also importable: from stakd_db import get, list_col, set_doc, update_doc, delete_doc
"""
import json, os, sys, urllib.request, urllib.error

API_KEY = "AIzaSyBwQfOJ4jRjmVcqoTAnC01snchuMl1hQm8"
PROJECT = "stakd-isaac"
ROOT = f"projects/{PROJECT}/databases/(default)/documents"
BASE = "https://firestore.googleapis.com/v1/" + ROOT
_tok = None
UID = None

def _post(url, body, tok=None):
    h = {"Content-Type": "application/json"}
    if tok: h["Authorization"] = "Bearer " + tok
    req = urllib.request.Request(url, json.dumps(body).encode(), h)
    return json.load(urllib.request.urlopen(req))

def token():
    global _tok, UID
    if _tok: return _tok
    em, pw = os.environ.get("STAKD_EMAIL"), os.environ.get("STAKD_PASSWORD")
    if not em or not pw: sys.exit("STAKD_EMAIL / STAKD_PASSWORD are not set in this environment")
    try:
        r = _post(f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}", {"email": em, "password": pw, "returnSecureToken": True})
    except urllib.error.HTTPError as e:
        sys.exit("Stakd sign-in failed: " + e.read().decode())
    _tok, UID = r["idToken"], r["localId"]
    return _tok

def _val(v):
    if v is None: return {"nullValue": None}
    if isinstance(v, bool): return {"booleanValue": v}
    if isinstance(v, int) and abs(v) < 2**63: return {"integerValue": str(v)}
    if isinstance(v, (int, float)): return {"doubleValue": float(v)}
    if isinstance(v, str): return {"stringValue": v}
    if isinstance(v, list): return {"arrayValue": {"values": [_val(x) for x in v]}}
    if isinstance(v, dict): return {"mapValue": {"fields": {k: _val(x) for k, x in v.items()}}}
    raise TypeError(type(v))

def _unv(v):
    k, x = next(iter(v.items()))
    if k == "integerValue": return int(x)
    if k == "nullValue": return None
    if k == "arrayValue": return [_unv(i) for i in x.get("values", [])]
    if k == "mapValue": return {a: _unv(b) for a, b in x.get("fields", {}).items()}
    return x

def _doc(d): return {"id": d["name"].rsplit("/", 1)[1], **{a: _unv(b) for a, b in d.get("fields", {}).items()}}

def _req(method, url, body=None):
    h = {"Authorization": "Bearer " + token(), "Content-Type": "application/json"}
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, h, method=method)
    try: return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        raise SystemExit(f"{method} failed {e.code}: {e.read().decode()}")

def _p(col, doc=None):
    token(); return f"{BASE}/users/{UID}/{col}" + (f"/{doc}" if doc else "")

def get(col, doc):
    d = _req("GET", _p(col, doc)); return _doc(d) if d else None

def list_col(col):
    out, page = [], ""
    while True:
        r = _req("GET", _p(col) + f"?pageSize=300{('&pageToken=' + page) if page else ''}") or {}
        out += [_doc(d) for d in r.get("documents", [])]
        page = r.get("nextPageToken")
        if not page: return out

def _commit(writes): return _req("POST", f"{BASE}:commit", {"writes": writes})

def set_doc(col, doc, data):
    token()
    data = {k: v for k, v in data.items() if k != "id"}
    return _commit([{"update": {"name": f"{ROOT}/users/{UID}/{col}/{doc}", "fields": {k: _val(v) for k, v in data.items()}}}])

def update_doc(col, doc, data):
    token()
    data = {k: v for k, v in data.items() if k != "id"}
    dels = [k for k, v in data.items() if isinstance(v, dict) and v.get("__delete__") is True]
    keep = {k: v for k, v in data.items() if k not in dels}
    mask = [f"`{k}`" if not k.replace("_", "").isalnum() else k for k in data]
    return _commit([{"update": {"name": f"{ROOT}/users/{UID}/{col}/{doc}", "fields": {k: _val(v) for k, v in keep.items()}},
                     "updateMask": {"fieldPaths": mask}}])

def delete_doc(col, doc):
    token(); return _commit([{"delete": f"{ROOT}/users/{UID}/{col}/{doc}"}])

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    cmd = a[0]
    if cmd == "get": print(json.dumps(get(a[1], a[2]), ensure_ascii=False, indent=1))
    elif cmd == "list": print(json.dumps(list_col(a[1]), ensure_ascii=False, indent=1))
    elif cmd == "set": set_doc(a[1], a[2], json.loads(a[3])); print("ok")
    elif cmd == "update": update_doc(a[1], a[2], json.loads(a[3])); print("ok")
    elif cmd == "delete": delete_doc(a[1], a[2]); print("ok")
    else: sys.exit(__doc__)
