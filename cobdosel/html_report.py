"""
Generador de informes HTML autocontenidos para CobDosel.

Incluye:
- Nombre y metadatos EXIF/GPS de la imagen
- Parámetros completos de calibración del lente y máscara de horizonte artificial
- Todos los indicadores reportados por GLAMA (Tichý 2016, https://doi.org/10.1111/jvs.12350)
- Tabla desglosada por anillos cenitales y LAI efectivo (Miller 1967)
- Vistas previas integradas (Base64 PNG) de anillos GLAMA y máscara de umbral
- Créditos: Jorge Fallas (jfallas56@gmail.com)

Historial:
- 0.11.0 (CobDosel): vista «Anillos cenitales» nueva (anillos visibles con etiquetas en
  grados, cielo en naranja, máscara sombreada, sectores); el CaCo se destaca como valor de
  cobertura del dosel; se informan R y su equivalente en GLAMA, la medición del círculo, el %
  visible del círculo de análisis, la orientación y el rumbo EXIF, los avisos del análisis y
  la tabla de fracción de claros por sector.
- 0.10.0 (2026-10-17): la imagen de clasificación usa la máscara analizada (no se
  re-umbraliza); fallos al generar imágenes se registran y se avisan en el informe;
  separador de miles con espacio; notas sobre LAI, fracción de claros y CaCo.
"""

import os
import io
import html
import base64
import logging
import datetime

from .canopy_analysis import (
    classify_measurement_type,
    compute_hemisphere_fraction,
    CHANNEL_LABELS,
)
from .visualization import (
    render_glama_rings,
    render_threshold_overlay,
)
from PIL import Image

from ._version import VERSION, fmt_int

_LOG = logging.getLogger("CobDosel")


def _file_to_data_uri(img_path, max_thumb_dim=900):
    """Convierte un archivo de imagen en un data URI PNG Base64 redimensionado."""
    try:
        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        if max(w, h) > max_thumb_dim:
            scale = float(max_thumb_dim) / float(max(w, h))
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.LANCZOS,
            )
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return "data:image/png;base64," + b64
    except Exception as e:
        _LOG.warning("[_file_to_data_uri] %s: %s", img_path, e)
        return None


def generate_html_report(results, output_path, include_images=True, log=None):
    """
    Genera un archivo HTML con los parámetros de calibración, nombre de la imagen
    y todos los resultados de CobDosel (basado en Tichý 2016).

    log: función opcional log(mensaje, nivel) para registrar avisos en el diálogo.
    Devuelve la ruta del informe. Los avisos quedan en results["report_warnings"].
    """
    warnings = []

    def _warn(msg):
        warnings.append(msg)
        _LOG.warning(msg)
        if callable(log):
            log(msg, "WARN")

    image_path = results.get("image_path", "")
    image_name = os.path.basename(image_path) if image_path else "Sin nombre"
    exif = results.get("exif") or {}
    cal = results.get("calibration") or {}
    cover = results.get("cover") or {}
    metrics = results.get("metrics") or {}
    lai = results.get("lai") or {}
    boundaries = results.get("ring_boundaries") or []

    half_fov = float(cal.get("max_zenith_deg", 90.0))
    full_fov = float(cal.get("full_fov_deg", 2.0 * half_fov))
    zenith_max_deg = float(results.get("zenith_max_deg", half_fov))
    horizon_mask_deg = float(results.get("horizon_mask_deg", max(0.0, 90.0 - zenith_max_deg)))

    hemi_frac = float(
        metrics.get(
            "hemisphere_fraction_pct",
            compute_hemisphere_fraction(half_fov),
        )
    )
    analyzed_hemi_frac = compute_hemisphere_fraction(zenith_max_deg)
    meas = classify_measurement_type(zenith_max_deg)

    channel_mode = results.get("channel_mode", "blue_red")
    channel_label = CHANNEL_LABELS.get(channel_mode, str(channel_mode))
    threshold = int(results.get("threshold", metrics.get("cut_level", 128)))
    sky_is_bright = bool(results.get("sky_is_bright", True))
    apply_cleanup = bool(results.get("apply_cleanup", True))

    total_circle_px = int(
        metrics.get(
            "total_pixels_in_circle",
            cover.get("total_pixels_in_circle", 0),
        )
    )
    total_frame_px = int(
        metrics.get(
            "total_pixels_in_frame",
            cover.get("total_pixels_in_frame", 0),
        )
    )
    light_px = int(
        metrics.get("light_pixels", cover.get("light_pixels", 0))
    )
    dark_px = int(
        metrics.get("dark_pixels", cover.get("dark_pixels", 0))
    )

    gap_fraction_pct = float(metrics.get("gap_fraction_pct", 0.0))
    canopy_openness_pct = float(
        metrics.get(
            "canopy_openness_pct",
            100.0 - float(metrics.get("canopy_closure_pct", 0.0)),
        )
    )
    canopy_closure_pct = float(metrics.get("canopy_closure_pct", 0.0))
    caco_index_pct = float(
        metrics.get(
            "canopy_cover_index_pct",
            metrics.get("canopy_cover_pct", 0.0),
        )
    )
    mod_caco_index_pct = float(
        metrics.get("spherical_cover_pct", metrics.get("modified_caco_index_pct", caco_index_pct))
    )
    lai_eff = float(lai.get("lai_effective", 0.0))
    lai_zmax = float(lai.get("lai_zenith_max_deg", zenith_max_deg))
    lai_reliable = bool(lai.get("lai_reliable", True))
    lai_note = (
        "Miller (1967) normalizado al rango 0–{:.1f}° (exacto para hojas de distribución "
        "esférica){}".format(
            lai_zmax,
            "" if lai_reliable else
            ". INDICATIVO: rango cenital &lt; 45°, el LAI depende fuertemente del supuesto "
            "de distribución foliar.",
        )
    )
    gap_unmasked_pct = float(metrics.get("gap_fraction_unmasked_pct", gap_fraction_pct))
    horizon_angles = results.get("horizon_angles")
    if horizon_angles:
        mask_str = "{} direcciones: {}° sobre el horizonte (dirección 1 = arriba, horario)".format(
            len(horizon_angles), "; ".join("{:g}".format(a) for a in horizon_angles))
    else:
        mask_str = "{:.1f}° sobre el horizonte (cenit 0–{:.1f}°)".format(
            horizon_mask_deg, 90.0 - horizon_mask_deg)
    calib_formula = ("aproximada atan(D/H)/2 (calibración antigua)" if cal.get("glama_compat")
                     else "geometría exacta, atan(D/2H)")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Metadatos EXIF y GPS
    if exif.get("has_gps"):
        gps_str = "{:.6f}, {:.6f}".format(
            exif["latitude"], exif["longitude"]
        )
        if exif.get("elevation_m") is not None:
            gps_str += " ({:.1f} m s.n.m.)".format(exif["elevation_m"])
    else:
        gps_str = "No disponible en EXIF"

    capture_dt = exif.get("capture_datetime") or "No disponible"
    cam_parts = [
        p for p in (exif.get("camera_make"), exif.get("camera_model")) if p
    ]
    camera_str = " ".join(cam_parts) if cam_parts else "No especificado"

    img_w = cal.get("image_width_px") or "—"
    img_h = cal.get("image_height_px") or "—"
    orig_size = results.get("original_image_size")
    if orig_size and (orig_size[0] != img_w or orig_size[1] != img_h):
        dim_str = "{} × {} px (original: {} × {} px)".format(
            img_w, img_h, orig_size[0], orig_size[1]
        )
    else:
        dim_str = "{} × {} px".format(img_w, img_h)

    lens_type_label = (
        "Ojo de pez (circular 180°)"
        if cal.get("lens_type") == "fisheye"
        else "Lente regular (círculo de diámetro conocido)"
    )
    proj_label = cal.get("projection_label", cal.get("projection", "—"))
    focal_px_str = (
        "{:.2f} px".format(cal["focal_length_px"])
        if cal.get("focal_length_px") is not None else "—"
    )
    virt_r_str = (
        "{:.1f} px".format(cal["virtual_radius_px"])
        if cal.get("virtual_radius_px") is not None else "—"
    )
    circle_cm_str = (
        "{:.2f} cm".format(cal["circle_diameter_cm"])
        if cal.get("circle_diameter_cm") is not None else "—"
    )
    height_cm_str = (
        "{:.2f} cm".format(cal["camera_height_cm"])
        if cal.get("camera_height_cm") is not None else "—"
    )
    px_diam_str = (
        "{:.2f} px".format(cal["pixel_diameter_px"])
        if cal.get("pixel_diameter_px") is not None else "—"
    )
    theta_ref_str = (
        "{:.2f}° (semiángulo cenital: {:.2f}°)".format(
            cal["angular_size_deg"],
            cal.get("zenith_ref_deg", cal["angular_size_deg"] / 2.0),
        )
        if cal.get("angular_size_deg") is not None else "—"
    )
    center_xy = results.get("center_xy") or cal.get("center_xy")
    center_str = (
        "({:.1f}, {:.1f}) px".format(center_xy[0], center_xy[1])
        if center_xy else "Centro de la imagen"
    )

    fmax = results.get("zenith_frame_max_deg") or cal.get("max_zenith_frame_deg")
    frame_max_str = "{:.2f}°".format(fmax) if fmax else "—"
    visible_str = "{:.1f} %".format(float(results.get("circle_visible_pct", 100.0)))
    measure_str = (cal.get("measurement") or {}).get("summary") or "—"
    exif_orient_str = "{}{}".format(
        exif.get("orientation") or "—",
        " / {:.0f}° ({})".format(exif["image_direction_deg"], exif.get("image_direction_ref") or "ref. ?")
        if exif.get("image_direction_deg") is not None else "")
    geo = results.get("glama_geometry")
    geometry_banner = (
        "<div class='warn-box'><strong>Geometría de pantalla de GLAMA activada</strong> (estudio de "
        "transición): los índices reproducen la app con sus sesgos. CaCo con la geometría correcta = "
        "<strong>{:.2f}%</strong>. No use este informe para el valor oficial.</div>".format(
            geo["correct_caco_pct"]) if geo else "")
    run_warnings_html = "".join(
        "<div class='warn-box'>⚠ {}</div>".format(html.escape(w))
        for w in (results.get("run_warnings") or []) if not (geo and "Geometría de pantalla" in w))
    sectors = results.get("sectors") or []
    n_sec = int(results.get("n_sectors") or 0)
    sector_html = ""
    if sectors and n_sec > 0:
        head = "".join("<th class='num'>S{}</th>".format(k + 1) for k in range(n_sec))
        rows = []
        for i, (lo, hi) in enumerate(boundaries):
            cells = "".join(
                "<td class='num'>{}</td>".format(
                    "{:.1f}".format(sc["gap_pct"]) if sc["gap_pct"] is not None else "—")
                for sc in sectors if sc["ring"] == i + 1)
            rows.append("<tr><td>Anillo {} ({:.1f}°–{:.1f}°)</td>{}</tr>".format(i + 1, lo, hi, cells))
        sector_html = (
            "<h3 style='margin-top:18px;'>Fracción de claros (%) por anillo × sector de acimut "
            "(S1 = arriba, sentido horario)</h3><table class='data-table'><thead><tr><th>Anillo</th>"
            + head + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")

    glama_uri = None
    thr_uri = None
    if include_images and image_path and os.path.isfile(image_path):
        tmp_files = []
        try:
            p_glama = render_glama_rings(
                image_path,
                cal,
                center_xy=center_xy,
                zenith_max_deg=float(results.get("mask_zenith_deg", zenith_max_deg)),
                horizon_angles=horizon_angles,
                sky_mask=results.get("sky_mask"),
                n_sectors=int(results.get("n_sectors") or 0),
                legend_lines=["Nivel de corte: {} ({})".format(threshold, results.get("cut_method") or "manual"),
                              "CaCo: {:.2f} %".format(caco_index_pct)],
                max_dim=1200,
                image_direction_deg=exif.get("image_direction_deg"),
            )
            tmp_files.append(p_glama)
            glama_uri = _file_to_data_uri(p_glama, max_thumb_dim=850)

            analysed_mask = results.get("sky_mask")
            if analysed_mask is not None:
                # Muestra exactamente la máscara que produjo los resultados
                p_thr = render_threshold_overlay(
                    image_path, sky_mask=analysed_mask, mode="overlay", max_dim=1200,
                    area_mask=results.get("analysis_area_mask"),
                )
            else:
                p_thr = render_threshold_overlay(
                    image_path,
                    threshold=threshold,
                    sky_is_bright=sky_is_bright,
                    apply_cleanup=apply_cleanup,
                    channel_mode=channel_mode,
                    mode="overlay",
                    max_dim=1200,
                    area_mask=results.get("analysis_area_mask"),
                )
            tmp_files.append(p_thr)
            thr_uri = _file_to_data_uri(p_thr, max_thumb_dim=850)
        except Exception as e:
            _warn("No se pudieron generar las visualizaciones del informe: {}".format(e))
        finally:
            for tf in tmp_files:
                try:
                    if tf and os.path.isfile(tf):
                        os.remove(tf)
                except OSError as e:
                    _LOG.debug("[cleanup informe] %s: %s", tf, e)
        if not (glama_uri and thr_uri) and not warnings:
            _warn("El informe se generó sin una o más visualizaciones.")

    ring_rows_html = []
    for i, r in enumerate(cover.get("per_ring", [])):
        lo, hi = boundaries[i] if i < len(boundaries) else (0.0, 0.0)
        cov_s = (
            "{:.2f}%".format(r["cover_pct"])
            if r.get("cover_pct") is not None else "n/d"
        )
        gap_s = (
            "{:.2f}%".format(100.0 * r["gap_fraction"])
            if r.get("gap_fraction") is not None else "n/d"
        )
        n_px = int(r.get("n_pixels") or 0)
        n_light = int(r.get("n_light_pixels") or 0)
        n_dark = int(r.get("n_dark_pixels") or 0)
        ring_rows_html.append(
            "<tr>"
            "<td>Anillo {ring}</td>"
            "<td>{lo:.1f}° – {hi:.1f}° (horizonte {h_lo:.1f}° – {h_hi:.1f}°)</td>"
            "<td class='num'>{n_px}</td>"
            "<td class='num'>{n_light}</td>"
            "<td class='num'>{n_dark}</td>"
            "<td class='num'><strong>{cov}</strong></td>"
            "<td class='num'>{gap}</td>"
            "</tr>".format(
                ring=r["ring"],
                lo=lo,
                hi=hi,
                h_lo=max(0.0, 90.0 - hi),
                h_hi=max(0.0, 90.0 - lo),
                n_px=fmt_int(n_px),
                n_light=fmt_int(n_light),
                n_dark=fmt_int(n_dark),
                cov=cov_s,
                gap=gap_s,
            )
        )

    lai_rows_html = []
    lai_bounds = lai.get("ring_boundaries", boundaries)
    lai_gaps = lai.get("per_ring_gap_fraction", [])
    for i, contrib in enumerate(lai.get("lai_per_ring", [])):
        lo, hi = lai_bounds[i] if i < len(lai_bounds) else (0.0, 0.0)
        gf = lai_gaps[i] if i < len(lai_gaps) else None
        lai_rows_html.append(
            "<tr><td>Anillo {n}</td><td>{lo:.1f}° – {hi:.1f}°</td>"
            "<td class='num'>{gf}</td><td class='num'>{c:.4f}</td></tr>".format(
                n=i + 1, lo=lo, hi=hi, c=contrib,
                gf="{:.2f}%".format(100.0 * gf) if gf is not None else "n/d",
            )
        )

    images_section_html = ""
    if include_images and warnings:
        images_section_html = (
            "<section class='card'><h2>4. Visualizaciones del Análisis</h2>"
            "<div class='meas-box'><strong>Aviso:</strong> "
            + "<br/>".join(html.escape(w) for w in warnings)
            + "</div></section>"
        )
    if glama_uri or thr_uri:
        cards = []
        if glama_uri:
            cards.append(
                "<div class='img-card'>"
                "<h4>Anillos cenitales (anillos de referencia, máscara y sectores)</h4>"
                "<img src='{uri}' alt='Vista de anillos cenitales'/>"
                "</div>".format(uri=glama_uri)
            )
        if thr_uri:
            cards.append(
                "<div class='img-card'>"
                "<h4>Clasificación Cielo / Dosel (Nivel de corte T = {thr})</h4>"
                "<img src='{uri}' alt='Superposición de umbral'/>"
                "</div>".format(uri=thr_uri, thr=threshold)
            )
        images_section_html = (
            "<section class='card'>"
            "<h2>4. Visualizaciones del Análisis</h2>"
            "<div class='img-grid'>" + "".join(cards) + "</div>"
            "</section>"
        )

    html_doc = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Informe CobDosel — {image_name}</title>
<style>
  :root {{
    --bg: #f4f7f6;
    --card-bg: #ffffff;
    --primary: #0d5c63;
    --primary-dark: #073b40;
    --accent: #e07a2b;
    --glama-top: #0a0a0a;
    --glama-teal: #0b4f5e;
    --glama-orange: #f09c38;
    --text: #1f2933;
    --muted: #52606d;
    --border: #d9e2ec;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    margin: 0;
    padding: 24px;
    line-height: 1.5;
  }}
  .container {{
    max-width: 1080px;
    margin: 0 auto;
  }}
  header.report-header {{
    background: linear-gradient(135deg, var(--primary-dark), var(--primary));
    color: #ffffff;
    padding: 24px 28px;
    border-radius: 10px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 16px;
  }}
  header.report-header h1 {{
    margin: 0 0 6px 0;
    font-size: 1.65rem;
    letter-spacing: 0.3px;
  }}
  header.report-header p {{
    margin: 2px 0;
    font-size: 0.95rem;
    opacity: 0.92;
  }}
  .author-badge {{
    background: rgba(255, 255, 255, 0.14);
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 0.88rem;
    text-align: left;
  }}
  .author-badge a {{
    color: #ffd180;
    text-decoration: none;
  }}
  section.card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  section.card h2 {{
    margin-top: 0;
    margin-bottom: 14px;
    color: var(--primary-dark);
    font-size: 1.2rem;
    border-bottom: 2px solid var(--border);
    padding-bottom: 8px;
  }}
  .kv-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 10px 24px;
  }}
  .kv-row {{
    display: flex;
    justify-content: flex-start;
    gap: 10px;
    padding: 6px 0;
    border-bottom: 1px dashed #e4e7eb;
    font-size: 0.94rem;
  }}
  .kv-row span.label {{
    color: var(--muted);
    font-weight: 500;
  }}
  .kv-row span.val {{
    font-weight: 600;
    text-align: left;
  }}
  .glama-panel {{
    border-radius: 10px;
    overflow: hidden;
    border: 2px solid #073b40;
    margin-bottom: 18px;
  }}
  .glama-file-bar {{
    background: #6c757d;
    color: #ffffff;
    padding: 8px 16px;
    font-weight: 700;
    font-size: 0.95rem;
    letter-spacing: 0.4px;
  }}
  .glama-sub-bar {{
    background: #0b4f5e;
    color: #ffffff;
    padding: 6px 16px;
    font-weight: 700;
    font-size: 1.05rem;
  }}
  .glama-black {{
    background: var(--glama-top);
    color: #ffffff;
    padding: 18px 22px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 18px 28px;
  }}
  .glama-teal {{
    background: var(--glama-teal);
    color: #ffffff;
    padding: 20px 22px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 20px 28px;
  }}
  .glama-item h3 {{
    margin: 0 0 4px 0;
    color: var(--glama-orange);
    font-size: 1.05rem;
    font-weight: 700;
  }}
  .glama-item p.desc {{
    margin: 0 0 8px 0;
    color: #b8dce4;
    font-size: 0.86rem;
  }}
  .glama-item .big-val {{
    font-size: 1.45rem;
    font-weight: 700;
    color: #ffffff;
  }}
  .glama-item .sub-val {{
    font-size: 1.05rem;
    color: #d9e2ec;
  }}
  table.data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.92rem;
    margin-top: 8px;
  }}
  table.data-table th, table.data-table td {{
    padding: 9px 12px;
    border-bottom: 1px solid var(--border);
    text-align: left;
  }}
  table.data-table th {{
    background: #f0f4f8;
    color: var(--primary-dark);
    font-weight: 700;
  }}
  table.data-table td.num, table.data-table th.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
  }}
  table.data-table tr:hover {{
    background: #f8fafc;
  }}
  .caco-box {{
    background: #0b4f5e;
    color: #ffffff;
    border-radius: 10px;
    padding: 14px 20px;
    margin-bottom: 16px;
  }}
  .caco-label {{ font-size: 1.05rem; color: #f09c38; font-weight: 700; }}
  .caco-val {{ font-size: 2.2rem; font-weight: 800; }}
  .caco-note {{ font-size: 0.88rem; color: #d9eef2; }}
  .warn-box {{
    background: #fff4e5;
    border-left: 4px solid #e07a2b;
    padding: 10px 14px;
    border-radius: 4px;
    margin: 10px 0;
    font-size: 0.92rem;
  }}
  .meas-box {{
    background: #eef6f7;
    border-left: 4px solid var(--primary);
    padding: 12px 16px;
    border-radius: 4px;
    margin-top: 14px;
    font-size: 0.93rem;
  }}
  .img-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 20px;
  }}
  .img-card {{
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
    background: #fafbfc;
  }}
  .img-card h4 {{
    margin: 0 0 10px 0;
    color: var(--primary-dark);
  }}
  .img-card img {{
    max-width: 100%;
    height: auto;
    border-radius: 6px;
  }}
  footer {{
    text-align: left;
    font-size: 0.85rem;
    color: var(--muted);
    margin-top: 24px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }}
  @media print {{
    body {{ background: #ffffff; padding: 0; }}
    section.card {{ box-shadow: none; break-inside: avoid; }}
    .glama-panel {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="container">

  <header class="report-header">
    <div>
      <h1>CobDosel — Informe de cobertura del dosel</h1>
      <p><strong>Archivo de imagen:</strong> {image_name}</p>
      <p><strong>Fecha del informe:</strong> {now_str}</p>
    </div>
    <div class="author-badge">
      <div><strong>CobDosel v{version} para QGIS</strong></div>
      <div>Autor: <strong>Jorge Fallas</strong></div>
      <div>Contacto: <a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a></div>
    </div>
  </header>

  <section class="card">
    <h2>1. Resultados (basado en Tichý 2016 — <a href="https://doi.org/10.1111/jvs.12350" target="_blank">doi:10.1111/jvs.12350</a>)</h2>
    {geometry_banner}
    <div class="caco-box">
      <div class="caco-label">Cobertura del dosel — Índice CaCo</div>
      <div class="caco-val">{caco_index_pct:.2f}%</div>
      <div class="caco-note">Valor de cobertura del dosel (proyección vertical). El cierre del dosel no es
      cobertura.</div>
    </div>
    <div class="glama-panel">
      <div class="glama-file-bar">ARCHIVO (FILE): {image_name}</div>
      <div class="glama-sub-bar">Resultados (Results)...</div>
      <div class="glama-black">
        <div class="glama-item">
          <h3>N.º total de píxeles en el círculo (en el fotograma)<br/><small>Total No. of Pixels in Circle (in Frame)</small></h3>
          <div class="big-val">{total_circle_px} px</div>
          <div class="sub-val">({total_frame_px} px)</div>
        </div>
        <div class="glama-item">
          <h3>N.º de píxeles claros (oscuros)<br/><small>No. of Light (Dark) Pixels</small></h3>
          <div class="big-val">{light_px} px</div>
          <div class="sub-val">({dark_px} px)</div>
        </div>
        <div class="glama-item">
          <h3>Fracción de claros del área seleccionada<br/><small>Gap Fraction of Selected Area</small></h3>
          <div class="big-val">{gap_fraction_pct:.2f}%</div>
          <div class="sub-val">Sobre el área analizada no enmascarada: {gap_unmasked_pct:.2f}%</div>
        </div>
        <div class="glama-item">
          <h3>Fracción del hemisferio captada por la cámara<br/><small>Part of Hemisph. Taken by Camera</small></h3>
          <div class="big-val">{hemi_frac:.2f}%</div>
          <div class="sub-val">Área tras máscara de horizonte ({horizon_mask_deg:.1f}°): {analyzed_hemi_frac:.2f}%</div>
        </div>
        <div class="glama-item">
          <h3>Nivel de corte entre píxeles blancos y negros (1–254)<br/><small>Cut Level between Black and White Pixels (1–254)</small></h3>
          <div class="big-val">{threshold}</div>
          <div><small>{cut_method}</small></div>
          <div class="sub-val">Canal: {channel_label}</div>
        </div>
        <div class="glama-item">
          <h3>Índice de Área Foliar Efectivo (Miller)<br/><small>Effective Leaf Area Index (LAIe)</small></h3>
          <div class="big-val">{lai_eff:.3f}</div>
          <div class="sub-val">{lai_note}</div>
        </div>
      </div>

      <div class="glama-teal">
        <div class="glama-item">
          <h3>Apertura del Dosel (Canopy Openness)</h3>
          <p class="desc">Cielo abierto / hemisferio completo (ponderado por sin θ; lo enmascarado cuenta como obstruido)</p>
          <div class="big-val">{canopy_openness_pct:.2f}%</div>
          <div class="sub-val">Sobre el área analizada (0–{zenith_max_deg:.1f}°): {openness_analysed_pct:.2f}%</div>
        </div>
        <div class="glama-item">
          <h3>Cierre del Dosel (Canopy Closure)</h3>
          <p class="desc">Área de cielo obstruido / área total del hemisferio (ponderado por sin θ)</p>
          <div class="big-val">{canopy_closure_pct:.2f}%</div>
        </div>
        <div class="glama-item">
          <h3>Índice de Cobertura del Dosel — Canopy Cover (CaCo) Index</h3>
          <p class="desc">Cobertura del dosel (Tichý 2016): transmitancia de cada anillo llevada a la vertical (T^cos θ), ponderada por sin θ·cos θ</p>
          <div class="big-val">{caco_index_pct:.2f}%</div>
        </div>
        <div class="glama-item">
          <h3>Índice CaCo Modificado — Modif. CaCo Index</h3>
          <p class="desc">Misma conversión T^cos θ, ponderada solo por ángulo sólido (sin θ); menos sensible a claros cerca del horizonte</p>
          <div class="big-val">{mod_caco_index_pct:.2f}%</div>
        </div>
      </div>
    </div>

    <div class="meas-box">
      <strong>Nota metodológica (Tichý, 2016):</strong> {meas_label}<br/>
      <span>{meas_note}</span>
    </div>
    <div class="meas-box">
      <strong>Definiciones y alcance (CobDosel v{version}):</strong>
      «Fracción de claros del área seleccionada» = píxeles claros no enmascarados / total de
      píxeles del círculo virtual. Fracción de claros, apertura, cierre y CaCo se calculan con el
      según Tichý (2016) (anillos de 1/90 del radio).
      Los índices son sensibles al nivel de corte. Números: punto decimal y espacio como
      separador de miles.
    </div>
    {run_warnings_html}
  </section>

  <section class="card">
    <h2>2. Datos de la Imagen y Parámetros de Calibración del Lente</h2>
    <div class="kv-grid">
      <div>
        <div class="kv-row"><span class="label">Nombre del archivo:</span><span class="val">{image_name}</span></div>
        <div class="kv-row"><span class="label">Dimensiones analizadas:</span><span class="val">{dim_str}</span></div>
        <div class="kv-row"><span class="label">Fecha/hora de captura (EXIF):</span><span class="val">{capture_dt}</span></div>
        <div class="kv-row"><span class="label">Cámara / Dispositivo:</span><span class="val">{camera_str}</span></div>
        <div class="kv-row"><span class="label">Coordenadas GPS (WGS84):</span><span class="val">{gps_str}</span></div>
        <div class="kv-row"><span class="label">Canal de umbralización:</span><span class="val">{channel_label}</span></div>
        <div class="kv-row"><span class="label">Nivel de corte (umbral T):</span><span class="val">{threshold} ({bright_str})</span></div>
        <div class="kv-row"><span class="label">Método del nivel de corte:</span><span class="val">{cut_method}</span></div>
        <div class="kv-row"><span class="label">Limpieza morfológica:</span><span class="val">{cleanup_str}</span></div>
      </div>
      <div>
        <div class="kv-row"><span class="label">Tipo de lente:</span><span class="val">{lens_type_label}</span></div>
        <div class="kv-row"><span class="label">Modelo de proyección:</span><span class="val">{proj_label}</span></div>
        <div class="kv-row"><span class="label">Diámetro físico del círculo ref.:</span><span class="val">{circle_cm_str}</span></div>
        <div class="kv-row"><span class="label">Altura de la cámara sobre el círculo:</span><span class="val">{height_cm_str}</span></div>
        <div class="kv-row"><span class="label">Diámetro medido en píxeles:</span><span class="val">{px_diam_str}</span></div>
        <div class="kv-row"><span class="label">Ángulo de referencia (θ_ref):</span><span class="val">{theta_ref_str}</span></div>
        <div class="kv-row"><span class="label">Fórmula de calibración:</span><span class="val">{calib_formula}</span></div>
        <div class="kv-row"><span class="label">Semiángulo de visión (θ_máx / Half-FOV):</span><span class="val">{half_fov:.2f}° (FOV total: {full_fov:.2f}°)</span></div>
        <div class="kv-row"><span class="label">Máscara de horizonte artificial:</span><span class="val">{mask_str}</span></div>
        <div class="kv-row"><span class="label">Longitud focal (f) / Radio hemisferio (90°):</span><span class="val">{focal_px_str} / {virt_r_str}</span></div>
        <div class="kv-row"><span class="label">Semiángulo en la esquina de la foto:</span><span class="val">{frame_max_str}</span></div>
        <div class="kv-row"><span class="label">Círculo de análisis visible en la foto:</span><span class="val">{visible_str}</span></div>
        <div class="kv-row"><span class="label">Medición del círculo:</span><span class="val">{measure_str}</span></div>
        <div class="kv-row"><span class="label">Centro óptico (cx, cy):</span><span class="val">{center_str}</span></div>
        <div class="kv-row"><span class="label">Orientación / rumbo EXIF:</span><span class="val">{exif_orient_str}</span></div>
      </div>
    </div>
  </section>

  <section class="card">
    <h2>3. Detalle por Anillos Cenitales (0° – {zenith_max_deg:.1f}°, Máscara de Horizonte {horizon_mask_deg:.1f}°)</h2>
    <table class="data-table">
      <thead>
        <tr>
          <th>Anillo</th>
          <th>Rango cenital (y altura sobre horizonte)</th>
          <th class="num">Píxeles totales</th>
          <th class="num">Píxeles claros (cielo)</th>
          <th class="num">Píxeles oscuros (dosel)</th>
          <th class="num">Cobertura (%)</th>
          <th class="num">Fracción de claros (%)</th>
        </tr>
      </thead>
      <tbody>
        {ring_rows}
      </tbody>
    </table>
    <h3 style="margin-top:18px;">LAI efectivo por anillo — {lai_note}</h3>
    <table class="data-table">
      <thead>
        <tr><th>Anillo LAI</th><th>Rango cenital</th>
        <th class="num">Fracción de claros (%)</th><th class="num">Contribución LAI</th></tr>
      </thead>
      <tbody>
        {lai_rows}
      </tbody>
    </table>
    {sector_html}
  </section>

  {images_section}

  <footer>
    Generado por <strong>CobDosel v{version}</strong> (cobertura del dosel, basado en Tichý 2016, <a href="https://doi.org/10.1111/jvs.12350" target="_blank">doi:10.1111/jvs.12350</a>) —
    Autor: <strong>Jorge Fallas</strong> (<a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a>)
  </footer>

</div>
</body>
</html>
""".format(
        image_name=html.escape(image_name),
        now_str=html.escape(now_str),
        version=VERSION,
        mask_str=html.escape(mask_str),
        calib_formula=html.escape(calib_formula),
        total_circle_px=fmt_int(total_circle_px),
        total_frame_px=fmt_int(total_frame_px),
        light_px=fmt_int(light_px),
        dark_px=fmt_int(dark_px),
        gap_unmasked_pct=gap_unmasked_pct,
        openness_analysed_pct=float(metrics.get("canopy_openness_analysed_pct", canopy_openness_pct)),
        lai_note=lai_note,
        gap_fraction_pct=gap_fraction_pct,
        hemi_frac=hemi_frac,
        horizon_mask_deg=horizon_mask_deg,
        analyzed_hemi_frac=analyzed_hemi_frac,
        threshold=threshold,
        cut_method=html.escape(str(results.get("cut_method") or "manual")),
        channel_label=html.escape(channel_label),
        lai_eff=lai_eff,
        zenith_max_deg=zenith_max_deg,
        canopy_openness_pct=canopy_openness_pct,
        canopy_closure_pct=canopy_closure_pct,
        caco_index_pct=caco_index_pct,
        mod_caco_index_pct=mod_caco_index_pct,
        meas_label=html.escape(meas["label"]),
        meas_note=html.escape(meas["note"]),
        dim_str=html.escape(dim_str),
        capture_dt=html.escape(str(capture_dt)),
        camera_str=html.escape(camera_str),
        gps_str=html.escape(gps_str),
        bright_str="Cielo más brillante que el dosel" if sky_is_bright else "Cielo más oscuro que el dosel",
        cleanup_str="Activada (apertura + cierre)" if apply_cleanup else "Desactivada",
        lens_type_label=html.escape(lens_type_label),
        proj_label=html.escape(str(proj_label)),
        circle_cm_str=html.escape(circle_cm_str),
        height_cm_str=html.escape(height_cm_str),
        px_diam_str=html.escape(px_diam_str),
        theta_ref_str=html.escape(theta_ref_str),
        half_fov=half_fov,
        full_fov=full_fov,
        focal_px_str=html.escape(focal_px_str),
        virt_r_str=html.escape(virt_r_str),
        center_str=html.escape(center_str),
        ring_rows="\n        ".join(ring_rows_html),
        lai_rows="\n        ".join(lai_rows_html),
        images_section=images_section_html,
        geometry_banner=geometry_banner,
        run_warnings_html=run_warnings_html,
        frame_max_str=html.escape(frame_max_str),
        visible_str=html.escape(visible_str),
        measure_str=html.escape(measure_str),
        exif_orient_str=html.escape(exif_orient_str),
        sector_html=sector_html,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_doc)

    results["report_warnings"] = warnings
    return output_path
