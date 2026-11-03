"""CobDosel 0.15.10: «Regla para puntos dudosos» en la ayuda de «Cobertura del suelo», con referencias.

Uso: python3 -I test_suelo_v01510.py <carpeta_padre_plugin>
"""
import os, re, sys
sys.path.insert(0, sys.argv[1])
src = open(os.path.join(sys.argv[1], "cobdosel", "help_texts.py"), encoding="utf-8").read()
ns = {}
exec(compile(re.search(r'^GROUND_HELP_HTML = """.*?^"""', src, re.S | re.M).group(0), "help", "exec"), ns)
H = ns["GROUND_HELP_HTML"]
ok = True


def chk(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))


li = re.search(r"<li><b>Regla para puntos dudosos:</b>(.*?)</li>", H, re.S)
chk("regla presente en la sección de clasificar", li is not None and H.index("Regla para puntos dudosos")
    > H.index("<h3>4. Clasificar los puntos</h3>"))
t = " ".join(li.group(1).split()) if li else ""
chk("1 solo el píxel bajo el centro de la cruz", "solo el píxel bajo el centro de la cruz" in t)
chk("2 píxel mixto: color dominante a zoom máximo", "color dominante a zoom máximo" in t)
chk("3 si no se puede decidir: «No identificable»", "si no se puede decidir, «No identificable»" in t)
chk("4 misma regla y conteo de dudosos; «Borde» como control", "misma regla en todas las fotos" in t
    and "cuántos puntos fueron dudosos" in t and "«Borde»" in t)
chk("referencias: Herrick et al. 2005 y Booth et al. 2006", "Herrick et al. 2005" in t and "Booth et al. 2006" in t)
ver = re.search(r'VERSION = "([^"]+)"', open(os.path.join(sys.argv[1], "cobdosel", "_version.py")).read()).group(1)
meta = open(os.path.join(sys.argv[1], "cobdosel", "metadata.txt"), encoding="utf-8").read()
chk("versión coherente (_version.py, metadata.txt)", "version={}\n".format(ver) in meta
    and "changelog={} (".format(ver) in meta, ver)
print("\nTodo OK" if ok else "\nHAY FALLAS")
sys.exit(0 if ok else 1)
