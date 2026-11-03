"""CobDosel 0.15.11: metadata.txt (lo que muestra el repositorio de QGIS) y README.

Uso: python3 -I test_meta_v01511.py <carpeta_padre_plugin>
"""
import configparser, os, re, sys
root = sys.argv[1]
ok = True


def chk(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))


cp = configparser.ConfigParser(interpolation=None)
cp.read(os.path.join(root, "cobdosel", "metadata.txt"), encoding="utf-8")
g = cp["general"]
desc, about, tags = g["description"], g["about"], g["tags"]
ver = re.search(r'VERSION = "([^"]+)"', open(os.path.join(root, "cobdosel", "_version.py")).read()).group(1)
chk("metadata se lee con configparser; versión = _version.py", g["version"] == ver, (g["version"], ver))
chk("description: dosel y suelo", "dosel" in desc and "suelo" in desc and "ground cover" in desc, desc)
for bad in ("Modificado", "Modified", "radio del hemisferio de la app GLAMA", "GLAMA app hemisphere radius"):
    chk("sin «{}» en description ni about".format(bad), bad not in desc and bad not in about)
chk("about ES y EN: las dos herramientas", "(2) Cobertura del suelo" in about and "(2) Ground cover" in about)
chk("about: calibración con baldosas y referencias del suelo", "baldosas" in about and "Patrignani y Ochsner 2015"
    in about and "Meyer y Neto 2008" in about)
chk("about: LAI solo con ojo de pez de 180°", "solo con ojo de pez de 180°" in about)
chk("etiquetas de suelo", all(t in tags.split(",") for t in ("cobertura del suelo", "ground cover", "Canopeo")))
r1 = open(os.path.join(root, "README.md"), encoding="utf-8").read()
r2 = open(os.path.join(root, "cobdosel", "README.md"), encoding="utf-8").read()
chk("README de la raíz igual al del complemento", r1 == r2)
chk("README: insignia con la versión actual", "badge/version-{}-green".format(ver) in r2)
chk("README: sección «Cobertura del suelo» y resumen en inglés sin funciones retiradas",
    "## Cobertura del suelo (foto hacia abajo)" in r2 and "Modified CaCo" not in r2.split("## English summary")[1]
    and "**Ground cover:**" in r2)
print("\nTodo OK" if ok else "\nHAY FALLAS")
sys.exit(0 if ok else 1)
