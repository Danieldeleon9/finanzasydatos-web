#!/usr/bin/env python3
"""Monitor de compras públicas GT — Finanzas&Datos
Procesa los extractos OCDS de Guatecompras (procesos + adjudicaciones)
y genera data/procesado/monitor_data.json para la web y el carrusel.

Uso: python3 compras/scripts/procesar.py [AÑO]  (por defecto, el año en curso en Guatemala)
Fuente: https://ocds.guatecompras.gt/descarga-datos (CC BY 4.0)
"""
import json, sys, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"
OUT.mkdir(parents=True, exist_ok=True)
import datetime as _dt
YEAR = sys.argv[1] if len(sys.argv) > 1 else str((_dt.datetime.utcnow() - _dt.timedelta(hours=6)).year)

# ---------- Nombres de familias UNSPSC (curados, español) ----------
FAM = {
 "7214":"Construcción pesada (carreteras y puentes)","8110":"Servicios de ingeniería",
 "8310":"Servicios públicos (energía, agua)","5114":"Medicamentos del sistema nervioso",
 "8512":"Servicios médicos especializados","4111":"Reactivos e instrumentos de laboratorio",
 "3011":"Concreto y cemento","8010":"Asesoría y consultoría","3012":"Materiales viales",
 "7810":"Transporte y mensajería","5019":"Alimentos preparados","2510":"Vehículos",
 "7315":"Mantenimiento e impresión industrial","5111":"Medicamentos oncológicos",
 "5112":"Medicamentos cardiovasculares","1510":"Combustibles","5110":"Medicamentos antiinfecciosos",
 "5113":"Medicamentos hematológicos","5118":"Hormonas e insulinas","4323":"Software y licencias",
 "4321":"Computadoras","7210":"Mantenimiento de edificios","2210":"Maquinaria pesada",
 "8016":"Logística y eventos","3017":"Puertas y ventanas","5020":"Agua y bebidas",
 "4229":"Instrumental quirúrgico","4216":"Insumos de diálisis","8612":"Obras y servicios educativos",
 "5120":"Inmunoglobulinas y vacunas","5119":"Sueros, electrolitos y nutrición","8413":"Seguros",
 "8510":"Servicios de diagnóstico","1235":"Biológicos y compuestos químicos",
 "8013":"Arrendamiento de inmuebles","6010":"Material didáctico","5117":"Otros medicamentos",
 "4810":"Equipo de cocina institucional","7215":"Construcción especializada",
 "8516":"Arrendamiento y mantenimiento de equipo médico","4222":"Insumos intravenosos",
 "4220":"Imagenología médica","4214":"Insumos de cuidado al paciente","4231":"Curación de heridas",
 "4511":"Equipo audiovisual","4410":"Equipo y licencias de oficina","8212":"Impresión y reproducción",
 "8311":"Telecomunicaciones","5612":"Mobiliario escolar","5610":"Mobiliario","8610":"Capacitación",
 "7611":"Limpieza","7314":"Producción gráfica","6012":"Útiles escolares","9412":"Obras comunitarias",
 "4218":"Equipo de monitoreo médico","4227":"Equipo respiratorio","4219":"Equipo hospitalario",
 "4221":"Insumos médicos varios","4113":"Equipo de laboratorio","4112":"Insumos de laboratorio",
 "4211":"Insumos de emergencia","4213":"Textiles médicos","4232":"Ortopedia","4217":"Equipo de emergencia",
 "4228":"Esterilización","4229":"Instrumental quirúrgico",
}
SEG = {
 "10":"Plantas y animales","11":"Minerales y textiles","12":"Químicos","14":"Papel","15":"Combustibles",
 "20":"Maquinaria de minería","21":"Maquinaria agrícola","22":"Maquinaria de construcción","23":"Maquinaria industrial",
 "24":"Equipo de carga","25":"Vehículos","26":"Generación eléctrica","27":"Herramientas","30":"Materiales de construcción",
 "31":"Componentes de manufactura","32":"Electrónica","39":"Material eléctrico","40":"Climatización y plomería",
 "41":"Laboratorio","42":"Equipo e insumos médicos","43":"Tecnología","44":"Oficina","45":"Audiovisual",
 "46":"Seguridad","47":"Limpieza","48":"Equipo de servicio","49":"Deportes y recreación","50":"Alimentos",
 "51":"Medicamentos","52":"Electrodomésticos","53":"Ropa y calzado","55":"Impresos","56":"Mobiliario",
 "60":"Material educativo","70":"Servicios agrícolas","71":"Minería","72":"Construcción y mantenimiento",
 "73":"Producción industrial","76":"Limpieza industrial","77":"Ambiente","78":"Transporte","80":"Gestión",
 "81":"Ingeniería","82":"Diseño y comunicación","83":"Servicios públicos","84":"Financieros y seguros",
 "85":"Salud (servicios)","86":"Educación (servicios)","90":"Viajes y alimentación","91":"Servicios personales",
 "92":"Defensa","93":"Servicios cívicos","94":"Organizaciones","95":"Terrenos y edificios",
}
def fam_name(f):
    return FAM.get(f) or (SEG.get(str(f)[:2], "Otros") + f" ({f})")

SECTORES = {
 "salud": {"nombre":"Salud","entidades":["MINISTERIO DE SALUD PÚBLICA","INSTITUTO GUATEMALTECO DE SEGURIDAD SOCIAL -IGSS-"]},
 "educacion": {"nombre":"Educación","entidades":["MINISTERIO DE EDUCACIÓN","UNIVERSIDAD DE SAN CARLOS DE GUATEMALA -USAC-"]},
 "justicia": {"nombre":"Justicia","entidades":["ORGANISMO JUDICIAL","MINISTERIO PÚBLICO","INSTITUTO DE LA DEFENSA PÚBLICA PENAL",
               "INSTITUTO NACIONAL DE CIENCIAS FORENSES DE GUATEMALA","CORTE DE CONSTITUCIONALIDAD"]},
}

def short(name, n=48):
    s = re.sub(r"\s+", " ", str(name)).strip()
    s = re.sub(r",?\s*SOCIEDAD AN[OÓ]NIMA\.?$", ", S.A.", s, flags=re.I)
    return s if len(s) <= n else s[:n-1] + "…"

def persona(name):
    """Persona individual: Guatecompras usa 'APELLIDO,APELLIDO,,NOMBRE,NOMBRE'."""
    return ",," in str(name)

# ---------- Carga ----------
p = pd.read_csv(next(RAW.glob("gc_procesos_*.tsv.gz")), sep="\t", dtype=str, quoting=3)
a = pd.read_csv(next(RAW.glob("gc_adjudicaciones_*.tsv.gz")), sep="\t", dtype=str, quoting=3)
a["monto"] = pd.to_numeric(a.monto, errors="coerce").fillna(0.0)
a = a[(a.estado_adj == "active") & (a.fecha_adjudicacion.str[:4] == YEAR)]
m = a.merge(p, on="ocid", how="left")
m["mes"] = m.fecha_adjudicacion.str[:7]
m["fl"] = m.familias_unspsc.fillna("").str.split("|")
corte = m.fecha_adjudicacion.max()

def explode_fam(df):
    e = df.explode("fl")
    e = e[e.fl.fillna("") != ""]
    e["w"] = e.monto / e.groupby(level=0).fl.transform("count")
    return e

def resumen(df, k=12):
    tot = float(df.monto.sum())
    e = explode_fam(df)
    comp = df.groupby("entidad").agg(Q=("monto","sum"), n=("ocid","nunique")).sort_values("Q", ascending=False)
    uni = df.groupby(["unidad_compradora","entidad"]).agg(Q=("monto","sum"), n=("ocid","nunique")).sort_values("Q", ascending=False)
    prov = df.groupby(["proveedor_id"]).agg(nombre=("proveedor","first"), Q=("monto","sum"), n=("ocid","nunique")).sort_values("Q", ascending=False)
    fam = e.groupby("fl").agg(Q=("w","sum"), n=("ocid","nunique")).sort_values("Q", ascending=False)
    seg = e.assign(s=e.fl.str[:2]).groupby("s").w.sum().sort_values(ascending=False)
    mod = df.groupby("modalidad").agg(Q=("monto","sum"), n=("ocid","size")).sort_values("Q", ascending=False)
    mes = df.groupby("mes").agg(Q=("monto","sum"), n=("ocid","nunique"))
    return {
      "total": tot, "procesos": int(df.ocid.nunique()), "adjudicaciones": int(len(df)),
      "proveedores": int(df.proveedor_id.nunique()), "compradores": int(df.entidad.nunique()),
      "unidades": int(df.unidad_compradora.nunique()),
      "top5_proveedores_pct": float(prov.Q.head(5).sum()/tot) if tot else 0,
      "compradores_top": [{"nombre":short(i,60),"Q":float(r.Q),"n":int(r.n)} for i,r in comp.head(k).iterrows()],
      "unidades_top": [{"nombre":short(i[0],60),"entidad":short(i[1],40),"Q":float(r.Q),"n":int(r.n)} for i,r in uni.head(k).iterrows()],
      "proveedores_top": [{"nombre":short(r.nombre,54),"persona":persona(r.nombre),"Q":float(r.Q),"n":int(r.n)} for i,r in prov.head(k).iterrows()],
      "familias_top": [{"codigo":i,"nombre":fam_name(i),"Q":float(r.Q),"n":int(r.n)} for i,r in fam.head(k).iterrows()],
      "segmentos": [{"codigo":i,"nombre":SEG.get(i,"Otros"),"Q":float(v),"pct":float(v/tot)} for i,v in seg.head(10).items()],
      "modalidades": [{"nombre":re.sub(r"\s*\(.*?\)\s*","",i).strip() or i,"Q":float(r.Q),"n":int(r.n)} for i,r in mod.head(8).iterrows()],
      "meses": [{"mes":i,"Q":float(r.Q),"n":int(r.n)} for i,r in mes.iterrows()],
    }

data = {"corte": corte, "anio": YEAR, "fuente": "Guatecompras OCDS (ocds.guatecompras.gt), Minfin — CC BY 4.0",
        "general": resumen(m, 20)}

# Tipo de entidad
te = m.groupby("tipo_entidad").agg(Q=("monto","sum"), n=("ocid","nunique")).sort_values("Q", ascending=False)
data["general"]["tipos_entidad"] = [{"nombre":i,"Q":float(r.Q),"n":int(r.n)} for i,r in te.iterrows()]

# Sectores
data["sectores"] = {}
for k, s in SECTORES.items():
    d = m[m.entidad.isin(s["entidades"])]
    data["sectores"][k] = {"nombre": s["nombre"], **resumen(d, 10)}
data["sectores"]["ejecutivo"] = {"nombre":"Ejecutivo (Adm. Central)", **resumen(m[m.tipo_entidad=="Administración Central"], 10)}
data["sectores"]["municipal"] = {"nombre":"Municipalidades", **resumen(m[m.tipo_entidad.str.startswith("Gobiernos Locales", na=False)], 10)}

# Enfoque MSPAS (carrusel)
ms = m[m.entidad == "MINISTERIO DE SALUD PÚBLICA"]
r = resumen(ms, 10)
cd = ms[ms.modalidad.str.startswith("Compra Directa", na=False)]
r["compra_directa_pct_adj"] = float(len(cd)/len(ms))
r["compra_directa_pct_Q"] = float(cd.monto.sum()/ms.monto.sum())
r["top2_unidades_pct"] = float(sum(u["Q"] for u in r["unidades_top"][:2]) / r["total"])
data["mspas"] = r

# Hoy (último día con adjudicaciones)
h = m[m.fecha_adjudicacion == corte]
data["hoy"] = {"fecha": corte, "Q": float(h.monto.sum()), "adjudicaciones": int(len(h)), "procesos": int(h.ocid.nunique()),
               "top_comprador": short(h.groupby("entidad").monto.sum().idxmax(), 60) if len(h) else "",
               "top_comprador_Q": float(h.groupby("entidad").monto.sum().max()) if len(h) else 0}
dd = m.groupby("fecha_adjudicacion").agg(Q=("monto","sum"), n=("ocid","size")).tail(60)
data["dias"] = [{"fecha":i,"Q":float(x.Q),"n":int(x.n)} for i,x in dd.iterrows()]

# Constelación: top compradores x top proveedores (aristas)
topc = [c for c in m.groupby("entidad").monto.sum().sort_values(ascending=False).head(14).index]
mm = m[m.entidad.isin(topc)]
topp = mm.groupby("proveedor_id").monto.sum().sort_values(ascending=False).head(60).index
ed = mm[mm.proveedor_id.isin(topp)].groupby(["entidad","proveedor_id"]).agg(Q=("monto","sum"), nombre=("proveedor","first")).reset_index()
ed = ed[ed.Q > 5e6]
data["constelacion"] = {
  "compradores": [{"id":c,"nombre":short(c,40),"Q":float(m[m.entidad==c].monto.sum())} for c in topc],
  "proveedores": [{"id":pid,"nombre":short(g.nombre.iloc[0],40),"persona":persona(g.nombre.iloc[0]),"Q":float(g.Q.sum())} for pid,g in ed.groupby("proveedor_id")],
  "aristas": [{"s":r.entidad,"t":r.proveedor_id,"Q":float(r.Q)} for r in ed.itertuples()],
}

(OUT/"monitor_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("OK", corte, round(data["general"]["total"]/1e6,1), "MQ;", data["general"]["procesos"], "procesos")
print("MSPAS", round(r["total"]/1e6,1), r["procesos"], r["proveedores"], "top5", round(r["top5_proveedores_pct"],3),
      "CD adj", round(r["compra_directa_pct_adj"],3), "CD Q", round(r["compra_directa_pct_Q"],3), "top2u", round(r["top2_unidades_pct"],3))
print("HOY", data["hoy"])
print("constelacion", len(data["constelacion"]["proveedores"]), len(data["constelacion"]["aristas"]))
