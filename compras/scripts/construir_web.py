#!/usr/bin/env python3
"""Inyecta compras/data/monitor_data.json en compras/plantilla.html -> compras/index.html"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
tpl = (ROOT / "plantilla.html").read_text(encoding="utf-8")
data = json.loads((ROOT / "data" / "monitor_data.json").read_text(encoding="utf-8"))
assert "/*__DATA__*/null" in tpl, "La plantilla no tiene el marcador de datos"
js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
(ROOT / "index.html").write_text(tpl.replace("/*__DATA__*/null", js), encoding="utf-8")
print("compras/index.html listo · corte", data["corte"])
