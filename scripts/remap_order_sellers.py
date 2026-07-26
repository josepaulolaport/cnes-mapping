#!/usr/bin/env python3
"""
Remap orders.seller_id from legacy ERP avulsa.Id_Vendedor → REP users.

Original ETL (data_etl/etl/06_orders.py) hardcoded seller_id = rep@atlasmed.com.br.
Source CSV has Id_Vendedor; we resolve it via:
  1) high-confidence atlasmed-2 consultant among clients with that Id_Vendedor
  2) dominant ERP Usuario on those orders (when maps to a user)
  3) create missing REP users from ERP Usuario for remaining vendedor ids
  4) per-order fallback: a2 facility consultant

Usage:
  python scripts/remap_order_sellers.py --db-url postgresql://.../atlasmed-3 --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path

import psycopg2
from argon2 import PasswordHasher

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AVULSA = Path("/Users/josepaulolaport/Documents/projects/data_etl/csv/avulsa.csv")
DEFAULT_CLIENTES = Path("/Users/josepaulolaport/Documents/projects/data_etl/csv/clientes.csv")
DEFAULT_CF_MAP = Path(
    "/Users/josepaulolaport/Documents/projects/data_etl/etl/output/client_facility_map.json"
)
DEFAULT_A2 = "postgresql://postgres:592jphlap@localhost:5432/atlasmed-2"
NOTE = "seller-remap-from-id-vendedor-20260726"
OPS = {
    "DIRETORIA",
    "THAISA.GONCALVES",
    "ANA.FIGUEIREDO",
    "MICHELL.DOMINGOS",
    "CAREN.LUIZ",
    "GABRIELY.FERNANDES",
    "MEDICA.RS",
    "MEDICA.SC",
    "VEGA",
}
ALIASES = {
    "mariana.gadioli": "mariana.costa",
    "marcio.paula": "marcio.(reumato)",
    "raquel.carvalho": "raquel",
    "jefferson.santos": "jefferson.spi",
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db-url", required=True)
    p.add_argument("--a2-url", default=DEFAULT_A2)
    p.add_argument("--avulsa", type=Path, default=DEFAULT_AVULSA)
    p.add_argument("--clientes", type=Path, default=DEFAULT_CLIENTES)
    p.add_argument("--client-facility-map", type=Path, default=DEFAULT_CF_MAP)
    p.add_argument("--password", default="Atlasmed@2026")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    c = psycopg2.connect(args.db_url)
    cur = c.cursor()
    c2 = psycopg2.connect(args.a2_url)
    s = c2.cursor()

    cur.execute("select id from roles where name='REP'")
    rep_role = cur.fetchone()[0]
    cur.execute("select id from users where email='rep@atlasmed.com.br'")
    fallback = cur.fetchone()[0]

    cur.execute(
        "select id, lower(username), lower(split_part(email,'@',1)), first_name, last_name "
        "from users where deleted_at is null"
    )
    by_uname: dict[str, str] = {}
    by_id: dict[str, dict] = {}
    for uid, uname, local, fn, ln in cur.fetchall():
        by_id[uid] = {"username": uname, "email_local": local, "fn": fn, "ln": ln}
        for k in {uname, uname.replace(".", "_"), uname.replace("_", "."), local}:
            by_uname[k] = uid

    def resolve_username(raw: str | None) -> str | None:
        if not raw:
            return None
        key = raw.strip().lower().replace("_", ".")
        key = ALIASES.get(key, key)
        return by_uname.get(key) or by_uname.get(key.replace(".", "_"))

    def ensure_user(display_usuario: str) -> str:
        uname = display_usuario.strip().lower().replace("_", ".")
        existing = resolve_username(uname)
        if existing:
            return existing
        parts = [p for p in re.split(r"[.\s_]+", uname) if p]
        first = parts[0].title() if parts else "Rep"
        last = " ".join(p.title() for p in parts[1:]) if len(parts) > 1 else "Rep"
        email = f"{uname}@atlasmed.internal"
        cur.execute(
            "select id from users where lower(email)=%s or lower(username)=%s",
            (email, uname),
        )
        hit = cur.fetchone()
        if hit:
            by_uname[uname] = hit[0]
            return hit[0]
        if not args.apply:
            fake = f"dryrun:{uname}"
            by_uname[uname] = fake
            by_id[fake] = {"username": uname, "email_local": uname, "fn": first, "ln": last}
            return fake
        uid = uuid.uuid4().hex
        cur.execute(
            """
            insert into users (
              id, email, username, password_hash, first_name, last_name,
              status, email_verified, role_id, metadata
            ) values (%s,%s,%s,%s,%s,%s,'ACTIVE',true,%s,%s::jsonb)
            """,
            (
                uid,
                email,
                uname,
                PasswordHasher().hash(args.password),
                first,
                last,
                rep_role,
                json.dumps({"source": NOTE, "erpUsuario": display_usuario}),
            ),
        )
        by_uname[uname] = uid
        by_id[uid] = {"username": uname, "email_local": uname, "fn": first, "ln": last}
        print(f"  created {email}")
        return uid

    cur.execute("select id, legacy_id::text, facility_id from orders")
    orders = {leg: (oid, fid) for oid, leg, fid in cur.fetchall()}

    order_meta = {}
    vend_usuario: dict[str, Counter] = defaultdict(Counter)
    vend_n: Counter = Counter()
    with open(args.avulsa, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            aid = row["id"].strip()
            if aid not in orders:
                continue
            order_meta[aid] = row
            vid = (row.get("Id_Vendedor") or "").strip()
            usr = (row.get("Usuario") or "").strip().upper()
            vend_n[vid] += 1
            if usr:
                vend_usuario[vid][usr] += 1

    with open(args.client_facility_map) as f:
        cf = json.load(f)
    client_vend = {}
    with open(args.clientes, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            client_vend[row["Id"].strip()] = (row.get("Id_Vendedor") or "").strip()
    s.execute(
        """
        select distinct on (facility_id) facility_id, user_id
        from facility_consultant_assignments
        where ended_at is null
        order by facility_id, started_at desc nulls last
        """
    )
    a2_cons = dict(s.fetchall())
    vend_a2: dict[str, Counter] = defaultdict(Counter)
    for cid, fid in cf.items():
        vid = client_vend.get(cid)
        if vid and fid in a2_cons:
            vend_a2[vid][a2_cons[fid]] += 1

    vend_map: dict[str, tuple[str | None, str]] = {}
    for vid, total in vend_n.items():
        a2_uid, a2_conf = None, 0.0
        if vend_a2.get(vid):
            a2_uid, a2c = vend_a2[vid].most_common(1)[0]
            a2_conf = a2c / sum(vend_a2[vid].values())
        best_uid, best_c = None, 0
        for usr, cnt in vend_usuario[vid].most_common():
            uid = resolve_username(usr)
            if uid and cnt > best_c:
                best_uid, best_c = uid, cnt
        u_conf = best_c / total if total else 0
        if a2_uid and a2_conf >= 0.70:
            vend_map[vid] = (a2_uid, f"a2:{a2_conf:.2f}")
        elif best_uid and u_conf >= 0.50:
            vend_map[vid] = (best_uid, f"usuario:{u_conf:.2f}")
        elif a2_uid and a2_conf >= 0.50:
            vend_map[vid] = (a2_uid, f"a2:{a2_conf:.2f}")
        elif best_uid:
            vend_map[vid] = (best_uid, f"usuario:{u_conf:.2f}")
        elif vend_usuario[vid]:
            created = None
            for usr, _ in vend_usuario[vid].most_common():
                if usr.upper() in OPS:
                    continue
                created = ensure_user(usr)
                break
            vend_map[vid] = (created, "created") if created else (None, "none")
        else:
            vend_map[vid] = (None, "none")

    stats: Counter = Counter()
    for aid, row in order_meta.items():
        oid, fid = orders[aid]
        vid = (row.get("Id_Vendedor") or "").strip()
        uid, method = vend_map.get(vid, (None, "none"))
        if not uid:
            uid = a2_cons.get(fid)
            method = "a2_facility" if uid else "fallback"
        if not uid:
            uid = fallback
            method = "fallback"
        stats[method.split(":")[0]] += 1
        if args.apply and not str(uid).startswith("dryrun:"):
            cur.execute(
                "update orders set seller_id=%s, updated_at=now() where id=%s",
                (uid, oid),
            )

    if args.apply:
        c.commit()
    else:
        c.rollback()

    out = {
        "note": NOTE,
        "apply": args.apply,
        "vend_map": {
            vid: {
                "user_id": uid,
                "method": m,
                "orders": vend_n[vid],
            }
            for vid, (uid, m) in vend_map.items()
        },
        "stats": dict(stats),
    }
    path = ROOT / "output" / "order_seller_remap.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print("stats", dict(stats))
    print("wrote", path)
    cur.execute(
        "select u.email, count(*) from orders o join users u on u.id=o.seller_id "
        "group by 1 order by 2 desc"
    )
    if args.apply:
        print("sellers:")
        for email, n in cur.fetchall():
            print(f"  {n:4d}  {email}")
    c.close()
    c2.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
