#!/usr/bin/env bash
# Pruebas de CobDosel sin QGIS (Qt fuera de pantalla). Uso: bash tests/run_all.sh [PyQt5|PyQt6]
# Requiere: numpy, scipy, Pillow, openpyxl y PyQt5 o PyQt6.
set -u
cd "$(dirname "$0")/.."
QT="${1:-PyQt5}"
OUT="tests/_out/$QT"
rm -rf "$OUT"; mkdir -p "$OUT"
export QT_QPA_PLATFORM=offscreen
fail=0

check() { local name="$1"; shift; if "$@" > "$OUT/$name.log" 2>&1 && ! grep -q '✗\|HAY FALLAS\|Traceback' "$OUT/$name.log"; then echo "OK    $name"; else echo "FALLA $name (ver $OUT/$name.log)"; fail=1; fi; }
check estatico_metodos   python3 tests/check_metodos.py cobdosel/*.py
check v0145              python3 tests/test_v0145.py .
check lote_v013          python3 tests/test_batch_v013.py . "$OUT/lote"
check dialogo_v011       python3 tests/smoke_dialog_v011.py . "$OUT/dialogo" "$QT"
check lote_dialogo_v014  python3 tests/smoke_batch_v014.py . "$OUT/lote_dialogo" "$QT" "$OUT/lote"
check proyeccion_v01422  python3 tests/test_proj_v01422.py . "$OUT/proy" "$QT"
check auditoria_v01423   python3 tests/test_audit_v01423.py . "$OUT/auditoria" "$QT"
check lente_v01426       python3 tests/test_lens_v01426.py . "$OUT/lente" "$QT"
check calibracion_v01427 python3 tests/test_cal_v01427.py . "$OUT/calibracion" "$QT"
check medicion_v01430    python3 tests/test_measure_v01430.py . "$OUT/medicion" "$QT"
check zoom_v01431        python3 tests/test_zoom_v01431.py . "$OUT/zoom" "$QT"
check orientacion_v01432 python3 tests/test_orient_v01432.py . "$OUT/orientacion" "$QT"
check focal_v01433       python3 tests/test_focal_v01433.py . "$OUT/focal" "$QT"
check revision_zoom_v01433 python3 tests/test_review_zoom_v01433.py . "$OUT/revision_zoom" "$QT"
check modelo_v01434      python3 tests/test_projsync_v01434.py . "$OUT/modelo" "$QT"
# Pruebas con fotos reales (no incluidas en el repositorio): COBDOSEL_FOTOS=<carpeta>
if [ -n "${COBDOSEL_FOTOS:-}" ]; then
  check area_v01435        python3 tests/test_area_v01435.py . "$OUT/area" "$QT" "$COBDOSEL_FOTOS"
  check consistencia_v01423 python3 tests/consistency_v01423.py . "$OUT/consistencia" "$QT" "$COBDOSEL_FOTOS"
fi
exit $fail
