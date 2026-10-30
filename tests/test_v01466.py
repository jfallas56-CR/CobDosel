"""CobDosel 0.14.66: la ayuda explica los anillos del informe; los pesos que da son los del Índice CaCo.

Uso: python3 -I test_v01466.py <carpeta_padre_plugin> <dir_salida> <PyQt5|PyQt6>
"""
import sys, os, math
sys.path.insert(0, sys.argv[1])
os.makedirs(sys.argv[2], exist_ok=True)
fails = []


def chk(name, ok, info=""):
    print(("OK   " if ok else "FALLA") + " " + name + ("  [" + str(info) + "]" if info != "" else ""))
    if not ok:
        fails.append(name)


hlp = open(os.path.join(sys.argv[1], "cobdosel", "help_texts.py"), encoding="utf-8").read()
chk("1 ayuda: «Anillos del informe» con cierre sin conversión y uso", "<b>Anillos del informe:</b>" in hlp
    and "sin conversión a la vertical" in hlp and "ver si el dosel es parejo" in hlp)
b = [0, 6.75, 13.5, 20.25, 27]
s2 = lambda d: math.sin(math.radians(d)) ** 2
w = [(s2(b[i + 1]) - s2(b[i])) / s2(27) for i in range(4)]
chk("2 pesos del CaCo (sin θ·cos θ) con 4 anillos: 7, 20, 32, 42 %", [round(100 * x) for x in w] == [7, 20, 32, 42],
    [round(100 * x, 1) for x in w])
cov = [97.96, 98.11, 98.89, 97.60]
caco = sum(w[i] * 100 * (1 - (1 - cov[i] / 100) ** math.cos(math.radians((b[i] + b[i + 1]) / 2))) for i in range(4))
chk("3 ejemplo del manual (varios estratos): 4 anillos llevados a la vertical dan 97.66 %", abs(caco - 97.66) < 0.01, round(caco, 3))
print("\n{} fallas".format(len(fails)) if fails else "\nTodo OK")
sys.exit(1 if fails else 0)
