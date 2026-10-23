# Pruebas de CobDosel

Pruebas que se ejecutan **sin QGIS**: los módulos de `qgis.core` se sustituyen por stubs y los diálogos se abren con Qt fuera de pantalla. Todas las imágenes de prueba son sintéticas y se generan en `tests/_out/`.

```bash
bash tests/run_all.sh PyQt5
bash tests/run_all.sh PyQt6
```

Requisitos: Python 3, numpy, scipy, Pillow, openpyxl y PyQt5 o PyQt6.

| Prueba | Qué comprueba |
|---|---|
| `check_metodos.py` | Cada llamada `self.metodo()` existe en su clase (o es heredada de Qt) |
| `check_unbound.py` | Heurística: variables asignadas en un `try` y usadas después de un `except` que no sale |
| `test_v0145.py` | Medición del círculo: modos, avisos y veredicto |
| `test_batch_v013.py` | Lote: formulario, emparejamiento, máscaras y medias; genera las fotos sintéticas del lote |
| `smoke_dialog_v011.py` | Diálogo principal completo: calibración, corte, análisis, informes y CSV |
| `smoke_batch_v014.py` | Diálogo del lote y revisión de cortes (usa las fotos de `test_batch_v013.py`) |
| `test_proj_v01422.py` | El tipo de lente y el modelo de proyección se conservan al cargar una calibración |
| `test_audit_v01423.py` | Correcciones de la auditoría de 0.14.23 (corte Mínimo, centro del lote, círculos degenerados, CSV UTF-8) |
| `test_lens_v01426.py` | Modelos de proyección por tipo de lente; «Rectilínea» predeterminado; radio de GLAMA |
| `test_cal_v01427.py` | La calibración se mantiene entre fotos y se recuerda la última; registro en el lote |
| `test_measure_v01430.py` | La medición del círculo pide D y H y no se sobrescribe con la calibración recordada |
| `test_zoom_v01431.py` | Zoom por rectángulo y zoom escrito en la medición del círculo y en la ventana de corte |
| `test_orient_v01432.py` | «Añadir imagen original» añade la foto con la orientación EXIF aplicada |
| `test_focal_v01433.py` | Comprobación de la distancia focal: umbrales (EXIF ±8/15 %, propia ±3/8 %) y avisos |
| `test_review_zoom_v01433.py` | Zoom por rectángulo y zoom escrito en «Revisar cortes…» |
| `test_projsync_v01434.py` | Cambiar el modelo de proyección recalcula la calibración activa |
| `test_area_v01435.py` | La ventana de corte muestra y cuenta solo el área analizada (requiere fotos reales) |
| `consistency_v01423.py` | Coherencia del análisis con fotos reales (requiere fotos reales) |

Las dos últimas pruebas necesitan fotos reales, que no se incluyen en el repositorio: `COBDOSEL_FOTOS=<carpeta> bash tests/run_all.sh PyQt5`.
| `test_audit_v01423.py` | Correcciones de la auditoría de v0.14.23 (método Mínimo, mediciones degeneradas, centro en el lote, reemplazo de calibraciones) |

Las pruebas no sustituyen la verificación manual en QGIS 3.x y 4.x antes de publicar.
