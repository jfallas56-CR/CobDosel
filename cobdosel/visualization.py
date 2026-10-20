"""
Módulo de visualización de CobDosel.

v0.11.0 (CobDosel):
- render_glama_rings(): vista «Anillos cenitales» legible en pantalla y en el informe:
  anillos a intervalos fijos de ángulo cenital (5° o 10°) con etiqueta en grados y trazo doble
  negro/blanco, cielo clasificado en naranja, zona fuera de la máscara en verde azulado con
  líneas radiales (como la app), contorno de la máscara (polígono si hay direcciones),
  sectores de acimut opcionales, marca de la dirección 1 y leyenda. Grosor de línea y letra
  proporcionales al tamaño final de la imagen.
- render_threshold_overlay clasifica con «≥ nivel de corte», igual que el análisis.

v0.10.0 (2026-10-17):
- Máscaras binarias redimensionadas con NEAREST (fiel a la clasificación analizada).
- Excepciones registradas con logging en lugar de silenciadas.

v0.9.0:
- Usa load_oriented_rgb_image para respetar siempre la orientación EXIF.
- Escala automáticamente la calibración y center_xy a la resolución de la imagen renderizada.
- Calcula los radios de los anillos cenitales mediante zenith_to_pixel_radius() para
  soportar con precisión todas las proyecciones (polar, equisólida, ortográfica,
  estereográfica, rectilínea y angular).
- render_threshold_overlay usa extract_channel(..., channel_mode) para coincidir
  exactamente con el canal de color seleccionado en el análisis.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

import os
import math
import logging
import tempfile

from PIL import Image, ImageDraw, ImageFont
import numpy as np

try:
    from scipy import ndimage
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from .exif_gps import load_oriented_rgb_image
from .lens_calibration import (
    zenith_to_pixel_radius,
    pixel_radius_to_zenith,
    scale_calibration_to_image,
)
from .canopy_analysis import extract_channel

_LOG = logging.getLogger("CobDosel")


# Colores de los anillos (trazo)
RING_COLORS = [
    (220, 60, 60),     # Rojo
    (230, 140, 30),    # Naranja
    (230, 200, 30),    # Amarillo
    (60, 180, 60),     # Verde
    (30, 120, 200),    # Azul
    (150, 60, 180),    # Púrpura
    (200, 60, 150),    # Magenta
    (60, 180, 180),    # Cian
    (120, 120, 120),   # Gris
    (30, 30, 30),      # Gris oscuro
]

TEXT_COLOR = (255, 255, 255)
TEXT_BG = (0, 0, 0)
CENTER_COLOR = (255, 0, 0)

# Superposición de cielo estilo GLAMA (naranja)
SKY_OVERLAY_DEFAULT_COLOR = (255, 140, 40)
SKY_OVERLAY_DEFAULT_ALPHA = 0.65


def _load_font(size):
    for name in (
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "arial.ttf",
        "Arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError as e:
            _LOG.debug("[_load_font] %s: %s", name, e)
            continue
    return ImageFont.load_default()


def _draw_crosshairs(draw, cx, cy, arm=20, color=(255, 0, 0), width=2):
    draw.line([(cx - arm, cy), (cx + arm, cy)], fill=color, width=width)
    draw.line([(cx, cy - arm), (cx, cy + arm)], fill=color, width=width)


def _cover_to_color(cover_pct):
    if cover_pct is None:
        return (128, 128, 128, 60)
    c = max(0.0, min(100.0, float(cover_pct))) / 100.0
    if c < 0.5:
        t = c / 0.5
        r = 255
        g = int(80 + (220 - 80) * t)
        b = int(80 + (60 - 80) * t)
    else:
        t = (c - 0.5) / 0.5
        r = int(255 + (60 - 255) * t)
        g = int(220 + (180 - 220) * t)
        b = 60
    return (r, g, b, 90)


def _draw_text_box(draw, cx, cy, text, font, bg_color, text_color,
                   padding=4):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
    except Exception:
        w = len(text) * 8
        h = 14

    box = [
        cx - w / 2 - padding,
        cy - h / 2 - padding,
        cx + w / 2 + padding,
        cy + h / 2 + padding,
    ]
    draw.rectangle(box, fill=bg_color)
    draw.text((cx - w / 2, cy - h / 2), text, fill=text_color, font=font)


def _draw_legend(img, ring_metrics, font_small, font_bold):
    draw = ImageDraw.Draw(img)
    W, H = img.size

    lines = ["Anillos de análisis CobDosel"]
    for i, m in enumerate(ring_metrics):
        cover = m.get("cover_pct")
        if cover is not None:
            lines.append("Anillo {}: {:.1f}% cob.".format(i + 1, cover))

    line_h = max(20, int(min(W, H) / 48))
    box_w = max(250, int(min(W, H) / 4))
    box_h = line_h * (len(lines) + 1)

    x0 = W - box_w - 20
    y0 = 20
    if x0 < 0:
        x0 = 10
    if y0 + box_h > H:
        y0 = max(10, H - box_h - 20)

    draw.rectangle(
        [x0, y0, x0 + box_w, y0 + box_h],
        fill=(0, 0, 0),
        outline=(255, 255, 255),
        width=1,
    )

    y = y0 + 8
    for i, line in enumerate(lines):
        font = font_bold if i == 0 else font_small
        color = (255, 255, 255) if i == 0 else (220, 220, 220)
        draw.text((x0 + 10, y), line, fill=color, font=font)
        y += line_h


def _ring_radius_px(angle_deg, scaled_cal, fallback_r_half, theta_max_deg):
    try:
        r = float(zenith_to_pixel_radius(angle_deg, scaled_cal))
        if math.isfinite(r) and r >= 0:
            return r
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as e:
        _LOG.debug("[_ring_radius_px] %s", e)
    if theta_max_deg > 0:
        return fallback_r_half * (float(angle_deg) / float(theta_max_deg))
    return fallback_r_half


def draw_zenith_rings(image, calibration, ring_boundaries, ring_metrics,
                      center_xy=None,
                      show_labels=True,
                      show_center=True,
                      show_crosshairs=True,
                      show_radial_spokes=True,
                      show_cover_fill=False,
                      show_sky_overlay=False,
                      sky_mask=None,
                      sky_overlay_color=SKY_OVERLAY_DEFAULT_COLOR,
                      sky_overlay_alpha=SKY_OVERLAY_DEFAULT_ALPHA,
                      crop_to_circle=False,
                      line_width=3,
                      font_size=None):
    """Dibuja los anillos cenitales concéntricos sobre una copia de la imagen."""
    img = image.copy().convert("RGB")
    W, H = img.size

    scaled_cal = scale_calibration_to_image(calibration, W, H)

    if center_xy is not None:
        cal_w = calibration.get("image_width_px") or W
        cal_h = calibration.get("image_height_px") or H
        cx = float(center_xy[0]) * (float(W) / float(cal_w))
        cy = float(center_xy[1]) * (float(H) / float(cal_h))
    elif scaled_cal.get("center_xy") is not None:
        cx, cy = float(scaled_cal["center_xy"][0]), float(scaled_cal["center_xy"][1])
    else:
        cx, cy = W / 2.0, H / 2.0

    r_image_half = scaled_cal.get("r_image_half_px") or (min(W, H) / 2.0)
    theta_max_deg = scaled_cal.get("max_zenith_deg", 90.0)

    if font_size is None:
        font_size = max(12, int(min(W, H) / 55))
    font = _load_font(font_size)
    font_small = _load_font(max(10, font_size - 4))

    # Opcional: superposición de píxeles de cielo
    if show_sky_overlay and sky_mask is not None:
        mask = sky_mask
        if mask.shape[0] != H or mask.shape[1] != W:
            mask_img = Image.fromarray((mask * 255).astype("uint8"), "L")
            mask_img = mask_img.resize((W, H), Image.NEAREST)
            mask = np.array(mask_img) > 127

        img_np = np.array(img).astype(np.float32)
        overlay_rgb = np.array(sky_overlay_color, dtype=np.float32)
        a = float(sky_overlay_alpha)
        for c in range(3):
            img_np[:, :, c] = np.where(
                mask,
                img_np[:, :, c] * (1.0 - a) + overlay_rgb[c] * a,
                img_np[:, :, c],
            )
        img = Image.fromarray(img_np.astype("uint8"), "RGB")

    outer_radius_px = _ring_radius_px(
        ring_boundaries[-1][1], scaled_cal, r_image_half, theta_max_deg
    )

    # Opcional: recorte circular
    if crop_to_circle:
        mask = Image.new("L", (W, H), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse(
            [cx - outer_radius_px, cy - outer_radius_px,
             cx + outer_radius_px, cy + outer_radius_px],
            fill=255,
        )
        black = Image.new("RGB", (W, H), (0, 0, 0))
        img = Image.composite(img, black, mask)

    # Opcional: relleno de anillos por % de cobertura
    if show_cover_fill:
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for i, (lo, hi) in enumerate(ring_boundaries):
            outer_r = _ring_radius_px(hi, scaled_cal, r_image_half, theta_max_deg)
            inner_r = _ring_radius_px(lo, scaled_cal, r_image_half, theta_max_deg)
            if outer_r < 1:
                continue

            metrics = ring_metrics[i] if i < len(ring_metrics) else {}
            cover_pct = metrics.get("cover_pct")
            color = _cover_to_color(cover_pct)

            ring_mask = Image.new("L", (W, H), 0)
            ring_mask_draw = ImageDraw.Draw(ring_mask)
            ring_mask_draw.ellipse(
                [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r],
                fill=255,
            )
            if inner_r > 0.5:
                ring_mask_draw.ellipse(
                    [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
                    fill=0,
                )
            fill_layer = Image.new("RGBA", (W, H), color)
            overlay.paste(fill_layer, (0, 0), ring_mask)

        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    if show_radial_spokes:
        n_spokes = 8
        for k in range(n_spokes):
            angle = 2.0 * math.pi * k / n_spokes - math.pi / 2.0
            x_end = cx + outer_radius_px * math.cos(angle)
            y_end = cy + outer_radius_px * math.sin(angle)
            draw.line(
                [(cx, cy), (x_end, y_end)],
                fill=(200, 200, 200),
                width=1,
            )

    for i, (lo, hi) in enumerate(ring_boundaries):
        outer_r = _ring_radius_px(hi, scaled_cal, r_image_half, theta_max_deg)
        if outer_r < 1:
            continue
        color = RING_COLORS[i % len(RING_COLORS)]
        draw.ellipse(
            [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r],
            outline=color,
            width=line_width,
        )

        if show_labels:
            label_angle = math.radians(-45.0)
            lx = cx + outer_r * math.cos(label_angle)
            ly = cy + outer_r * math.sin(label_angle)

            if 0 <= lx < W and 0 <= ly < H:
                metrics = ring_metrics[i] if i < len(ring_metrics) else {}
                cover = metrics.get("cover_pct")
                if cover is not None:
                    text = "A{} {:.0f}%".format(i + 1, cover)
                else:
                    text = "A{}".format(i + 1)
                _draw_text_box(draw, lx, ly, text, font, TEXT_BG, TEXT_COLOR)

    if show_center:
        marker_r = max(6, line_width * 2)
        draw.ellipse(
            [cx - marker_r, cy - marker_r, cx + marker_r, cy + marker_r],
            fill=(255, 255, 255), outline=(0, 0, 0), width=2,
        )
        inner_r = max(2, marker_r // 3)
        draw.ellipse(
            [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
            fill=CENTER_COLOR,
        )

    if show_crosshairs:
        arm = r_image_half * 0.08
        _draw_crosshairs(draw, cx, cy, arm=arm, color=(255, 0, 0), width=2)

    _draw_legend(img, ring_metrics, font_small, font)

    return img


def render_glama_style(image_path, calibration, ring_boundaries, ring_metrics,
                       center_xy=None,
                       output_path=None,
                       sky_mask=None,
                       show_sky_overlay=False,
                       show_cover_fill=False,
                       crop_to_circle=True,
                       max_dim=None):
    """Renderiza una visualización con anillos cenitales al estilo GLAMA."""
    img, _, _ = load_oriented_rgb_image(image_path, max_dim=max_dim)
    rendered = draw_zenith_rings(
        img, calibration, ring_boundaries, ring_metrics,
        center_xy=center_xy,
        show_labels=True,
        show_center=True,
        show_crosshairs=True,
        show_radial_spokes=True,
        show_cover_fill=show_cover_fill,
        show_sky_overlay=show_sky_overlay,
        sky_mask=sky_mask,
        crop_to_circle=crop_to_circle,
    )

    if output_path is None:
        fd, output_path = tempfile.mkstemp(
            suffix=".png", prefix="cobdosel_viz_"
        )
        os.close(fd)

    rendered.save(output_path, "PNG")
    return output_path


def render_threshold_overlay(image_path, sky_mask=None,
                             threshold=None,
                             sky_is_bright=True,
                             apply_cleanup=True,
                             channel_mode="blue_red",
                             output_path=None,
                             mode="overlay",
                             sky_color=SKY_OVERLAY_DEFAULT_COLOR,
                             canopy_color=None,
                             alpha=SKY_OVERLAY_DEFAULT_ALPHA,
                             max_dim=None,
                             area_mask=None):
    """
    Renderiza la fotografía con una superposición de color mostrando la
    clasificación cielo/dosel en el canal seleccionado.

    area_mask (0.14.15): área analizada (True = dentro de la máscara de horizonte). Lo que queda
    fuera se tiñe de verde azulado y su borde se dibuja en amarillo, como en la vista de anillos;
    el cielo fuera de la máscara no se tiñe de naranja porque no entra en los resultados.
    """
    img, _, _ = load_oriented_rgb_image(image_path, max_dim=max_dim)
    W, H = img.size

    if threshold is not None:
        arr_rgb = np.array(img)
        gray_full = extract_channel(arr_rgb, channel_mode=channel_mode)

        # Mismo criterio que el análisis (threshold_image): claro si valor ≥ nivel de corte
        if sky_is_bright:
            mask = gray_full >= threshold
        else:
            mask = gray_full < threshold

        if apply_cleanup and HAS_SCIPY:
            mask = ndimage.binary_opening(mask, iterations=1)
            mask = ndimage.binary_closing(mask, iterations=1)

    elif sky_mask is not None:
        mask = sky_mask
        if mask.shape[0] != H or mask.shape[1] != W:
            mask_img = Image.fromarray((mask * 255).astype("uint8"), "L")
            mask_img = mask_img.resize((W, H), Image.NEAREST)
            mask = np.array(mask_img) > 127

    else:
        raise ValueError(
            "render_threshold_overlay requiere 'threshold' o 'sky_mask'."
        )

    if area_mask is not None:
        area_mask = _fit_mask(area_mask, W, H)
        mask = mask & area_mask        # el cielo fuera del área analizada no se tiñe

    if mode == "solid":
        if canopy_color is None:
            canopy_color = (40, 40, 40)
        result_np = np.zeros((H, W, 3), dtype=np.uint8)
        result_np[mask] = sky_color
        result_np[~mask] = canopy_color
        result = Image.fromarray(result_np, "RGB")

    elif mode == "soft":
        img_np = np.array(img).astype(np.float32)
        overlay = np.zeros_like(img_np)
        overlay[:, :] = (80, 200, 255)
        a = 0.35
        for c in range(3):
            img_np[:, :, c] = np.where(
                mask,
                img_np[:, :, c] * (1.0 - a) + overlay[:, :, c] * a,
                img_np[:, :, c],
            )
        result = Image.fromarray(img_np.astype("uint8"), "RGB")

    else:  # "overlay"
        img_np = np.array(img).astype(np.float32)
        sky_rgb = np.array(sky_color, dtype=np.float32)
        a = float(alpha)
        for c in range(3):
            img_np[:, :, c] = np.where(
                mask,
                img_np[:, :, c] * (1.0 - a) + sky_rgb[c] * a,
                img_np[:, :, c],
            )
        result = Image.fromarray(img_np.astype("uint8"), "RGB")

    if area_mask is not None:
        result = _apply_area_mask(result, area_mask)

    if output_path is None:
        fd, output_path = tempfile.mkstemp(
            suffix=".png", prefix="cobdosel_thr_"
        )
        os.close(fd)

    result.save(output_path, "PNG")
    return output_path


def _fit_mask(mask, W, H):
    """Máscara booleana al tamaño (W, H) (vecino más próximo)."""
    m = np.asarray(mask, dtype=bool)
    if m.shape != (H, W):
        m = np.array(Image.fromarray(m.astype("uint8") * 255, "L").resize((W, H), Image.NEAREST)) > 127
    return m


def _apply_area_mask(result, area_mask, alpha=0.55):
    """Tiñe de verde azulado lo que queda fuera del área analizada y dibuja su borde en amarillo."""
    W, H = result.size
    area = _fit_mask(area_mask, W, H)
    if area.all():
        return result
    img_np = np.array(result).astype(np.float32)
    outside = ~area
    teal = np.array(GLAMA_TEAL, dtype=np.float32)
    for c in range(3):
        img_np[:, :, c] = np.where(outside, img_np[:, :, c] * (1.0 - alpha) + teal[c] * alpha, img_np[:, :, c])
    # Borde: píxeles del área con algún vecino fuera (grosor ~2 px por cada 1000 px)
    edge = np.zeros_like(area)
    k = max(1, int(round(max(W, H) / 1000.0)))
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            if dx == 0 and dy == 0:
                continue
            sh = np.roll(np.roll(outside, dy, axis=0), dx, axis=1)
            edge |= area & sh
    img_np[edge] = MASK_EDGE_COLOR
    return Image.fromarray(np.clip(img_np, 0, 255).astype("uint8"), "RGB")


# ======================================================================
# Vista «Anillos cenitales» (v0.11.0)
# ======================================================================
GLAMA_TEAL = (54, 176, 170)          # fondo de la app fuera de la máscara
GLAMA_TEAL_LINE = (30, 120, 116)     # líneas radiales de la app
MASK_EDGE_COLOR = (255, 230, 0)      # contorno de la máscara de horizonte


RING_STEPS_DEG = (1.0, 2.0, 2.5, 5.0, 10.0, 15.0)


def auto_ring_interval(zenith_limit_deg, min_rings=4):
    """
    Intervalo de anillos de referencia: el mayor de RING_STEPS_DEG que deja al menos min_rings
    anillos dentro de zenith_limit_deg. zenith_limit_deg debe ser el cenit visible (el menor entre
    la máscara y la esquina de la foto): con lente regular la foto puede llegar solo a ~20°.
    """
    zl = float(zenith_limit_deg)
    for step in reversed(RING_STEPS_DEG):
        if math.floor(zl / step + 1e-9) >= min_rings:
            return step
    return RING_STEPS_DEG[0]


def _zenith_limit_grid(az_deg, zenith_max_deg, horizon_angles):
    if horizon_angles:
        from .glama_engine import horizon_zenith_limit
        return horizon_zenith_limit(az_deg, horizon_angles)
    return np.full(np.shape(az_deg), float(zenith_max_deg))


def render_glama_rings(image_path, calibration, center_xy=None, zenith_max_deg=45.0,
                       horizon_angles=None, sky_mask=None, ring_interval_deg=None,
                       n_sectors=0, show_sky_overlay=True, show_outside_mask=True,
                       legend_lines=None, output_path=None, max_dim=1600,
                       image_direction_deg=None):
    """
    Vista «Anillos cenitales». Devuelve la ruta del PNG generado.

    zenith_max_deg / horizon_angles: máscara de horizonte (única o por direcciones, en grados
    sobre el horizonte; dirección 1 arriba, sentido horario, como GLAMA).
    sky_mask: máscara de cielo del análisis (se reescala con NEAREST).
    n_sectors: 0 = sin sectores; 4, 8, 12 o 16 = líneas de sector de acimut.
    legend_lines: líneas de texto extra para la leyenda (p. ej. CaCo y nivel de corte).
    image_direction_deg: rumbo EXIF (GPSImgDirection) para anotarlo en la leyenda.
    """
    img, _, _ = load_oriented_rgb_image(image_path, max_dim=max_dim)
    img = img.convert("RGB")
    W, H = img.size
    cal = scale_calibration_to_image(calibration, W, H)
    if center_xy is not None:
        cal_w = calibration.get("image_width_px") or W
        cal_h = calibration.get("image_height_px") or H
        cx = float(center_xy[0]) * W / float(cal_w)
        cy = float(center_xy[1]) * H / float(cal_h)
    elif cal.get("center_xy") is not None:
        cx, cy = float(cal["center_xy"][0]), float(cal["center_xy"][1])
    else:
        cx, cy = W / 2.0, H / 2.0

    yy, xx = np.ogrid[0:H, 0:W]
    dx = (xx - cx).astype(np.float32)
    dy = (yy - cy).astype(np.float32)
    r = np.sqrt(dx * dx + dy * dy)
    zen = np.asarray(pixel_radius_to_zenith(r, cal), dtype=np.float32)
    az = np.mod(np.degrees(np.arctan2(dx, -dy)), 360.0)
    zlim = _zenith_limit_grid(az, zenith_max_deg, horizon_angles)
    masked = zen > zlim + 1e-6

    arr = np.asarray(img).astype(np.float32)
    if show_sky_overlay and sky_mask is not None:
        m = np.asarray(sky_mask)
        if m.shape[0] != H or m.shape[1] != W:
            m = np.asarray(Image.fromarray((m.astype(np.uint8) * 255), "L").resize(
                (W, H), Image.NEAREST)) > 127
        sky = m & ~masked
        a = SKY_OVERLAY_DEFAULT_ALPHA
        for c in range(3):
            arr[:, :, c] = np.where(sky, arr[:, :, c] * (1 - a) + SKY_OVERLAY_DEFAULT_COLOR[c] * a,
                                    arr[:, :, c])
    if show_outside_mask:
        a = 0.85
        for c in range(3):
            arr[:, :, c] = np.where(masked, arr[:, :, c] * (1 - a) + GLAMA_TEAL[c] * a, arr[:, :, c])
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

    lw = max(3, int(round(min(W, H) / 260.0)))
    font = _load_font(max(12, int(min(W, H) / 45)))
    font_small = _load_font(max(10, int(min(W, H) / 60)))
    diag = math.hypot(W, H)

    # Líneas radiales de la app fuera de la máscara (cada 3°)
    if show_outside_mask and masked.any():
        spokes = Image.new("L", (W, H), 0)
        sd = ImageDraw.Draw(spokes)
        for k in range(120):
            ang = math.radians(k * 3.0)
            sd.line([(cx, cy), (cx + diag * math.sin(ang), cy - diag * math.cos(ang))],
                    fill=255, width=max(1, lw // 2))
        sp = (np.asarray(spokes) > 0) & masked
        o = np.asarray(out).copy()
        o[sp] = GLAMA_TEAL_LINE
        out = Image.fromarray(o, "RGB")

    draw = ImageDraw.Draw(out)

    def _rad(z):
        return float(zenith_to_pixel_radius(float(z), cal))

    zmax_all = float(np.max(_zenith_limit_grid(np.arange(0, 360, 1.0), zenith_max_deg,
                                               horizon_angles)))
    # Cenit que alcanza la foto: esquina más lejana y borde más cercano (lente regular)
    corner_r = max(math.hypot(px - cx, py - cy) for px in (0.0, W) for py in (0.0, H))
    edge_r = min(cx, W - cx, cy, H - cy)
    z_corner = float(pixel_radius_to_zenith(np.array([corner_r]), cal)[0])
    z_edge = float(pixel_radius_to_zenith(np.array([max(edge_r, 0.0)]), cal)[0])
    z_vis = min(zmax_all, z_corner)
    step = ring_interval_deg or auto_ring_interval(z_vis)
    margin = 6.0
    z = step
    n_drawn = 0
    while z < zmax_all - 1e-6 and z <= z_corner + 1e-6:
        rr = _rad(z)
        box = [cx - rr, cy - rr, cx + rr, cy + rr]
        draw.ellipse(box, outline=(0, 0, 0), width=lw + 3)
        draw.ellipse(box, outline=(255, 255, 255), width=lw)
        n_drawn += 1
        # Etiqueta: junto al eje derecho (8° por debajo) o, si queda fuera, el primer ángulo visible
        for off in [8.0] + [8.0 + k * 5.0 for k in range(1, 72)]:
            lx = cx + rr * math.cos(math.radians(off))
            ly = cy + rr * math.sin(math.radians(off))
            if margin * 4 <= lx < W - margin * 4 and margin * 3 <= ly < H - margin * 3:
                _draw_text_box(draw, lx, ly, "{:g}°".format(z), font_small, TEXT_BG, TEXT_COLOR)
                break
        z += step

    # Contorno de la máscara de horizonte (círculo o polígono por direcciones)
    pts = []
    for a_deg in np.arange(0.0, 360.0 + 0.5, 1.0):
        zl = float(_zenith_limit_grid(np.array([a_deg]), zenith_max_deg, horizon_angles)[0])
        rr = _rad(zl)
        pts.append((cx + rr * math.sin(math.radians(a_deg)), cy - rr * math.cos(math.radians(a_deg))))
    draw.line(pts, fill=(0, 0, 0), width=lw + 4)
    draw.line(pts, fill=MASK_EDGE_COLOR, width=lw + 1)

    # Sectores de acimut (dirección 1 = arriba, sentido horario)
    if n_sectors and n_sectors > 1:
        for k in range(int(n_sectors)):
            a_deg = k * 360.0 / n_sectors
            zl = float(_zenith_limit_grid(np.array([a_deg]), zenith_max_deg, horizon_angles)[0])
            rr = _rad(zl)
            x2 = cx + rr * math.sin(math.radians(a_deg))
            y2 = cy - rr * math.cos(math.radians(a_deg))
            draw.line([(cx, cy), (x2, y2)], fill=(0, 0, 0), width=lw + 2)
            draw.line([(cx, cy), (x2, y2)], fill=(255, 255, 255), width=max(1, lw - 1))
            amid = math.radians(a_deg + 180.0 / n_sectors)
            tx = cx + 0.55 * rr * math.sin(amid)
            ty = cy - 0.55 * rr * math.cos(amid)
            if 0 <= tx < W and 0 <= ty < H:
                _draw_text_box(draw, tx, ty, "S{}".format(k + 1), font_small, TEXT_BG, TEXT_COLOR)

    # Marca de la dirección 1 (arriba) y centro
    r_top = _rad(zmax_all)
    ty = max(14.0, cy - r_top - 18.0)
    _draw_text_box(draw, cx, ty, "1 ▲", font_small, (40, 40, 40), (255, 230, 0))
    arm = max(10.0, min(W, H) * 0.03)
    draw.line([(cx - arm, cy), (cx + arm, cy)], fill=(255, 0, 0), width=lw)
    draw.line([(cx, cy - arm), (cx, cy + arm)], fill=(255, 0, 0), width=lw)

    # Leyenda
    lines = ["CobDosel — Anillos cenitales",
             "Anillos cada {:g}° de cenit".format(step),
             "La foto llega a {:.1f}° del cenit (borde) y {:.1f}° (esquina)".format(z_edge, z_corner)]
    if horizon_angles:
        lines.append("Máscara: {} direcciones ({})".format(
            len(horizon_angles), "; ".join("{:g}°".format(h) for h in horizon_angles)))
    else:
        lines.append("Máscara: {:.1f}° sobre el horizonte (cenit {:.1f}°)".format(
            90.0 - float(zenith_max_deg), float(zenith_max_deg)))
    if zmax_all > z_corner + 1e-6:
        # Sin «⚠»: la fuente del dibujo no siempre tiene ese símbolo (se veía como un cuadro)
        lines.append("Aviso: el contorno de la máscara ({:.1f}° de cenit) queda fuera de la foto".format(zmax_all))
        lines.append("Máscara ≥ {:.1f}° sobre el horizonte para quedar dentro".format(90.0 - z_edge))
    elif zmax_all > z_edge + 1e-6:
        lines.append("Aviso: la máscara sale de la foto en los bordes cortos")
        lines.append("Máscara ≥ {:.1f}° sobre el horizonte para quedar dentro".format(90.0 - z_edge))
    if show_sky_overlay and sky_mask is not None:
        lines.append("Naranja = cielo (claro); verde azulado = enmascarado")
    if image_direction_deg is not None:
        lines.append("Rumbo EXIF: {:.0f}° (borde superior)".format(float(image_direction_deg)))
    for extra in (legend_lines or []):
        lines.append(str(extra))
    line_h = int(font_small.size * 1.45) if hasattr(font_small, "size") else 16
    try:
        box_w = max(int(draw.textlength(t, font=font_small if i else font)) for i, t in enumerate(lines)) + 20
    except AttributeError:
        box_w = max(len(t) for t in lines) * 8 + 20
    box_h = line_h * len(lines) + 14
    x0, y0 = 10, 10
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=(0, 0, 0), outline=(255, 255, 255))
    y = y0 + 7
    for i, t in enumerate(lines):
        draw.text((x0 + 10, y), t, fill=(255, 255, 255) if i == 0 else (225, 225, 225),
                  font=font if i == 0 else font_small)
        y += line_h

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".png", prefix="cobdosel_anillos_")
        os.close(fd)
    out.save(output_path, "PNG")
    return output_path
