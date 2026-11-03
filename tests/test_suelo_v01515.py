"""CobDosel 0.15.15: aviso «a revisar» para el usuario final: los dos valores, qué parte es dudosa, que se informa
Canopeo por ser la regla publicada (no «la correcta») y dónde verlo (tecla C en la ventana; imagen en el informe).

Uso: python3 -I test_suelo_v01515.py <carpeta_padre_plugin> <dir_salida>
"""
import os, sys
sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
import numpy as np
from cobdosel import ground_cover as gc
ok = True


def chk(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))


res = {"revisar": True, "diferencia_pct": -5.32, "verde_canopeo_pct": 71.24, "verde_exgexr_pct": 76.56}
w = gc.agreement_note(res)
chk("1 los dos valores y la diferencia", "difieren 5.3 puntos (Canopeo 71.2 %; ExG − ExR 76.6 %" in w, w)
chk("1 qué es la parte dudosa y que no es un error", "píxeles mezcla en el borde entre hojas verdes y material seco" in w
    and "No es un error de la foto ni de la clasificación" in w)
chk("1 por qué se informa Canopeo (regla publicada) y cuánto sería con ExG − ExR",
    "El valor que se informa es el de Canopeo, la regla publicada que usa CobDosel" in w
    and "el verde sería 76.6 %" in w)
chk("1 ventana: pulse C", "pulse C en la ventana" in w and "cian: verde solo para ExG − ExR" in w)
r = gc.agreement_note(res, where="informe")
chk("2 informe: remite a la imagen, no a la tecla", "vea la imagen «Dónde difieren Canopeo y ExG − ExR»" in r
    and "pulse C" not in r)
o = gc.agreement_note({"revisar": True, "diferencia_pct": 6.0, "verde_canopeo_pct": 50.0, "verde_exgexr_pct": 44.0})
chk("3 Canopeo mayor: el texto se invierte (sí cuenta / no cuenta) y cambia la causa",
    "que sí cuenta esa parte dudosa; con ExG − ExR, que no la cuenta, el verde sería 44.0 %" in o
    and "suelo, piedras o algas de color verdoso" in o, o)
chk("3 sin «a revisar», sin aviso", gc.agreement_note(dict(res, revisar=False)) == "")
a = np.zeros((40, 40, 3), np.uint8); a[:, :20] = (40, 150, 40); a[:, 20:] = (128, 132, 60)
rr = gc.summarize(a, [None] * 4)
hp = os.path.join(OUT, "i.html")
gc.write_html(rr, {"archivo": "f.png", "modo_area": "Cuadro", "lado_m": 1, "area_m2": 1}, a, [], [], hp, "x")
ht = open(hp, encoding="utf-8").read()
chk("4 el informe usa el texto del informe", rr["revisar"] and "vea la imagen «Dónde difieren" in ht and "pulse C" not in ht)
src = open(os.path.join(sys.argv[1], "cobdosel", "ground_cover_dialog.py"), encoding="utf-8").read()
chk("4 la ventana usa el texto de la ventana", 'lines.append("A revisar: " + gc.agreement_note(r))' in src)
from cobdosel.help_texts import GROUND_HELP_HTML
chk("5 ayuda: se informa Canopeo por ser la regla publicada", "El valor que se informa es el de Canopeo</b>" in GROUND_HELP_HTML)
print("\nTodo OK" if ok else "\nHAY FALLAS")
sys.exit(0 if ok else 1)
