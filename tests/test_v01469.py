"""CobDosel 0.14.69: avisos de consistencia por parcela (varios días, más de 20 min, rango del CaCo > 30 puntos),
con o sin formulario; pie del informe del lote igual al de una foto; «Cámara:» y «Canal de color:» en el informe
de una foto.

Uso: python3 -I test_v01469.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
"""
import sys, os, re
sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
from cobdosel import batch_core as bc  # noqa: E402

fails = []


def chk(name, ok, info=""):
    print(("OK   " if ok else "FALLA") + " " + name + ("  [" + str(info)[:300] + "]" if info != "" else ""))
    if not ok:
        fails.append(name)


def rec(p, t, c, ok=True):
    return {"parcela": p, "punto": "x", "archivo": "f_{}_{}.jpg".format(p, t), "valida": ok, "emparejado_por": "hora",
            "hora_exif": t, "caco": c, "decision": "automático", "reemplaza_a": ""}


# Caso real: 22 fotos asignadas por orden de hora, 11 por parcela
p1 = [rec("1", "2026-06-18 08:50:03", 90.94), rec("1", "2026-06-18 09:11:23", 96.75)] + \
     [rec("1", "2026-06-27 13:5{}:00".format(i), 93.5) for i in range(9)]
p2 = [rec("2", "2026-06-27 13:59:0{}".format(i), 94.6) for i in range(3)] + \
     [rec("2", "2026-06-28 11:05:09", 56.47), rec("2", "2026-06-28 12:17:56", 97.66)] + \
     [rec("2", "2026-06-28 11:0{}:00".format(i), 72.0) for i in range(6)]
w = bc.plot_consistency_warnings(p1 + p2)
chk("1 parcela 1: fotos de 2 días (18/06 y 27/06)", any(x.startswith("Parcela 1: fotos de 2 días (18/06/2026, 27/06/2026)") for x in w), w)
chk("1 parcela 2: fotos de 2 días (27/06 y 28/06)", any(x.startswith("Parcela 2: fotos de 2 días (27/06/2026, 28/06/2026)") for x in w), w)
chk("1 parcela 2: rango 56.47–97.66 % (41.19 puntos) → aviso",
    any("Parcela 2: el CaCo de sus fotos va de 56.47 a 97.66 % (41.19 puntos, más de 30)" in x for x in w), w)
chk("1 parcela 1: rango 5.81 puntos → sin aviso de rango", not any(x.startswith("Parcela 1: el CaCo") for x in w))
# mismo día, más de 20 min
p3 = [rec("3", "2026-06-28 11:00:00", 80.0), rec("3", "2026-06-28 11:35:00", 82.0)]
w3 = bc.plot_consistency_warnings(p3)
chk("2 mismo día, 35 min → «fotos con 35 min 00 s de diferencia (más de 20 min)»",
    w3 == ["Parcela 3: fotos con 35 min 00 s de diferencia (más de 20 min); revise la asignación de parcelas."], w3)
# parcela correcta: sin avisos
p4 = [rec("4", "2026-06-28 11:00:{:02d}".format(10 * i), 90.0 + i) for i in range(5)]
chk("3 parcela bien asignada (mismo punto, 40 s, rango 4 puntos): sin avisos", bc.plot_consistency_warnings(p4) == [])
chk("3 fotos inválidas no cuentan para el rango",
    bc.plot_consistency_warnings([rec("5", "2026-06-28 11:00:00", 90.0), rec("5", "2026-06-28 11:00:30", 20.0, ok=False)]) == [])
# aggregate los incluye en los avisos del sitio
agg = bc.aggregate(p1 + p2, 2)
chk("4 aggregate: avisos de consistencia en los avisos del sitio", sum(1 for x in agg["avisos"] if x.startswith("Parcela ")) == 3,
    agg["avisos"])
# sin formulario: el aviso de 20 min no se repite
src = open(os.path.join(sys.argv[1], "cobdosel", "batch_core.py"), encoding="utf-8").read()
chk("4 sin formulario: no se repite el aviso de 20 min; el aviso explica que las parcelas son por hora",
    'abarcan más de 20 min; revise la asignación.")]' in src and "se forman por hora de captura, no por ubicación" in src)
# pie del lote igual al de una foto
batch = dict(agg); batch["fotos"] = p1 + p2; batch["parametros"] = {}
hp = os.path.join(OUT, "lote.html")
bc.write_html(batch, hp, "0.14.69", "Prueba")
ht = open(hp, encoding="utf-8").read()
rep = open(os.path.join(sys.argv[1], "cobdosel", "html_report.py"), encoding="utf-8").read()
foot = re.sub(r"\s+", " ", ht.split("<footer")[1].split("</footer>")[0])
chk("5 pie del lote: Tichý (2016) con doi; CobDosel vX para QGIS · Autor · Contacto",
    "Basado en Tichý (2016), <a href=\"https://doi.org/10.1111/jvs.12350\"" in foot and "doi:10.1111/jvs.12350</a>.<br/>" in foot
    and "<strong>CobDosel v0.14.69</strong> para QGIS · Autor: Jorge Fallas · Contacto: <a href=\"mailto:jfallas56@gmail.com\">jfallas56@gmail.com</a>" in foot
    and "Generado por" not in ht, foot)
chk("5 pie de una foto con el mismo texto", "Basado en Tichý (2016)," in rep and "para QGIS · Autor: Jorge Fallas · Contacto:" in rep)
chk("6 informe de una foto: «Cámara:» y «Canal de color:»",
    '<span class="label">Cámara:</span>' in rep and '<span class="label">Canal de color:</span>' in rep
    and "Cámara de la foto:</span>" not in rep and "Canal de umbralización" not in rep)
print("\n{} fallas".format(len(fails)) if fails else "\nTodo OK")
sys.exit(1 if fails else 0)
