#!/usr/bin/env python3
"""Descarga los archivos mensuales OCDS de Guatecompras y genera dos tablas compactas:

  compras/data/raw/gc_procesos_auto.tsv.gz        (un proceso por fila)
  compras/data/raw/gc_adjudicaciones_auto.tsv.gz  (una adjudicación-proveedor por fila)

Cubre desde septiembre del año anterior hasta el mes en curso, para no perder
adjudicaciones de concursos publicados a finales del año previo.
Fuente: https://ocds.guatecompras.gt/descarga-datos (Minfin, CC BY 4.0)
"""
import datetime as dt
import gzip
import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import ijson

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
URL = "https://ocds.guatecompras.gt/file/json/{y}/{m}"
UA = {"User-Agent": "FinanzasYDatos-MonitorCompras/1.0 (+https://finanzasydatos.com/compras/)"}

hoy = (dt.datetime.utcnow() - dt.timedelta(hours=6)).date()  # hora de Guatemala
ANIO = int(sys.argv[1]) if len(sys.argv) > 1 else hoy.year
fin = hoy.month if ANIO == hoy.year else 12
MESES = [(ANIO - 1, m) for m in range(9, 13)] + [(ANIO, m) for m in range(1, fin + 1)]

P_COLS = ["ocid", "fecha_publicacion", "comprador_id", "comprador", "tipo_entidad", "nivel", "entidad",
          "unidad_compradora", "modalidad", "categoria", "estado", "num_oferentes", "familias_unspsc", "item1", "titulo"]
A_COLS = ["ocid", "fecha_adjudicacion", "monto", "moneda", "proveedor_id", "proveedor", "estado_adj", "num_proveedores"]


def clean(v):
    if v is None:
        return ""
    return " ".join(str(v).replace("\t", " ").split())


def descargar(y, m, intentos=4):
    for k in range(intentos):
        try:
            req = urllib.request.Request(URL.format(y=y, m=m), headers=UA)
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            print(f"  intento {k+1} falló para {y}-{m}: {e}", flush=True)
            time.sleep(20 * (k + 1))
    raise RuntimeError(f"No se pudo descargar {y}-{m}")


def filas(registro):
    c = registro.get("compiledRelease") or {}
    t = c.get("tender") or {}
    partes = c.get("parties") or []
    def comprador(scheme):
        for p in partes:
            if "buyer" in (p.get("roles") or []) and (p.get("identifier") or {}).get("scheme") == scheme:
                return p
        return {}
    ent, uni = comprador("GT-CISP"), comprador("GT-GCUC")
    det = ent.get("details") or {}
    fams, item1 = [], ""
    for i, it in enumerate(t.get("items") or []):
        f = str((it.get("classification") or {}).get("id") or "")[:4]
        if f and f not in fams:
            fams.append(f)
        if i == 0:
            item1 = (it.get("description") or "")[:90]
    nt = t.get("numberOfTenderers")
    proc = [c.get("ocid"), (t.get("datePublished") or "")[:10], (c.get("buyer") or {}).get("id"),
            (c.get("buyer") or {}).get("name"), (det.get("entityType") or {}).get("description"),
            (det.get("level") or {}).get("description"), ent.get("name"), uni.get("name"),
            t.get("procurementMethodDetails"), t.get("mainProcurementCategory"), t.get("statusDetails"),
            "" if nt is None else nt, "|".join(fams), item1, (t.get("title") or "")[:140]]
    adjs = []
    for a in c.get("awards") or []:
        sup = a.get("suppliers") or [{}]
        val = a.get("value") or {}
        for si, s in enumerate(sup):
            monto = val.get("amount") if si == 0 else 0
            adjs.append([c.get("ocid"), (a.get("date") or "")[:10], "" if monto is None else monto,
                         val.get("currency"), s.get("id"), s.get("name"), a.get("status"), len(sup)])
    return proc, adjs


def main():
    pf = gzip.open(RAW / "gc_procesos_auto.tsv.gz", "wt", encoding="utf-8")
    af = gzip.open(RAW / "gc_adjudicaciones_auto.tsv.gz", "wt", encoding="utf-8")
    pf.write("\t".join(P_COLS) + "\n")
    af.write("\t".join(A_COLS) + "\n")
    vistos = set()
    tp = ta = 0
    for y, m in MESES:
        t0 = time.time()
        datos = descargar(y, m)
        with zipfile.ZipFile(io.BytesIO(datos)) as zf:
            nombre = next(n for n in zf.namelist() if n.lower().endswith(".json"))
            with zf.open(nombre) as fh:
                n = 0
                for rec in ijson.items(fh, "records.item", use_float=True):
                    proc, adjs = filas(rec)
                    if proc[0] in vistos:
                        continue
                    vistos.add(proc[0])
                    pf.write("\t".join(clean(v) for v in proc) + "\n")
                    for r in adjs:
                        af.write("\t".join(clean(v) for v in r) + "\n")
                    n += 1
                    ta += len(adjs)
                tp += n
        print(f"{y}-{m:02d}: {n} procesos ({len(datos)/1e6:.1f} MB, {time.time()-t0:.0f}s)", flush=True)
    pf.close()
    af.close()
    print(f"Listo: {tp} procesos, {ta} adjudicaciones")
    if tp == 0:
        sys.exit("Sin datos: se detiene la actualización")


if __name__ == "__main__":
    main()
