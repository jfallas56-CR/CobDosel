# CobDosel — cobertura del dosel a partir de fotografías

![version](https://img.shields.io/badge/version-1.1.2-green) ![QGIS](https://img.shields.io/badge/QGIS-3.28%E2%80%934.x-blue) ![licencia](https://img.shields.io/badge/licencia-GPL--2.0-lightgrey)

Complemento de QGIS con dos herramientas:

- **Cobertura del dosel:** a partir de fotografías cenitales de teléfono u ojo de pez con el método de **Tichý (2016)** ([doi:10.1111/jvs.12350](https://doi.org/10.1111/jvs.12350)).
- **Cobertura del suelo (foto hacia abajo):** vegetación verde automática (Canopeo) y vegetación seca, hojarasca, suelo desnudo y clases propias por intercepción de puntos.

**Autor:** Jorge Fallas (jfallas56@gmail.com)

## Valor de cobertura

El **Índice CaCo** es la cobertura del dosel: proyección vertical del dosel, con los huecos dentro de las copas contados como abiertos. El *cierre* del dosel no es cobertura.

## Resultados

| Indicador | Descripción |
|---|---|
| N.º de píxeles en el círculo (en el fotograma) | Círculo virtual de 90° y su parte visible en la imagen |
| N.º de píxeles claros (oscuros) | Cielo no enmascarado; oscuros = total del círculo − claros |
| Fracción de claros del área seleccionada | Claros / total de píxeles del círculo virtual (verificado con resultados publicados de la app GLAMA) |
| Fracción del hemisferio captada | Fracción visible de cada anillo de 1°, ponderada por ángulo sólido |
| Apertura / cierre del dosel | Anillos de 1° ponderados por ángulo sólido; lo enmascarado cuenta como obstruido |
| **Índice CaCo** (cobertura del dosel) | Transmitancia de cada anillo llevada a la vertical (`T^cos θ`), ponderada por `sin θ · cos θ` |
| Nivel de corte recomendado (log-normal) | Cruce de dos log-normales ajustadas al histograma. Implementación independiente en Python del procedimiento del nivel de corte recomendado de la app GLAMA (Tichý 2016), reconstruido a partir de la app y verificado con sus resultados. Pasos en la Ayuda §10. |
| Fracción de claros por sector | Anillo × sector de acimut (S1 = arriba, sentido horario) |
| LAI efectivo | Miller (1967) normalizado al rango cenital observado (por defecto 0–60°); solo con ojo de pez de 180° («No aplica» con lente regular) |

Salidas: panel de resultados, CSV, capa de puntos GNSS (EXIF), vista «Anillos cenitales», superposición de la clasificación e informe HTML autocontenido.

## Flujo de trabajo

1. **Imagen:** fotografía cenital original del teléfono (JPEG con EXIF; también PNG, TIFF, WebP; HEIC con `pillow-heif`).
2. **Calibración:**
   - círculo de diámetro conocido *D* a una distancia *H*, centrado en la foto; medición con **dos diámetros E–O y N–S** o **ajuste de ≥ 5 puntos**, con control de calidad (diferencia ≤ 1 %, centro ≤ 5 % del diámetro);
   - o baldosas o un rectángulo de tamaño conocido en el suelo, con una o dos fotos a dos alturas («Calibrar con baldosas o un rectángulo conocido…»);
   - o detección automática del círculo de un ojo de pez.

   Se muestra el radio del hemisferio *R*. La calibración guardada registra en qué foto se midió el círculo.
3. **Nivel de corte (1–254):** recomendado (log-normal) o automático (Mínimo u Otsu) sobre el área analizada; un solo criterio para todas las fotos.
4. **Máscara de horizonte:** Tichý (2016) recomienda > 45° sobre el horizonte, o la máscara recomendada según parcela y altura del dosel (Tichý 2015). El análisis llega hasta la máscara; si el círculo sale de la foto se informa el % visible.
5. **Ejecutar** y exportar CSV / HTML.

## Procesamiento por sitio (lote)

Menú **CobDosel → Procesamiento por sitio (lote)**:

- **Diseño:** cualquiera; el formulario indica parcela y punto de cada foto (ejemplo: parcelas de 500 m² con 5 fotos: Centro, N-O, N-E, S-E, S-O a 8.9 m). El número de parcelas lo indica el usuario.
- **Entradas:** carpeta de fotos originales (sin renombrar), **formulario de fotos** (Excel/CSV; plantilla en `plantillas/`, o «Crear formulario desde las fotos…», que lo prellena con ID y hora de todas las fotos), calibración guardada en el diálogo principal, máscara de horizonte y n.º de parcelas planificadas.
- **Emparejamiento:** por ID de fotografía (nombre del archivo) y, como respaldo, por hora de captura (DD/MM/AAAA HH:MM:SS) frente a la hora EXIF, con tolerancia y desfase de reloj.
- **Máscara:** fija en **63°** por defecto (estándar de CobDosel; cenit ≤ 27°, círculo completo con teléfonos de 23–25 mm; Tichý 2016 usó 60°). Opcional: desde la altura del dosel, cenit = atan(6.31 / (altura − 1.3)), con la altura de referencia del estrato de dosel dominante (3 → 10 m, 4 → 22.5 m, 5 → 30 m) o escrita a mano.
- **Nivel de corte:** recomendado (log-normal) en cada foto, partiendo de 128 (convención de CobDosel), con comprobación del método; las fotos que no la pasan quedan «a revisar».
- **Revisión visual («Revisar cortes…»):** como la pantalla de corte de GLAMA (cielo en naranja, zoom, histograma, control deslizante, CaCo en vivo); aceptar, ajustar o excluir cada foto. Decisiones guardadas en `CobDosel_revision_cortes.json` y registradas en el CSV y el informe.
- **Resultado:** media por parcela (fotos válidas disponibles) y media del sitio (Índice CaCo); parcelas de reemplazo registradas; fotos de otra cámara/lente excluidas; CSV, informe HTML y capa de parcelas unida por ID.

## Cobertura del suelo (foto hacia abajo)

Menú **CobDosel → Cobertura del suelo (foto hacia abajo)**. Herramienta general: no supone un diseño de muestreo.

- **Foto:** cámara principal 1x, hacia abajo y nivelada, a altura fija (1–1,5 m), con luz difusa; la ayuda lista las buenas prácticas y las fotos que conviene evitar.
- **Área:** un **cuadro** físico (4 esquinas, cursor en cruz y líneas guía; se rectifica a un cuadrado) o un **área fija** desde la altura de la cámara y la calibración «Rectilínea» (la ventana indica qué cuadrado cabe a cada altura; una foto de otra proporción que la calibración se rechaza).
- **Vegetación verde (píxeles):** regla de Canopeo (Patrignani y Ochsner 2015: R/G < 0,95, B/G < 0,95, 2G − R − B > 20), comprobada con ExG − ExR (Meyer y Neto 2008). Si difieren más de 5 puntos, «a revisar», que no indica un error: la tecla C muestra dónde difieren (cian y naranja).
- **Intercepción de puntos:** cuadrícula regular con desfase aleatorio y semilla registrada; los puntos verdes según Canopeo se marcan solos y el analista clasifica los demás («Siguiente» asigna la clase marcada; teclas 1–9; clases propias, hasta 9; grupos de clases como «Vegetación total» para medir toda la vegetación). Regla para puntos dudosos: solo el píxel bajo el centro de la cruz (Booth et al. 2006). Cobertura de cada clase con IC 95 % (Wilson).
- **Varios analistas:** «Modo reglamentario» (el verde lo decide la regla de Canopeo), «Cargar área y cuadrícula de un CSV…» (doble clasificación sobre los mismos puntos) y «Comparar clasificaciones…» (acuerdo, kappa de Cohen, tabla de confusión y puntos en desacuerdo).
- **Varias fotos de un sitio:** «Procesamiento por sitio…» las clasifica una tras otra con los mismos parámetros (con formulario de fotos, en su orden y con parcela y punto); semilla de cada foto = semilla base + número; se puede continuar donde quedó. «Resumen del sitio»: media e IC 95 % con t de Student, por fotos o por parcelas.
- **Salidas:** CSV por foto y por punto, e informe HTML con la imagen del área y la de las diferencias entre las reglas.

## Requisitos

- QGIS 3.28 LTR o posterior (probado sin interfaz con PyQt5 y PyQt6; falta la prueba manual en QGIS).
- Obligatorios: `numpy`, `Pillow` (incluidos en las instalaciones habituales de QGIS).
- Opcionales: `opencv-python` (detección del círculo ojo de pez), `pillow-heif` (HEIC), `openpyxl` (formulario en Excel; sin él se usa GDAL de QGIS o el formulario en CSV).

## Alcance y validación

- **Fidelidad al método de Tichý (2016) y a la app GLAMA:** fracción de claros, apertura, cierre, CaCo y nivel de corte recomendado reproducen exactamente los casos de prueba de la app y valores publicados de la app.
- **Diferencias conocidas con la app GLAMA:**
  - la pantalla de análisis de GLAMA usa el recorte cuadrado central de la foto (1080 px = lado menor), y en fotos 4:3 su escala difiere en 4/3 de la de calibración;
  - si el círculo de la máscara sale de la foto, GLAMA cuenta la franja negra como dosel;
  - GLAMA clasifica la imagen reducida de su pantalla.

  Con la misma geometría, CobDosel y GLAMA coinciden en ≈ 1–2 puntos de CaCo.
- **Calibración:** geometría exacta `atan(D/2H)`, la misma que usa la app GLAMA (comprobado: el radio del hemisferio de la app coincide con esa fórmula en 15 combinaciones de *D* y *H*). Modelo predeterminado «Rectilínea»; «Lineal» equivale al «Polar» de GLAMA. Las calibraciones antiguas con la aproximación `atan(D/H)/2` se siguen leyendo.
- **Nivel de corte:** todos los índices dependen del umbral cielo/dosel; fije un criterio y regístrelo.
- **Validación pendiente:** ni GLAMA ni CobDosel se han validado en Costa Rica contra una referencia independiente (tubo de observación vertical o LiDAR).
- **Formato numérico:** punto decimal y espacio como separador de miles en pantalla e informe; el CSV guarda números sin separador.

## Ejemplo de resultados

Un informe HTML y el CSV de una foto real están en [`docs/ejemplos/`](docs/ejemplos/): [ver el informe](https://jfallas56-cr.github.io/CobDosel/ejemplos/Informe_CobDosel_ejemplo.html).

## Registro de cambios

El historial de versiones está en [CHANGELOG.md](https://github.com/jfallas56-CR/CobDosel/blob/main/CHANGELOG.md) del repositorio.

---

## English summary

CobDosel is a QGIS plugin with two tools. **Canopy cover:** estimates canopy cover from smartphone or fisheye canopy photographs with the method of Tichý (2016). The Canopy Cover (CaCo) Index is reported as the canopy-cover value (vertical projection); the plugin also reports canopy openness and closure, gap fraction, per-azimuth-sector gap fraction and Miller effective LAI (180° fisheye only). Calibration uses a known circle (two diameters or circle fit, with quality control and traceability), floor tiles or another known rectangle (one or two heights), or fisheye auto-detection. Site (batch) processing with a photo form gives plot and site means. **Ground cover:** downward photos of a rectified quadrat or a fixed area; automatic green vegetation with the Canopeo rule, checked against ExG − ExR, and dry vegetation, litter, bare soil and user-defined classes by point intercept with Wilson 95 % confidence intervals. Outputs: results panel, CSV, GNSS point layer, zenith-ring view and self-contained HTML reports. License: GPL-2.0.
