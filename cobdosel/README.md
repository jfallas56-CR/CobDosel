# CobDosel — cobertura del dosel a partir de fotografías

![version](https://img.shields.io/badge/version-0.14.39-green) ![QGIS](https://img.shields.io/badge/QGIS-3.28%E2%80%934.x-blue) ![licencia](https://img.shields.io/badge/licencia-GPL--2.0-lightgrey)

Complemento de QGIS que estima la **cobertura del dosel** a partir de fotografías cenitales de teléfono u ojo de pez con el método de **Tichý (2016)** ([doi:10.1111/jvs.12350](https://doi.org/10.1111/jvs.12350)).

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
| Índice CaCo Modificado | Igual, ponderado por `sin θ` |
| Nivel de corte recomendado (log-normal) | Cruce de dos log-normales ajustadas al histograma. Implementación independiente en Python del procedimiento del nivel de corte recomendado de la app GLAMA (Tichý 2016), reconstruido a partir de la app y verificado con sus resultados. Pasos en la Ayuda §10. |
| Fracción de claros por sector | Anillo × sector de acimut (S1 = arriba, sentido horario) |
| LAI efectivo | Miller (1967) normalizado al rango cenital observado (por defecto 0–60°) |

Salidas: panel de resultados, CSV, capa de puntos GPS (EXIF), vista «Anillos cenitales», superposición de la clasificación e informe HTML autocontenido.

## Flujo de trabajo

1. **Imagen:** fotografía cenital original del teléfono (JPEG con EXIF; también PNG, TIFF, WebP; HEIC con `pillow-heif`).
2. **Calibración:**
   - círculo de diámetro conocido *D* a una distancia *H*, centrado en la foto; medición con **dos diámetros E–O y N–S** o **ajuste de ≥ 5 puntos**, con control de calidad (diferencia ≤ 1 %, centro ≤ 5 % del diámetro);
   - o el **«Hemisph. radius» de la app GLAMA**;
   - o detección automática del círculo de un ojo de pez.

   Se muestran el radio del hemisferio *R* y su equivalente en GLAMA. La calibración guardada registra en qué foto se midió el círculo.
3. **Nivel de corte (1–254):** recomendado (log-normal) o automático (Mínimo u Otsu) sobre el área analizada; un solo criterio para todas las fotos.
4. **Máscara de horizonte:** Tichý (2016) recomienda > 45° sobre el horizonte, o la Tabla 1 de GLAMA. El análisis llega hasta la máscara; si el círculo sale de la foto se informa el % visible.
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

## Requisitos

- QGIS 3.28 LTR o posterior (probado sin interfaz con PyQt5 y PyQt6; falta la prueba manual en QGIS).
- Obligatorios: `numpy`, `Pillow` (incluidos en las instalaciones habituales de QGIS).
- Opcionales: `scipy` (limpieza morfológica), `opencv-python` (detección del círculo ojo de pez), `pillow-heif` (HEIC), `openpyxl` (formulario en Excel; sin él se usa GDAL de QGIS o el formulario en CSV).

## Alcance y validación

- **Fidelidad al método de Tichý (2016) y a la app GLAMA:** fracción de claros, apertura, cierre, CaCo y nivel de corte recomendado reproducen exactamente los casos de prueba de la app y valores publicados de la app.
- **Diferencias conocidas con la app GLAMA:**
  - la pantalla de análisis de GLAMA usa el recorte cuadrado central de la foto (1080 px = lado menor), y en fotos 4:3 su escala difiere en 4/3 de la de calibración;
  - si el círculo de la máscara sale de la foto, GLAMA cuenta la franja negra como dosel;
  - GLAMA clasifica la imagen reducida de su pantalla.

  Con la misma geometría, CobDosel y GLAMA coinciden en ≈ 1–2 puntos de CaCo. La opción «geometría de pantalla de GLAMA» reproduce la app para estudios pareados de transición; no debe usarse para el valor oficial.
- **Calibración:** geometría exacta `atan(D/2H)`, la misma que usa la app GLAMA (comprobado: el radio del hemisferio de la app coincide con esa fórmula en 15 combinaciones de *D* y *H*). Modelo predeterminado «Rectilínea»; «Lineal» equivale al «Polar» de GLAMA. Las calibraciones antiguas con la aproximación `atan(D/H)/2` se siguen leyendo.
- **Nivel de corte:** todos los índices dependen del umbral cielo/dosel; fije un criterio y regístrelo.
- **Validación pendiente:** ni GLAMA ni CobDosel se han validado en Costa Rica contra una referencia independiente (tubo de observación vertical o LiDAR).
- **Formato numérico:** punto decimal y espacio como separador de miles en pantalla e informe; el CSV guarda números sin separador.

## Historial

- **0.14.39 (2026-10-23):** Intro ya no pulsa botones; flechas para mover la imagen; quitar puntos en la medición del círculo; fotos HEIC del iPhone en el lote.
- **0.14.38 (2026-10-22):** correcciones de una revisión independiente (sincronía del modelo, centro en «Revisar cortes…», medición en otra foto, filtro de calidad, corte de Otsu y más); pruebas nuevas de escenarios, respuesta a las entradas y hechos verificados.
- **0.14.37 (2026-10-22):** descripción emergente de «Modelo de proyección» corregida.
- **0.14.36 (2026-10-22):** documentación: GLAMA usa la fórmula exacta atan(D/2H), como CobDosel.
- **0.14.35 (2026-10-22):** la ventana de nivel de corte muestra solo el área analizada (fuera, en verde azulado), como GLAMA.
- **0.14.34 (2026-10-22):** cambiar el modelo de proyección recalcula la calibración activa (antes la lista y la calibración podían no coincidir); ayuda actualizada.
- **0.14.33 (2026-10-22):** «Rectilínea» como modelo predeterminado para lente regular; comprobación de la distancia focal al calibrar; zoom por rectángulo en «Revisar cortes…»; modelo y focal en la línea de calibración del lote.
- **0.14.32 (2026-10-21):** «Añadir imagen original» añade la foto con la orientación EXIF aplicada, igual que los anillos y la superposición.
- **0.14.31 (2026-10-21):** zoom por rectángulo (clic derecho y arrastrar) y valor de zoom escrito en la medición del círculo y en la ventana de umbral; zoom alto sin copia gigante de la foto.
- **0.14.30 (2026-10-21):** la medición del círculo pide D y H; corrección de la sobrescritura de la medición por la calibración recordada.
- **0.14.29 (2026-10-21):** máscara estándar de 63° (cenit 0–27°) en ambas ventanas.
- **0.14.28 (2026-10-21):** diámetro del círculo «sin medir» en lugar de 1975 px fijos.
- **0.14.27 (2026-10-20):** la calibración se mantiene entre fotos y se recuerda la última; máscara predeterminada de 60°; registro de la calibración en el lote.
- **0.14.26 (2026-10-20):** modelos de proyección filtrados por tipo de lente; corrección de «math domain error» con el círculo entero dentro de la foto.
- **0.14.25 (2026-10-20):** ayuda: interpretación de la prueba de dos círculos.
- **0.14.24 (2026-10-19):** ayuda: recomendación para teléfonos y círculos de tamaño GLAMA.
- **0.14.23 (2026-10-19):** auditoría: método Mínimo con dosel saturado, centro de la calibración en el lote, mediciones degeneradas, error del botón recomendado, confirmación al reemplazar calibraciones, CSV con BOM.
- **0.14.22 (2026-10-19):** corrección: el modelo de proyección de una calibración cargada se muestra correctamente; ayuda: tipo de lente y modelos de proyección.
- **0.14.21 (2026-10-19):** ayuda: procedimiento de calibración, círculo grande y prueba con dos círculos.
- **0.14.20 (2026-10-19):** ayuda: orientación EXIF y recorte en los bordes cortos.
- **0.14.19 (2026-10-19):** ayuda: una calibración por modelo de teléfono.
- **0.14.18 (2026-10-19):** ayuda ampliada (convención de la máscara, corte heredado, fotos sin dos modos).
- **0.14.17 (2026-10-19):** inspector de píxeles en la vista previa del umbral.
- **0.14.16 (2026-10-19):** texto del método del corte sin repetición.
- **0.14.15 (2026-10-19):** superposición de umbral con el área analizada (fuera de la máscara en verde azulado).
- **0.14.14 (2026-10-19):** leyenda de la vista de anillos sin símbolo ilegible; indica la máscara mínima para quedar dentro de la foto.
- **0.14.13 (2026-10-19):** el corte de la foto anterior se marca como heredado y se avisa al ejecutar.
- **0.14.12 (2026-10-19):** comprobación del corte recomendado también en el análisis de una foto, con aviso y método «no comprobado».
- **0.14.11 (2026-10-18):** control de calidad de la medición con veredicto global y mensajes agrupados (fotografía / medición).
- **0.14.10 (2026-10-18):** ayuda con protocolo de campo, CaCo frente a fracción de claros sin ponderar y comparabilidad (Bianchi et al. 2017).
- **0.14.9 (2026-10-18):** método del nivel de corte registrado en panel, informe HTML y CSV (foto y lote).
- **0.14.8 (2026-10-18):** sin remisiones a figuras o páginas del manual de GLAMA (se mantiene la cita de Tichý 2015 para la Tabla 1); vista previa con la guía de cada modo.
- **0.14.7 (2026-10-18):** líneas que no se cruzan en su punto medio: nota si los 4 puntos están sobre un mismo círculo, advertencia si no; textos de control de calidad más claros.
- **0.14.6 (2026-10-18):** dos diámetros: diámetro y centro del círculo que pasa por los 4 puntos (antes intersección de las líneas, desplazada si una línea no era un diámetro); aviso.
- **0.14.5 (2026-10-18):** nivel de corte automático Otsu o Mínimo (selector + Calcular); vistas Claro/Oscuro; desplazamiento del centro del círculo dibujado en todos los modos, aviso graduado y control del arco de los puntos; recomendaciones de medición en la ayuda; autor fuera de las ventanas.
- **0.14.4 (2026-10-18):** misma opacidad en las vistas Claro y Oscuro, ajustable.
- **0.14.3 (2026-10-18):** lente regular por defecto; menos menciones de GLAMA; sin fórmula atan(D/H)/2 ni radio equivalente GLAMA; informe alineado a la izquierda; zoom con la rueda y arrastre en la vista previa.
- **0.14.2 (2026-10-18):** exportaciones en la carpeta de la foto; se cita Tichý (2016); vista «Anillos cenitales».
- **0.14.1 (2026-10-18):** corrección: las calibraciones medidas se guardaban como «diámetro escrito a mano» y la medición en otra foto no se reescalaba; recalibre las calibraciones hechas con 0.11.0–0.14.0.
- **0.14.0 (2026-10-18):** comprobación del corte automático y revisión visual de cortes en el lote, con registro de decisiones; descripción del procedimiento del corte recomendado y referencias (Kittler e Illingworth 1986; Otsu 1979).
- **0.13.2 (2026-10-18):** «Recomendado (GLAMA)» pasa a «Recomendado (log-normal)»; la ayuda explica el origen del método (app GLAMA, archivos APK) y que 128 es solo el punto de partida.
- **0.13.1 (2026-10-18):** informes del lote en la carpeta de fotos y opción de abrir el HTML; botón «Registrar cámara…» para calibraciones antiguas.
- **0.13.0 (2026-10-18):** herramienta de uso general: se elimina el umbral de cobertura y las referencias legales; «formulario de fotos» (antes Formulario 8) y botón «Crear formulario desde las fotos…»; información de la calibración en el lote.
- **0.12.4 (2026-10-18):** comprobación de cámara/lente (EXIF) entre la calibración y cada foto; resoluciones distintas de la misma lente se reescalan; otras lentes se excluyen.
- **0.12.3 (2026-10-17):** «Recomendado (GLAMA)» iterado desde 128; ya no depende del valor previo del control.
- **0.12.2 (2026-10-17):** vista de anillos: intervalo automático según el cenit que cubre la foto, etiquetas visibles, aviso de máscara fuera de la foto.
- **0.12.1 (2026-10-17):** máscara fija de 60° por defecto en el lote; grupos de dosel en lugar de altura; columna de altura eliminada del Formulario 8.
- **0.12.0 (2026-10-17):** procesamiento por sitio (lote) con el Formulario 8 digital; plantilla Excel/CSV.
- **0.11.1 (2026-10-17):** la geometría de pantalla de GLAMA usa el centro del hemisferio desplazado 39 px en la vista (ajustable), que reproduce exactamente «(in Frame)» y «Part of Hemisph.» de la app.
- **0.11.0 (2026-10-17):** nuevo nombre **CobDosel**.
  - Análisis hasta la máscara de horizonte (antes se limitaba al semiángulo del lado corto).
  - Radio *R* y equivalente GLAMA visibles; trazabilidad de la medición del círculo y aviso al cargar calibraciones de otra proporción o sin trazabilidad.
  - Medición con dos diámetros o ajuste de círculo.
  - Calibración con el radio de GLAMA y modo «geometría de pantalla de GLAMA».
  - Aviso de círculo parcialmente fuera de la foto.
  - Vista «Anillos cenitales» nueva y fracción de claros por sector.
  - Orientación y rumbo EXIF.
  - Encabezado de resultados y CaCo identificado como cobertura del dosel.
  - Calibraciones en `~/.cobdosel` (se leen las de `~/.canopy`).
- **0.10.1 (2026-10-17):** corrige la calibración cuando el círculo se mide en una foto de otra resolución.
- **0.10.0 (2026-10-17):** LAI con rango propio y Miller normalizado; índices con el método GLAMA; nivel de corte recomendado; compatibilidad Qt5/Qt6.
- **0.9.0:** versión inicial.

---

## English summary

CobDosel is a QGIS plugin that estimates **canopy cover** from smartphone or fisheye canopy photographs with the method of Tichý (2016). The Canopy Cover (CaCo) Index is reported as the canopy-cover value (vertical projection). The plugin also reports the Modified CaCo Index, canopy openness and closure, gap fraction, per-azimuth-sector gap fraction and normalized Miller effective LAI. Calibration uses a known circle (two diameters or circle fit, with quality control and traceability) or the GLAMA app hemisphere radius. Outputs: results panel, CSV, GPS point layer, zenith-ring view and a self-contained HTML report. Known differences from the GLAMA app (square crop and 4:3 scale on its analysis screen, black band counted as canopy) are documented, and an optional GLAMA screen-geometry mode supports paired transition studies. License: GPL-2.0.
