"""v0.14.38 — Registro de hechos verificados y revisión de textos (sin Qt).

Cada hecho proviene de una medición real (app GLAMA, Pixel 10) o de una decisión del usuario. Si el
código o un texto se apartan de ellos, la prueba falla. Los textos de ayuda, README y metadata se revisan
contra afirmaciones retiradas (por ejemplo, que GLAMA usa atan(D/H)/2) y contra códigos internos o
números de versión mostrados al usuario.
Uso: python3 -I test_hechos_v01438.py <carpeta_padre_plugin>
"""
import sys, os, re, math
sys.path.insert(0, sys.argv[1])
PLUG = os.path.join(sys.argv[1], "cobdosel")
from cobdosel import lens_calibration as lc, batch_core as bc, focal_check as fc

ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))

# ---- H1. App GLAMA (2026-10-22): misma foto del círculo, D y H escritos; radio del hemisferio y máscara
# recomendada leídos en la app. r = 268,3 px en la vista de 1080 px (lado menor 3000 px de una foto 4000×3000).
GLAMA_APP = [(20.6, 40.1, 1676, 61.0), (20.7, 40.1, 1669, 60.9), (20.8, 40.1, 1661, 60.7), (20.9, 40.1, 1653, 60.6),
             (21.0, 40.1, 1646, 60.5), (21.1, 40.1, 1638, 60.3), (21.2, 40.1, 1631, 60.2), (21.3, 40.1, 1624, 60.1),
             (21.3, 39.8, 1612, 59.8), (21.3, 40.0, 1620, 60.0), (21.3, 41.0, 1658, 60.7), (21.3, 42.0, 1697, 61.4),
             (21.3, 43.0, 1736, 62.0), (21.3, 39.0, 1581, 59.3), (21.3, 38.0, 1542, 58.5)]
d_px = 2 * 268.3 * 3000 / 1080.0
worst_R = worst_m = 0.0
for D, H, R_app, m_app in GLAMA_APP:
    cal = lc.calibrate_regular_lens(D, H, d_px, 4000, 3000, projection="angular")
    R_eq = lc.glama_equivalent_radius(cal, 4000, 3000)
    worst_R = max(worst_R, abs(R_eq - R_app))
    worst_m = max(worst_m, abs((90 - 90 * 540 / R_eq) - m_app))
chk("H1 GLAMA: «Lineal» con atan(D/2H) reproduce el radio de la app en 15 combinaciones (±1,5 px)", worst_R <= 1.5, round(worst_R, 2))
chk("H1 GLAMA: máscara recomendada = 90 − 90·540/R (±0,1°)", worst_m <= 0.1, round(worst_m, 3))

# ---- H2. Pixel 10 a 1x, H = 40 cm, tres círculos medidos en CobDosel (2026-10-22)
P10 = [(12.1, 886.64), (20.6, 1512.68), (23.4, 1720.73)]
fmm = [fc.calibration_focal_mm(lc.calibrate_regular_lens(D, 40, d, 4000, 3000, "rectilinear")) for D, d in P10]
chk("H2 Pixel 10: «Rectilínea» da la misma focal con los tres círculos (±0,3 %)", (max(fmm) / min(fmm) - 1) < 0.006,
    [round(x, 2) for x in fmm])
chk("H2 Pixel 10: focal equivalente 25,4 mm (±0,2)", abs(sum(fmm) / 3 - 25.4) <= 0.2, round(sum(fmm) / 3, 2))
Rl = [lc.calibrate_regular_lens(D, 40, d, 4000, 3000, "angular")["virtual_radius_px"] for D, d in P10]
chk("H2 Pixel 10: con «Lineal» R crece con el círculo (+1,6 % y +2,4 %)",
    abs(100 * (Rl[1] / Rl[0] - 1) - 1.6) < 0.15 and abs(100 * (Rl[2] / Rl[0] - 1) - 2.4) < 0.15,
    [round(100 * (x / Rl[0] - 1), 2) for x in Rl])

# ---- H3. Decisiones del usuario
chk("H3 máscara estándar 63° en el lote", bc.DEFAULT_MASK_DEG == 63.0)
chk("H3 modelo predeterminado para lente regular: Rectilínea", lc.PROJECTIONS_REGULAR[0] == "rectilinear")
chk("H3 «Lineal» se llama «Lineal (compatible con Polar de GLAMA)»",
    lc.PROJECTIONS["angular"]["label"] == "Lineal (compatible con Polar de GLAMA)")
chk("H3 umbrales de la focal: EXIF 8/15 %, propia 3/8 %",
    (fc.EXIF_NOTE_PCT, fc.EXIF_WARN_PCT, fc.OWN_NOTE_PCT, fc.OWN_WARN_PCT) == (8.0, 15.0, 3.0, 8.0))
chk("H3 fórmula exacta atan(D/2H)", abs(lc.calibrate_regular_lens(33, 40, 2000, 4000, 3000, "rectilinear")["zenith_ref_deg"]
                                         - math.degrees(math.atan(33 / 80.0))) < 1e-9)

# ---- T. Revisión de textos para el usuario
def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()
help_txt = read(os.path.join(PLUG, "help_texts.py"))
readme = read(os.path.join(PLUG, "README.md"))
meta = read(os.path.join(PLUG, "metadata.txt"))
about = [l for l in meta.splitlines() if l.startswith(("about=", "description="))]
texts = {"ayuda": help_txt, "README": readme.split("## Historial")[0], "metadata (about)": "\n".join(about)}

def sentences(t):
    return re.split(r"(?<=[.!?])\s+|\n", t)
for name, t in texts.items():
    bad = [s for s in sentences(t) if "GLAMA" in s and "atan(D/H)/2" in s and not re.search(r"exacta|misma|comprob", s)]
    chk("T {}: ninguna frase atribuye a GLAMA la aproximación atan(D/H)/2".format(name), not bad, bad[:1])
    chk("T {}: sin «Lineal (lente regular)» ni «Lineal» como predeterminado".format(name),
        "Lineal (lente regular)" not in t and not re.search(r"Lineal[^.;\n]{0,40}(por defecto|predeterminado)", t))
    chk("T {}: sin «63° según Tichý»".format(name), not re.search(r"63\s*°[^.\n]{0,30}según Tichý", t))
    chk("T {}: sin «Máscara mínima» como etiqueta".format(name), "«Máscara mínima»" not in t)
    chk("T {}: sin códigos internos de modelos".format(name),
        not re.search(r"«(rectilinear|angular|equisolid|orthographic|stereographic|polar)»", t))
vers = [m.group(0) for m in re.finditer(r"(antes de|desde( la)?( versión)?|versión) \d+\.\d+(\.\d+)?", help_txt)]
chk("T ayuda: sin referencias a versiones anteriores", not vers, vers[:3])
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
