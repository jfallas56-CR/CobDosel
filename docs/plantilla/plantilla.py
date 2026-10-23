"""Plantilla de calibración CobDosel, tamaño carta: círculo de 20 cm (pág. 1) y círculos de 20 y 10 cm (pág. 2)."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import glob
reg = [f for f in glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)][0]
bold = [f for f in glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)][0]
pdfmetrics.registerFont(TTFont("DV", reg)); pdfmetrics.registerFont(TTFont("DVB", bold))
W, H = letter
LINE = 1.0 * mm

def circle_page(c, diameters, title, note, fields=None, title_dy=2.2):
    cx, cy = W / 2, H - 1.2 * cm - 10 * cm
    c.setStrokeColorRGB(0, 0, 0)
    for i, d in enumerate(diameters):
        c.setLineWidth(LINE if i == 0 else 0.8 * mm)
        c.circle(cx, cy, d / 2 * cm, stroke=1, fill=0)
    # Cruz central y marcas de los extremos de los diámetros E–O y N–S
    c.setLineWidth(0.3 * mm)
    c.line(cx - 6 * mm, cy, cx + 6 * mm, cy); c.line(cx, cy - 6 * mm, cx, cy + 6 * mm)
    c.circle(cx, cy, 1.0 * mm, stroke=1, fill=0)
    r = diameters[0] / 2 * cm
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        x0, y0 = cx + dx * (r - 9 * mm), cy + dy * (r - 9 * mm)
        x1, y1 = cx + dx * (r - 4 * mm), cy + dy * (r - 4 * mm)
        c.line(x0, y0, x1, y1)
    c.setFont("DV", 7)
    c.drawCentredString(cx, cy + r - 13 * mm, "N")
    c.drawCentredString(cx, cy - r + 10.5 * mm, "S")
    c.drawString(cx + r - 13 * mm, cy - 1 * mm, "E")
    c.drawString(cx - r + 10.5 * mm, cy - 1 * mm, "O")
    c.setFont("DVB", 9)
    c.drawCentredString(cx, cy + title_dy * cm, title)
    c.setFont("DV", 7.5)
    c.drawCentredString(cx, cy + (title_dy - 0.45) * cm, note)
    # Escala de 10 cm con marcas de 1 cm y 1 mm
    y = 5.6 * cm; x0 = W / 2 - 5 * cm
    c.setLineWidth(0.25 * mm); c.line(x0, y, x0 + 10 * cm, y)
    for k in range(101):
        h = 4 * mm if k % 10 == 0 else (2.5 * mm if k % 5 == 0 else 1.5 * mm)
        c.line(x0 + k * mm, y, x0 + k * mm, y + h)
    c.setFont("DV", 7)
    for k in range(11):
        c.drawCentredString(x0 + k * cm, y - 3 * mm, str(k))
    c.drawString(x0 + 10 * cm + 2 * mm, y - 0.5 * mm, "cm")
    c.drawCentredString(W / 2, y + 6 * mm, "Escala de control: debe medir exactamente 10 cm. Si no, imprima de nuevo al 100 %.")
    # Casillas de registro
    c.setFont("DV", 8)
    yb = 3.9 * cm
    fields = fields or (("D medido (cm)", 3.6), ("H, vidrio → papel (cm)", 4.0), ("Teléfono / lente", 4.6), ("Fecha", 2.8))
    x = 1.5 * cm
    for label, wcm in fields:
        c.rect(x, yb - 0.75 * cm, wcm * cm, 0.75 * cm)
        c.drawString(x + 1 * mm, yb + 1.2 * mm, label)
        x += wcm * cm + 0.35 * cm
    # Instrucciones
    c.setFont("DV", 7.2)
    lines = [
        "1. Imprima al 100 % («Tamaño real»; no «Ajustar a la página») y compruebe la escala de 10 cm.",
        "2. Mida el diámetro D sobre el papel, por el centro de la línea, en dos o tres diámetros; escriba el promedio en CobDosel (no el valor nominal).",
        "3. Mida H desde el vidrio de la cámara hasta el papel (p. ej. 40 cm). Papel plano, sin sombras sobre la línea; teléfono a 1x, paralelo al papel.",
        "4. Centre: alinee la cuadrícula 3 × 3 de la cámara con las marcas E–O y N–S; el centro de la foto cae en la cruz. Mida con «Ajuste de círculo», 8 puntos.",
    ]
    for i, t in enumerate(lines):
        c.drawString(1.5 * cm, 2.45 * cm - i * 3.6 * mm, t)
    c.setFont("DV", 6.5); c.setFillGray(0.4)
    c.drawRightString(W - 1.2 * cm, 0.8 * cm, "CobDosel — plantilla de calibración (carta, 21,59 × 27,94 cm)")
    c.setFillGray(0)

c = canvas.Canvas("Plantilla_calibracion_CobDosel_carta.pdf", pagesize=letter)
c.setTitle("Plantilla de calibración CobDosel (carta)")
c.setAuthor("Jorge Fallas")
circle_page(c, [20.0], "Círculo de calibración: D nominal 20 cm",
            "Con «Rectilínea» basta este círculo. Mida D impreso y escríbalo en CobDosel.")
c.showPage()
circle_page(c, [20.0, 10.0], "Comprobación con dos círculos: D nominales 20 y 10 cm",
            "Una sola foto; mida cada círculo con su propio D. Con «Rectilínea» la focal debe coincidir (±1 %).",
            fields=(("D grande medido (cm)", 3.4), ("D pequeño medido (cm)", 3.4), ("H (cm)", 2.2), ("Teléfono / lente", 4.0), ("Fecha", 2.2)),
            title_dy=7.3)
c.showPage(); c.save()
