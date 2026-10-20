"""Pruebas 0.14.5: método del mínimo, aviso graduado del centro y arco de los puntos.
Uso: python3 -I test_v0145.py <carpeta_padre_del_paquete_cobdosel>"""
import sys, math
import numpy as np
sys.path.insert(0, sys.argv[1])
from cobdosel import canopy_analysis as ca, circle_measure as cm
fails = []


def check(n, ok, d=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (("  — " + str(d)) if d != "" else ""))
    ok or fails.append(n)


print("=== 1. Método del mínimo (Prewitt y Mendelsohn 1966) ===")
x = np.arange(256)
bim = 1e5 * np.exp(-0.5 * ((x - 40) / 15) ** 2) + 3e4 * np.exp(-0.5 * ((x - 220) / 10) ** 2) + 5
t, it = ca.minimum_threshold_from_hist(bim)
check("bimodal: corte en el valle (entre 120 y 190)", t is not None and 120 < t < 190, (t, it))
check("bimodal: corte = mínimo del histograma entre los modos (±3)",
      abs(t - (60 + int(np.argmin(bim[60:200])))) <= 3, (t, 60 + int(np.argmin(bim[60:200]))))
noisy = bim * (1 + 0.3 * np.random.default_rng(1).standard_normal(256)).clip(0.1)
t2, it2 = ca.minimum_threshold_from_hist(noisy)
check("bimodal con ruido: suaviza (%d iteraciones) y corta en el valle" % it2, it2 > 0 and 110 < t2 < 200, t2)
uni = 1e5 * np.exp(-0.5 * ((x - 40) / 20) ** 2) + 1
check("unimodal (sin cielo): None", ca.minimum_threshold_from_hist(uni)[0] is None)
check("plano: None", ca.minimum_threshold_from_hist(np.full(256, 1000.0))[0] is None)
o = 1e5 * np.exp(-0.5 * ((x - 60) / 20) ** 2); o[250:] += 4e4
g = np.repeat(x.astype(np.uint8), (o / 100).astype(int))
tm, used, note = ca.compute_auto_threshold(g, None, "minimum")
check("cielo sobreexpuesto: Mínimo da un corte válido entre dosel y cielo", used == "minimum" and 100 < tm < 250, tm)
gu = np.repeat(x.astype(np.uint8), (uni / 100).astype(int))
tu, used, note = ca.compute_auto_threshold(gu, None, "minimum")
check("sin dos modos: respaldo Otsu con nota", used == "otsu" and "Otsu" in note and tu == ca.compute_otsu_threshold(gu))
check("método otsu sin cambios", ca.compute_auto_threshold(g, None, "otsu")[0] == ca.compute_otsu_threshold(g))
mask = np.zeros(g.shape, bool); mask[: g.size // 2] = True
check("respeta la máscara de área válida", ca.compute_minimum_threshold(g, mask) == ca.minimum_threshold_from_hist(
    np.bincount(g[mask], minlength=256))[0])

print("\n=== 2. Aviso graduado del desplazamiento del centro ===")
W, H, r = 2560, 1920, 500.0
def cross(dx):
    cx, cy = W / 2 + dx, H / 2
    return [(cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r)]
for dx, kind in ((30, "none"), (80, "note"), (200, "warn")):
    res = cm.measure(cross(dx), "cruz", (W, H))
    got = "warn" if res["warnings"] else ("note" if res["notes"] else "none")
    check("desplazamiento %.1f %% → %s" % (res["centre_offset_pct"], kind), got == kind, (res["warnings"], res["notes"]))
res = cm.measure(cross(80), "cruz", (W, H))
check("nota 8 %: calibración usable y efecto con ojo de pez ≈ 0.5 %", "Puede usar la calibración" in res["notes"][0]
      and "0.5 %" in res["notes"][0], res["notes"][0])
check("ojo de pez: error 0 sin desplazamiento, ≈ 0.5 % con 7.8 %, ≈ 1.8 % con 15 %",
      cm.fisheye_offset_error_pct(0) < 1e-9 and abs(cm.fisheye_offset_error_pct(7.8) - 0.50) < 0.02
      and abs(cm.fisheye_offset_error_pct(15) - 1.84) < 0.02)

print("\n=== 3. Arco cubierto por los puntos (ajuste) ===")
def arc_pts(a0, a1, n):
    return [(W / 2 + r * math.cos(math.radians(a)), H / 2 + r * math.sin(math.radians(a))) for a in np.linspace(a0, a1, n)]
res = cm.measure(arc_pts(0, 315, 8), "ajuste", (W, H))
check("8 puntos cada 45°: arco 315°, sin aviso", abs(res["arc_deg"] - 315) < 1e-6 and not res["warnings"], res["arc_deg"])
res = cm.measure(arc_pts(0, 120, 8), "ajuste", (W, H))
check("8 puntos en 120°: aviso de distribución", abs(res["arc_deg"] - 120) < 1e-6 and any("arco de 120°" in w for w in res["warnings"]))
res = cm.measure(arc_pts(-100, 100, 6), "ajuste", (W, H))
check("arco que cruza 0° (200°) calculado bien, sin aviso", abs(res["arc_deg"] - 200) < 1e-6 and not res["warnings"], res["arc_deg"])

print("\n=== 4. Dos diámetros con una línea fuera del centro (0.14.6) ===")
cx, cy, rr = 1300.0, 950.0, 500.0
xo = cx + 50.0                       # línea N–S marcada 50 px a la derecha del centro (sobre la guía)
hh = math.sqrt(rr ** 2 - 50.0 ** 2)
pts4 = [(cx - rr, cy), (cx + rr, cy), (xo, cy - hh), (xo, cy + hh)]
res = cm.measure(pts4, "cruz", (W, H))
check("centro = el del círculo real (antes: intersección desplazada 50 px)",
      math.hypot(res["centre_xy"][0] - cx, res["centre_xy"][1] - cy) < 1e-6, res["centre_xy"])
check("diámetro = diámetro real 1000 px (antes: promedio con la cuerda, %.1f px)" % ((1000 + 2 * hh) / 2),
      abs(res["diameter_px"] - 1000.0) < 1e-6, res["diameter_px"])
check("0.14.7: 4 puntos sobre el mismo círculo → nota informativa (resultado válido), sin advertencias",
      any("punto medio" in n and "la medición es correcta" in n for n in res["notes"]) and res["warnings"] == []
      and res["verdict"][0] == "usable_avisos",
      (res["warnings"], res["notes"]))
bad = pts4[:3] + [(xo, cy + hh - 60)]
resb = cm.measure(bad, "cruz", (W, H))
check("0.14.7: un clic fuera de la línea → advertencia «Repita la medición»",
      any("no están sobre un mismo círculo" in w for w in resb["warnings"]), resb["warnings"])
res = cm.measure([(cx - rr, cy), (cx + rr, cy), (cx, cy - rr), (cx, cy + rr)], "cruz", (W, H))
check("dos diámetros verdaderos: igual que antes (diámetro medio, sin avisos)",
      abs(res["diameter_px"] - 1000) < 1e-6 and res["warnings"] == [] and res["midpoint_gap_pct"] < 1e-9)

print("\n=== 5. Veredicto global (0.14.11) ===")
far = [(p[0] + 860.0, p[1]) for p in pts4]            # círculo muy desplazado + línea fuera del centro
resf = cm.measure(far, "cruz", (4000, 3000))
scopes = [(i["level"], i["scope"]) for i in resf["issues"]]
check("foto desplazada + medición correcta → «repita la fotografía»; medición como nota, no contradice",
      resf["verdict"][0] == "repetir_foto" and ("warn", "fotografia") in scopes and ("note", "medicion") in scopes,
      (resf["verdict"], scopes))
check("veredicto «repita la medición» si solo fallan los clics",
      cm.measure(bad, "cruz", (W, H))["verdict"][0] in ("repetir_medicion", "repetir_foto"))
okr = cm.measure([(cx - rr + 30, cy - 15), (cx + rr + 30, cy - 15), (cx + 30, cy - rr - 15), (cx + 30, cy + rr - 15)],
                 "cruz", (2600, 1870))
check("todo en tolerancia → «Dentro de tolerancia»", okr["verdict"][0] == "ok", okr["verdict"])

print("\nRESULTADO: %s" % ("TODAS LAS PRUEBAS PASAN" if not fails else "FALLAN: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
