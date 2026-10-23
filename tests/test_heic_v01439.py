"""v0.14.39 — Fotos HEIC (iPhone) en el procesamiento por sitio sin abrir la ventana principal.

Uso: python3 -I test_heic_v01439.py <carpeta_padre_plugin> <dir_salida>
Si «pillow-heif» no está instalado, solo se comprueba el mensaje claro.
"""
import sys, os
sys.path.insert(0, sys.argv[1]); OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
import numpy as np
from PIL import Image
ok_all = True
def chk(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (("  — " + str(extra)) if extra != "" else ""))
# Solo el núcleo del lote: no se importa ningún diálogo
from cobdosel import batch_core as bc, exif_gps
from cobdosel.lens_calibration import calibrate_regular_lens
try:
    import pillow_heif  # noqa: F401
    have = True
except ImportError:
    have = False
p = os.path.join(OUT, "IMG_0001.HEIC")
if have:
    from PIL.TiffImagePlugin import IFDRational as R
    rng = np.random.default_rng(0)
    img = np.full((3024, 4032, 3), (200, 215, 240), np.uint8)
    img[np.kron(rng.random((121, 162)) < 0.5, np.ones((25, 25), bool))[:3024, :4032]] = (25, 45, 25)
    ex = Image.Exif(); ex[0x010F] = "Apple"; ex[0x0110] = "iPhone 15 Pro"; ex[0x0112] = 6
    ifd = ex.get_ifd(0x8769); ifd[0xA405] = 24; ifd[0x920A] = R(678, 100)
    Image.fromarray(img).save(p, exif=ex.tobytes(), quality=90)
    e = exif_gps.extract_exif(p)
    chk("EXIF del iPhone leído (modelo y focal equivalente)", e.get("camera_model") == "iPhone 15 Pro" and e.get("focal_length_35mm") == 24.0)
    im, _s, _o = exif_gps.load_oriented_rgb_image(p)
    chk("foto HEIC cargada y girada (3024 × 4032)", im.size == (3024, 4032), im.size)
    cal = calibrate_regular_lens(20, 40, 1400, 3024, 4032, "rectilinear")
    r = bc.analyze_photo(p, cal, 27.0)
    chk("el lote analiza la foto HEIC sin abrir la ventana principal", r["caco"] > 0, round(r["caco"], 2))
else:
    print("  (pillow-heif no instalado: se omite la lectura HEIC)")
    open(p, "wb").write(b"\x00")
# Sin soporte HEIC: mensaje claro
saved = exif_gps.HEIF_SUPPORTED
exif_gps.HEIF_SUPPORTED = False
try:
    exif_gps.load_oriented_rgb_image(p); msg = ""
except RuntimeError as err:
    msg = str(err)
exif_gps.HEIF_SUPPORTED = saved
chk("sin pillow-heif: mensaje claro con la instalación y la alternativa JPEG", "pillow-heif" in msg and "Más compatible" in msg)
print("TODO OK" if ok_all else "HAY FALLAS"); sys.exit(0 if ok_all else 1)
