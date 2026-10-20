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
| `test_audit_v01423.py` | Correcciones de la auditoría de v0.14.23 (método Mínimo, mediciones degeneradas, centro en el lote, reemplazo de calibraciones) |

Las pruebas no sustituyen la verificación manual en QGIS 3.x y 4.x antes de publicar.
