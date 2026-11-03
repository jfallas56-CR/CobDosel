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
| `check_unbound.py` | (en run_all.sh como «sin_variables») Heurística: variables asignadas en un `try` y usadas después de un `except` que no sale |
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
| `test_sync_v01438.py` | Escenarios: la lista de modelos y el modelo del análisis nunca difieren (tipo de lente, radio de GLAMA, ojo de pez detectado); corte desactualizado |
| `test_review_v01438.py` | Correcciones de la revisión independiente: centro en «Revisar cortes…», aceptación en bloque, filtro de calidad, medición en otra foto, sin calibración, nombres de modelo, Lineal imposible, foto girada |
| `test_respuesta_v01438.py` | El resultado responde a cada entrada (corte, máscara, modelo, D, H); parámetros incoherentes rechazados; Otsu |
| `test_hechos_v01438.py` | Hechos verificados (lecturas de la app GLAMA, Pixel 10 con tres círculos, decisiones) y revisión de textos |
| `test_teclado_v01439.py` | Intro no pulsa botones (medición, corte, ventana principal); flechas; quitar puntos (clic derecho, Supr, botón) |
| `test_heic_v01439.py` | Fotos HEIC del iPhone en el lote sin abrir la ventana principal; mensaje sin «pillow-heif» |
| `test_v01447.py` | Informes sin autor; informe de una foto en español, por grupos, con el motivo del corte no comprobado; cielo no uniforme junto al resultado del sitio (informe y panel) |
| `test_v01448.py` | «Analista» en ventanas, informe y CSV; informe de una foto con sitio, analista y créditos al final; anillos con letra mayor y leyenda arriba (o franja); lote sin máscara por altura ni «5 = Centro…»; cielo «Verificadas por…»; tabla de parcelas |
| `test_v01461.py` | Formulario desde las fotos: nota solo en parcelas de más de 20 min; singular y plural de las decisiones guardadas |
| `test_v01462.py` | Sitio = media de todas las fotos válidas con 2 decimales (datos reales 4 × 5: 79,18); parcela con 3 fotos; redondeo 70,005 → 70,01; informe y CSV |
| `test_v01463.py` | Funciones de GLAMA retiradas (radio, geometría de pantalla, tabla); calibración antigua con aviso; CSV con «;» y coma decimal; avisos sin repetir el cielo ni «Resultado provisional»; pie con contacto; sin «⚠» |
| `test_v01464.py` | Apertura, cierre y referencia de GLAMA solo en el CSV; sin «NO es cobertura»; nota del densiómetro (±8 puntos con 100 lecturas); tiempo de procesamiento del lote |
| `test_v01465.py` | Informe de una foto con todo lo de «calibración y máscara» del panel: cámaras y comprobación de lente, n.º de anillos |
| `test_v01466.py` | Ayuda «Anillos del informe»; pesos del CaCo por anillo; ejemplo de varios estratos (97,66 %) |
| `test_v01467.py` | «No aplica» en celdas sin valor; LAI solo con ojo de pez de 180°; sin glama_engine ni CaCo lineal; calibración sin R rechazada; residuo del ajuste en el CSV |
| `test_v01468.py` | Nota «se registra como copa o cielo»; GNSS; «Sin datos» en latitud, longitud y altitud; valores del informe a la derecha |
| `test_v01469.py` | Avisos de consistencia por parcela (días, 20 min, rango > 30 puntos); pie del lote igual al de una foto; «Cámara:» y «Canal de color:» |
| `test_v01470.py` | Sin CaCo modificado; «Sí»/«No»; «Sin cielo suficiente»; nota de cielo fragmentado |
| `test_suelo_v01500.py` | Cobertura del suelo: Canopeo y ExG − ExR, cuadro enderezado, área fija, cuadrícula de puntos, IC de Wilson, diálogo, CSV, informe y menú |
| `test_suelo_v01501.py` | Cobertura del suelo: verde sombreado opcional (V), anillos con cruz, siguiente sin clasificar, semilla, aviso antes de descartar, modo y esquinas |
| `test_suelo_v01515.py` | Aviso «a revisar»: dos valores, parte dudosa, por qué se informa Canopeo, texto según qué regla da más verde, ventana (tecla C) e informe (imagen) |
| `test_suelo_v01514.py` | «Cargar clasificación de un CSV…»: área del CSV de foto, clases propias creadas, clasificación completa y a medias, grupos, errores (otra foto, sin área, clase automática distinta, modo reglamentario) |
| `test_suelo_v01513.py` | Grupos de clases: suma e IC de Wilson de la suma, errores, clases quitadas, CSV, informe, ventana «Grupos de clases», guardado y resumen |
| `test_suelo_v01512.py` | Modo reglamentario (rechazos, excepción a «No identificable», activar con violaciones, registro), «Cargar área y cuadrícula de un CSV…», «Comparar clasificaciones» (kappa del ejemplo del protocolo, errores, área distinta, ventana, ir al punto, informe) |
| `test_meta_v01511.py` | metadata.txt: descripción y about con las dos herramientas, sin funciones retiradas, etiquetas de suelo; README de la raíz igual al del complemento y con la versión actual |
| `test_suelo_v01510.py` | Ayuda de cobertura del suelo: «Regla para puntos dudosos» con sus pasos y referencias; versión 0.15.10 coherente |
| `test_suelo_v01509.py` | Área fija: fixed_area_fit y fit_table (Pixel 10, independencia de la resolución), tablas de la ayuda, texto de la ventana (cabe, sin margen, no cabe, calibración no rectilínea), foto 16:9 con calibración 4:3 rechazada |
| `test_suelo_v01508.py` | Cursor en cruz y líneas guía (solo al marcar esquinas, en las dos ventanas; no en área fija; cruz tras arrastrar); ayuda con buenas prácticas y fotos a evitar |
| `test_suelo_v01507.py` | Cobertura del suelo: diferencias entre las reglas (máscaras, sombreado, tecla C, imagen del informe), aviso «a revisar» nuevo, clases nuevas (núcleo, ventana, guardado, CSV, informe, quitar) |
| `test_suelo_v01506.py` | Cobertura del suelo: «Siguiente» asigna la clase marcada (primera vez solo muestra), la clase se mantiene, otra clase marcada se asigna, «Saltar» (S), punto ya clasificado no cambia, contador y número del punto |
| `test_suelo_v01505.py` | Calibración con baldosas: «Usar y guardar esta calibración…», nombre propuesto, guardado desde la ventana principal y desde «Cobertura del suelo», cancelar deja la calibración activa sin guardar |
| `test_suelo_v01504.py` | Flechas del teclado mueven la vista (10 %; Mayús 50 %) en «Cobertura del suelo» y «Calibrar con baldosas»; centro dentro de la imagen; foco en el lienzo al cargar; 1–5 y +/− siguen funcionando |
| `test_suelo_v01503.py` | Calibración con baldosas: f exacta con cámara inclinada, dos alturas cancelan el punto de medición, errores claros, círculo equivalente «Rectilínea», ventana, ventana principal y guardado desde «Cobertura del suelo» |
| `test_suelo_v01502.py` | Cobertura del suelo: N avanza y salta, 1–5 clasifican y pasan al siguiente, zoom (botones y +/−), arrastre sin clasificar, pestaña «Ayuda» |
| `test_v01460.py` | Aviso de cielo no uniforme según la verificación de cortes; plantilla del formulario con instrucciones actuales |
| `test_v01459.py` | Lote: una exportación por clic (doble clic, barra espaciadora y llamadas repetidas descartadas); mensaje con la carpeta una vez |
| `test_v01457.py` | Tabla de parcelas: «—» en Mín. y Máx. con una sola foto válida; el CSV conserva los números |
| `test_v01456.py` | Decisión guardada: «cielo no uniforme» una sola vez en Observaciones; motivo sin «protocolo de campo» |
| `test_v01455.py` | Parámetros del informe del sitio: nombres legibles, sin «None», fecha sin microsegundos; el CSV conserva las claves |
| `test_v01452.py` | Sin limpieza morfológica en ventanas, análisis, informe y CSV; mismo CaCo en una foto y en el lote; el complemento se importa sin scipy |
| `test_v01451.py` | Cielo abierto: apertura de GLAMA = área analizada / referencia (44.5 % con 63°), foto = ángulo sólido del encuadre, misma base en el informe, nota metodológica única, columnas nuevas del CSV |
| `test_v01450.py` | Sin globo de ayuda sobre la foto en la vista previa del nivel de corte ni al medir el círculo |
| `test_v01449.py` | «Recomendado (log-normal)» en la vista previa: mismo corte que el botón principal (fotos reales), resolución completa, motivos al informe; CaCo como estimación |
| `test_v01446.py` | Avisos comunes con su alcance («Todas las fotos…»), etiquetas breves por foto, un aviso si ninguna parcela tiene fotos válidas; cielo no uniforme «a revisar» (con `COBDOSEL_FOTOS_CIELO`, 7 fotos reales) |
| `test_v01445.py` | Informe del lote: observaciones en segunda fila, parámetros legibles, sin cita en el encabezado; decisiones guardadas con fecha y operador; «Borrar revisión guardada…» |
| `test_v01444.py` | Comprobación de la cámara antes de procesar el sitio: propone la calibración guardada que coincide (Sí), procesar igual (No) o cancelar; sin calibración de esa cámara pide calibrarla |
| `test_v01443.py` | Operador en la ventana del lote (parámetros, panel, CSV, revisión) y puntos «Foto N» sin avisos falsos (sin formulario, 1, 3 y 5 fotos por parcela) |
| `test_v01442.py` | Uniformidad del cielo, motivo «separa dos brillos del cielo», lote sin formulario ni número de parcelas, ventana del lote redimensionable, revisión: pregunta por cortes sin aceptar, guardado al aceptar, opacidad; con `COBDOSEL_FOTOS_CIELO`, las 14 fotos de prueba |
| `consistency_v01423.py` | Coherencia del análisis con fotos reales (requiere fotos reales) |

Las dos últimas pruebas necesitan fotos reales, que no se incluyen en el repositorio: `COBDOSEL_FOTOS=<carpeta> bash tests/run_all.sh PyQt5`.

Las pruebas no sustituyen la verificación manual en QGIS 3.x y 4.x antes de publicar.
