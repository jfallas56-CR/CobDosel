"""v0.14.38 — Pruebas que deben responder a sus entradas (sin Qt).

Cada parámetro clave (corte, máscara, modelo, D, H) debe cambiar el resultado; si una prueba no puede
fallar, no prueba nada. También: sin parámetros ignorados en silencio y corte de Otsu en el lado correcto.
Uso: python3 -I test_respuesta_v01438.py <carpeta_padre_plugin> <dir_salida>
"""
import sys, os
sys.path.insert(0, sys.argv[1]); OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
import numpy as np
from PIL import Image
from cobdosel import batch_core as bc
from cobdosel.lens_calibration import calibrate_regular_lens
from cobdosel.canopy_analysis import compute_otsu_threshold, threshold_image

ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))

# Foto sintética 4000 × 3000: dosel en bloques con cielo graduado (para que el corte importe)
rng = np.random.default_rng(7)
by, bx = np.mgrid[0:120, 0:160]
rb = np.hypot(bx * 25 + 12 - 2000, by * 25 + 12 - 1500) / 1500.0      # radio relativo de cada bloque
blocks = rng.random((120, 160)) < np.clip(0.9 - 0.8 * rb, 0.05, 0.9)   # más cielo al centro, más dosel al borde
sky = np.kron(blocks, np.ones((25, 25), bool))
yy, xx = np.mgrid[0:3000, 0:4000]
r = np.hypot(xx - 2000, yy - 1500) / 2500.0
img = np.zeros((3000, 4000, 3), np.uint8)
lev = (120 + 120 * (1 - r)).clip(0, 255).astype(np.uint8)          # cielo más oscuro hacia el borde
img[sky] = np.stack([lev, lev, np.minimum(lev + 20, 255)], -1)[sky]
img[~sky] = [25, 45, 25]
p = os.path.join(OUT, "resp.jpg"); Image.fromarray(img).save(p, quality=95)

def caco(cal, zen=27.0, cut=150):
    return bc.analyze_photo(p, cal, zen, cut_rule="fixed", fixed_cut=cut)["caco"]

rect = calibrate_regular_lens(12.1, 40, 886.64, 4000, 3000, "rectilinear")
lin = calibrate_regular_lens(12.1, 40, 886.64, 4000, 3000, "angular")
base = caco(rect)
chk("corte: 150 → 200 cambia el CaCo", abs(caco(rect, cut=200) - base) > 0.5, (round(base, 2), round(caco(rect, cut=200), 2)))
chk("máscara: 63° → 60° cambia el CaCo", abs(caco(rect, zen=30.0) - base) > 0.05, round(caco(rect, zen=30.0), 2))
chk("modelo: Rectilínea → Lineal cambia el CaCo", abs(caco(lin) - base) > 0.05, round(caco(lin), 2))
chk("D: 12,1 → 14 cm (mismo diámetro en px) cambia el CaCo",
    abs(caco(calibrate_regular_lens(14.0, 40, 886.64, 4000, 3000, "rectilinear")) - base) > 0.05)
chk("H: 40 → 46 cm cambia el CaCo",
    abs(caco(calibrate_regular_lens(12.1, 46, 886.64, 4000, 3000, "rectilinear")) - base) > 0.05)
chk("mismo todo → mismo CaCo (diferencia 0)", caco(rect) == base)
a = bc.analyze_photo(p, rect, 27.0)
chk("corte automático y corte fijo igual al automático dan el mismo CaCo",
    abs(bc.analyze_photo(p, rect, 27.0, cut_rule="fixed", fixed_cut=a["corte"])["caco"] - a["caco"]) < 1e-9)
chk("corte fijo: el método se registra como «fijo»",
    bc.analyze_photo(p, rect, 27.0, cut_rule="fixed", fixed_cut=150)["metodo_corte"] == "fijo")
# Sin parámetros ignorados en silencio
for kw, label in ((dict(fixed_cut=150), "fixed_cut sin cut_rule='fixed'"),
                  (dict(cut_rule="fixed"), "cut_rule='fixed' sin fixed_cut"),
                  (dict(cut_rule="otsuu"), "cut_rule desconocido")):
    try:
        bc.analyze_photo(p, rect, 27.0, **kw); raised = False
    except ValueError:
        raised = True
    chk("analyze_photo rechaza " + label, raised)
# Otsu: el corte separa «< t» (dosel) de «≥ t» (cielo) en el lado correcto
two = np.array([30] * 500 + [230] * 500, np.uint8).reshape(10, 100)
t = compute_otsu_threshold(two)
chk("Otsu con dos valores (30 y 230): 30 es dosel y 230 cielo", 30 < t <= 230 and threshold_image(two, t).mean() == 0.5, t)
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
