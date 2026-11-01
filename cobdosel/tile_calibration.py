"""Calibración de la cámara con un rectángulo de tamaño conocido en el suelo (CobDosel 0.15.3).

Sirve un bloque de baldosas (n × paso entre juntas), un cuadro de muestreo o una hoja de papel: se marcan sus
4 esquinas en una foto tomada hacia abajo a la altura H. La homografía suelo → foto da la escala (px/cm) en el
centro de la foto; con la cámara rectilínea (cámara principal del teléfono) f = escala · H. Se corrige la
inclinación de la cámara con la pose deducida de la misma homografía (Zhang 2000): K⁻¹·Hm = λ·[r1 r2 t]; la
altura del lente sobre el suelo es |r3 · t|, que crece en proporción a f; se busca la f cuya altura es H.

Con dos fotos a dos alturas (H1 y H2, medidas desde el MISMO punto del teléfono) se cancela la distancia
desconocida δ entre ese punto y el lente: h_i(f) = H_i + δ, de modo que f = f·(H2 − H1)/(h2(f) − h1(f)) y
δ = h1(f) − H1.

El resultado se expresa como el círculo equivalente que usa CobDosel (D, H, diámetro en px): con una lente
rectilínea d = f·D/H es exacto con cualquier D.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import math

import numpy as np

from .ground_cover import order_corners, homography

TILE_PITCH_DEFAULT_CM = 32.0
MIN_HEIGHT_DIFF_CM = 20.0        # con menos diferencia entre alturas el error de f se multiplica
TILT_WARN_DEG = 3.0              # inclinación que conviene corregir antes de usar «Foto entera»


def block_homography(corners_px, side1_cm, side2_cm):
    """Homografía suelo (cm) → foto (px). side1: lado entre las esquinas superior izquierda y superior derecha de
    la foto; side2: entre superior derecha e inferior derecha."""
    if side1_cm <= 0 or side2_cm <= 0:
        raise ValueError("Los lados del rectángulo deben ser positivos.")
    img = order_corners(corners_px)
    world = np.array([[0, 0], [side1_cm, 0], [side1_cm, side2_cm], [0, side2_cm]], float)
    return homography(world, img)


def center_scale(Hm, width_px, height_px):
    """Escala (px/cm) en el centro de la foto: (a lo ancho, a lo alto, media geométrica por el área)."""
    Hi = np.linalg.inv(Hm)

    def w(u, v):
        q = Hi @ np.array([u, v, 1.0])
        return q[:2] / q[2]

    cx, cy, d = width_px / 2.0, height_px / 2.0, 5.0
    gx = w(cx + d, cy) - w(cx - d, cy)
    gy = w(cx, cy + d) - w(cx, cy - d)
    sx = 2 * d / np.linalg.norm(gx)
    sy = 2 * d / np.linalg.norm(gy)
    area = abs(gx[0] * gy[1] - gx[1] * gy[0])          # cm² de un cuadrado de 2d × 2d px
    return sx, sy, 2 * d / math.sqrt(area)


def plane_pose(Hm, f_px, width_px, height_px):
    """(altura del lente sobre el plano en cm, inclinación de la cámara en grados) para una focal dada."""
    K = np.array([[f_px, 0, width_px / 2.0], [0, f_px, height_px / 2.0], [0, 0, 1.0]])
    M = np.linalg.inv(K) @ Hm
    lam = 2.0 / (np.linalg.norm(M[:, 0]) + np.linalg.norm(M[:, 1]))
    r1, r2, t = M[:, 0] * lam, M[:, 1] * lam, M[:, 2] * lam
    r3 = np.cross(r1, r2)
    r3 /= np.linalg.norm(r3)
    height = abs(float(r3 @ t))
    tilt = math.degrees(math.acos(min(1.0, abs(float(r3[2])))))
    return height, tilt


def _focal_for_height(Hm, w, h, height_cm):
    s = center_scale(Hm, w, h)[2]
    f = s * height_cm
    for _ in range(20):
        hh, _t = plane_pose(Hm, f, w, h)
        f_new = f * height_cm / hh
        if abs(f_new - f) < 1e-6 * f:
            f = f_new
            break
        f = f_new
    return f


def _photo(m):
    w, h = float(m["width_px"]), float(m["height_px"])
    Hm = block_homography(m["corners_px"], m["side1_cm"], m["side2_cm"])
    sx, sy, s = center_scale(Hm, w, h)
    return Hm, w, h, (sx, sy, s)


def calibrate_tiles(m1, m2=None):
    """
    Focal (px, en el tamaño nativo de la foto) a partir de una o dos fotos del rectángulo conocido.

    m: dict con corners_px (4 esquinas en px nativos), side1_cm, side2_cm, height_cm (altura medida),
    width_px, height_px (tamaño nativo). Con m2, las dos fotos deben tener el mismo tamaño y las alturas medirse
    desde el mismo punto del teléfono.

    Devuelve dict: focal_px, lens_height_cm (altura real del lente en la foto 1), offset_cm (δ; None con una foto),
    photos: [{height_cm, lens_height_cm, tilt_deg, scale_x, scale_y, scale_px_cm}], n_photos, width_px, height_px.
    """
    Hm1, w, h, sc1 = _photo(m1)
    if m2 is None:
        f = _focal_for_height(Hm1, w, h, float(m1["height_cm"]))
        lh1, t1 = plane_pose(Hm1, f, w, h)
        photos = [{"height_cm": float(m1["height_cm"]), "lens_height_cm": lh1, "tilt_deg": t1,
                   "scale_x": sc1[0], "scale_y": sc1[1], "scale_px_cm": sc1[2]}]
        return {"focal_px": f, "lens_height_cm": lh1, "offset_cm": None, "photos": photos, "n_photos": 1,
                "width_px": int(w), "height_px": int(h)}
    Hm2, w2, h2, sc2 = _photo(m2)
    if (int(w2), int(h2)) != (int(w), int(h)):
        raise ValueError("Las dos fotos deben tener el mismo tamaño ({}×{} y {}×{} px): misma cámara y misma "
                         "configuración.".format(int(w), int(h), int(w2), int(h2)))
    H1, H2 = float(m1["height_cm"]), float(m2["height_cm"])
    if abs(H2 - H1) < MIN_HEIGHT_DIFF_CM:
        raise ValueError("Las alturas difieren {:.1f} cm: se necesitan al menos {:g} cm (mejor 40–60 cm) para que "
                         "el error de los clics no se multiplique.".format(abs(H2 - H1), MIN_HEIGHT_DIFF_CM))
    f = sc1[2] * H1
    for _ in range(50):
        h1 = plane_pose(Hm1, f, w, h)[0]
        h2 = plane_pose(Hm2, f, w, h)[0]
        if (h2 - h1) * (H2 - H1) <= 0:
            raise ValueError("La foto más alta muestra el rectángulo más grande que la más baja: revise las alturas "
                             "y las esquinas marcadas.")
        f_new = f * (H2 - H1) / (h2 - h1)
        if abs(f_new - f) < 1e-7 * f:
            f = f_new
            break
        f = f_new
    lh1, t1 = plane_pose(Hm1, f, w, h)
    lh2, t2 = plane_pose(Hm2, f, w, h)
    offset = lh1 - H1
    photos = [{"height_cm": H1, "lens_height_cm": lh1, "tilt_deg": t1,
               "scale_x": sc1[0], "scale_y": sc1[1], "scale_px_cm": sc1[2]},
              {"height_cm": H2, "lens_height_cm": lh2, "tilt_deg": t2,
               "scale_x": sc2[0], "scale_y": sc2[1], "scale_px_cm": sc2[2]}]
    return {"focal_px": f, "lens_height_cm": lh1, "offset_cm": offset, "photos": photos, "n_photos": 2,
            "width_px": int(w), "height_px": int(h)}


def equivalent_focal_mm(f_px, width_px, height_px):
    """Focal equivalente de 35 mm por la diagonal (convención del EXIF)."""
    return float(f_px) * 43.27 / math.hypot(width_px, height_px)


def equivalent_circle(res, side1_cm):
    """(D cm, H cm, diámetro en px nativos) del círculo equivalente: D = lado 1, H = altura real del lente."""
    D = float(side1_cm)
    H = float(res["lens_height_cm"])
    return D, H, res["focal_px"] * D / H


def summary_lines(res):
    """Líneas en español para el registro y la ventana."""
    out = ["Focal f = {:.1f} px en {}×{} px (equivalente a {:.1f} mm en 35 mm); campo de visión {:.1f}° × {:.1f}°."
           .format(res["focal_px"], res["width_px"], res["height_px"],
                   equivalent_focal_mm(res["focal_px"], res["width_px"], res["height_px"]),
                   2 * math.degrees(math.atan(res["width_px"] / 2.0 / res["focal_px"])),
                   2 * math.degrees(math.atan(res["height_px"] / 2.0 / res["focal_px"])))]
    for i, p in enumerate(res["photos"], 1):
        out.append("Foto {}: altura medida {:.1f} cm; lente a {:.1f} cm; escala en el centro {:.2f} px/cm; "
                   "inclinación de la cámara {:.1f}°.".format(i, p["height_cm"], p["lens_height_cm"],
                                                              p["scale_px_cm"], p["tilt_deg"]))
    if res["offset_cm"] is not None:
        out.append("El lente está {:.1f} cm {} del punto desde el que se midieron las alturas.".format(
            abs(res["offset_cm"]), "por encima" if res["offset_cm"] > 0 else "por debajo"))
    else:
        out.append("Con una foto, f depende de la altura medida: 2 cm de error en H cambian f un 2 %. Con dos "
                   "fotos a dos alturas el error del punto de medición se cancela.")
    for i, p in enumerate(res["photos"], 1):
        if p["tilt_deg"] > TILT_WARN_DEG:
            out.append("Aviso: la cámara de la foto {} estaba inclinada {:.1f}° (la calibración lo corrige, pero "
                       "al muestrear la foto entera nivele el teléfono).".format(i, p["tilt_deg"]))
    return out
