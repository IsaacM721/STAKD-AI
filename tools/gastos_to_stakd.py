#!/usr/bin/env python3
"""Send the transactions from the "gastos" skill into Stakd AI's Spend tab.

  gastos_to_stakd.py transactions.json [--dry-run]

transactions.json is what the gastos skill builds (scripts/build_dataset.py) from the Banreservas and
BHD alert emails. Each row becomes one doc in users/{uid}/spend with doc id = the Gmail message id.

- Only adds transactions Stakd doesn't have yet, so edits you make in the app (category, "Remove")
  are never overwritten.
- A BHD reversal marks the purchase it cancels as "Reversada" (so it stops counting), like the
  gastos dashboard subtracts it.
- Banreservas Uber charges that look like holds are flagged as "Possible double".
- Signs in with STAKD_EMAIL / STAKD_PASSWORD through stakd_db.py (same folder). --dry-run prints the
  docs it would write and needs no sign-in.
"""
import json, os, sys, time
from datetime import datetime, timedelta, timezone

USD_RATE = 60          # same rate the app uses (SP_USD_RATE)
EUR_RATE = 73
DR = timezone(timedelta(hours=-4))  # gastos dates are Dominican Republic local time

# gastos category -> Stakd category key (see SP_CATS in index.html)
CATS = {
    "Comida": "food", "Supermercado": "groceries", "Delivery": "delivery",
    "Transporte": "rides", "Combustible": "gas", "Carro": "gas",
    "Suscripciones / Software": "subs", "Salud": "health", "Compras": "shopping",
    "Educación": "needs", "Impuestos y cargos": "fees", "Efectivo (cajero)": "cash",
    "Transferencias": "other", "Otros": "other",
}


def title(s):
    """"UBER EATS" -> "Uber Eats"; text that already has mixed case stays as it is."""
    return " ".join(w.capitalize() for w in s.split()) if s.isupper() else s


def ts_ms(fecha):
    return int(datetime.strptime(fecha, "%Y-%m-%d %H:%M").replace(tzinfo=DR).timestamp() * 1000)


def to_rd(amount, cur):
    return round(amount * (USD_RATE if cur == "USD" else EUR_RATE if cur == "EUR" else 1), 2)


def to_doc(r):
    mov, cat_es, desc = r["movimiento"], r.get("categoria", "Otros"), r.get("descripcion", "")
    doc = {
        "date": r["fecha"][:10], "merchant": title(desc) or r.get("tipo", ""), "raw": desc,
        "amount": r["monto"], "currency": r["moneda"], "rd": to_rd(r["monto"], r["moneda"]),
        "kind": "consumo", "status": "Aprobada", "cat": CATS.get(cat_es, "other"),
        "source": "gastos", "bank": r.get("banco", ""), "excluded": False, "ts": ts_ms(r["fecha"]),
    }
    if cat_es == "Efectivo (cajero)":
        doc.update(kind="retiro", cat="cash")
    elif cat_es == "Transferencias" and mov == "gasto":
        doc["kind"] = "transfer"
    if mov == "rechazada":
        doc["status"] = "Declinada"
    elif mov == "ingreso":
        doc.update(kind="ingreso", cat="other")
    elif mov == "interno":
        if cat_es == "Movimiento interno":      # e.g. paying your own card: not spending
            doc.update(kind="transfer", own=True, cat="other")
        else:                                   # paid by someone else (_no_es_gasto)
            doc.update(excluded=True, cat="family", note=cat_es)
    if r.get("posible_retencion"):
        doc["dupe"] = True
    return doc


def reversals(rows):
    """{purchase id: reversal row} for BHD reversals, matched the way gastos does it."""
    out = {}
    for rv in (r for r in rows if r["movimiento"] == "reverso"):
        t = datetime.strptime(rv["fecha"], "%Y-%m-%d %H:%M")
        want = rv["descripcion"].removeprefix("Reverso · ")
        for p in reversed(rows):
            if (p["movimiento"] == "gasto" and p["id"] not in out and p["banco"] == rv["banco"]
                    and p["cuenta"] == rv["cuenta"] and p["monto"] == rv["monto"] and p["descripcion"] == want
                    and 0 <= (t - datetime.strptime(p["fecha"], "%Y-%m-%d %H:%M")).total_seconds() <= 7200):
                out[p["id"]] = rv
                break
    return out


def plan(rows, existing):
    """(new docs {id: doc}, status updates {id: fields}) given existing spend docs {id: doc}."""
    rev = reversals(rows)
    used_rev = {rv["id"] for rv in rev.values()}
    new, upd = {}, {}
    for r in rows:
        if r["movimiento"] == "reverso" and r["id"] in used_rev:
            continue                                  # shown on the purchase it cancels
        doc = to_doc(r)
        if r["movimiento"] == "reverso":              # reversal with no purchase found: show it, don't count it
            doc.update(status="Reversada", merchant=title(r["descripcion"].removeprefix("Reverso · ")) or "Reverso")
        if r["id"] in rev:
            doc["status"] = "Reversada"
        if r["id"] not in existing:
            new[r["id"]] = doc
        elif r["id"] in rev and existing[r["id"]].get("status") == "Aprobada":
            upd[r["id"]] = {"status": "Reversada"}
    return new, upd


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(a) != 1:
        sys.exit(__doc__)
    rows = json.load(open(a[0], encoding="utf-8"))
    if dry:
        new, upd = plan(rows, {})
        print(json.dumps(new, ensure_ascii=False, indent=1))
        print(f"dry run: {len(new)} docs would be written")
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stakd_db as db
    db.token()
    existing = {d["id"]: d for d in db.list_col("spend")}
    new, upd = plan(rows, existing)
    writes = [{"update": {"name": f"{db.ROOT}/users/{db.UID}/spend/{i}", "fields": {k: db._val(v) for k, v in d.items()}}}
              for i, d in new.items()]
    writes += [{"update": {"name": f"{db.ROOT}/users/{db.UID}/spend/{i}", "fields": {k: db._val(v) for k, v in f.items()}},
                "updateMask": {"fieldPaths": list(f)}} for i, f in upd.items()]
    for i in range(0, len(writes), 400):              # Firestore allows 500 writes per commit
        db._commit(writes[i:i + 400])
    now = int(time.time() * 1000)
    db.update_doc("spendMeta", "sync", {"lastSync": datetime.now(DR).strftime("%Y-%m-%d"), "lastRunAt": now})
    print(f"{len(new)} added, {len(upd)} marked reversed, {len(existing)} were already in Stakd")


if __name__ == "__main__":
    main()
