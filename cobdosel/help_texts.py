"""Textos de ayuda (corta y completa) de CobDosel, en español.

Autor: Jorge Fallas (jfallas56@gmail.com)
"""

SHORT_HELP_TOPICS = {
    "resumen": """
<h3>Guía rápida — CobDosel v__VERSION__</h3>
<p><b>CobDosel</b> (cobertura del dosel) estima en QGIS la <b>cobertura del dosel</b> a partir de fotografías cenitales con el método de <b>Tichý (2016)</b> (<a href="https://doi.org/10.1111/jvs.12350">doi:10.1111/jvs.12350</a>): <b>Índice CaCo</b>, Índice CaCo Modificado, apertura/cierre del dosel y LAI efectivo.</p>
<ol>
  <li><b>1. Imagen:</b> fotografía tomada con el teléfono nivelado, apuntando al cenit.</li>
  <li><b>2. Calibración:</b> círculo de diámetro conocido <i>D</i> a la distancia <i>H</i> (recomendado: dos diámetros E–O y N–S), o el radio del hemisferio de la app GLAMA.</li>
  <li><b>3. Nivel de corte (1–254):</b> elija un criterio objetivo (recomendado log-normal, o automático: Mínimo u Otsu) y úselo en todas las fotos.</li>
  <li><b>4. Máscara de horizonte:</b> Tichý (2016) recomienda <b>&gt; 45°</b> sobre el horizonte; o la Tabla 1 (Tichý 2015). El valor es el ángulo <i>sobre el horizonte</i>: 60° analiza el cenit 0–30°. Con la lente normal de un teléfono la foto llega a ≈ 30° del cenit en los bordes cortos, por lo que se recomienda <b>60°</b> (con 45° ≈ 30 % del círculo queda fuera de la foto).</li>
  <li><b>5. Ejecutar</b> y exportar el informe HTML y el CSV.</li>
</ol>
<p><b>Sitios completos:</b> menú <i>CobDosel → Procesamiento por sitio (lote)</i> (parcelas × fotos, formulario de fotos).</p>
<p><b>Valor de cobertura:</b> el <b>Índice CaCo</b> es la cobertura del dosel (proyección vertical). El <i>cierre</i> del dosel no es cobertura.</p>
<hr/>
<p><b>Autor:</b> Jorge Fallas — <a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a></p>
""",
    "imagen": """
<h3>1. Imagen y metadatos EXIF</h3>
<ul>
  <li><b>Toma:</b> teléfono nivelado, lente hacia el cenit, cielo nublado o sin sol directo.</li>
  <li><b>Protocolo de campo:</b> cielo uniformemente nublado, o temprano en la mañana o al final de la tarde; nunca el sol en el encuadre (el sol directo sobreexpone el cielo y los bordes de las hojas). Tome varias fotos por parcela y promedie: Bianchi et al. (2017) obtuvieron mejores resultados promediando dos fotos por punto que con una sola.</li>
  <li><b>Formato:</b> use el JPEG original del teléfono (conserva EXIF, GPS y orientación).</li>
  <li><b>Orientación EXIF:</b> se aplica al cargar la imagen (análisis, medición y vistas) y se registra en el informe. La dirección 1 de la máscara por direcciones es el borde superior de la imagen ya orientada. Algunos visores no la aplican igual: la misma foto puede verse girada 90° o 180° entre el visor y CobDosel.</li>
  <li><b>Orientación con el teléfono hacia el cenit:</b> el teléfono no sabe dónde está «arriba» y la orientación guardada es prácticamente aleatoria. No afecta CaCo, apertura ni LAI; sí la tabla por sectores (S1 = borde superior). Si los sectores importan, fije la orientación en el campo (p. ej. parte superior del teléfono al norte) y registre el rumbo.</li>
  <li><b>Recorte en los bordes cortos:</b> con máscara de 60° y lente normal el círculo de análisis es apenas más ancho que el lado corto (≈ 0,2 % fuera de la foto): se recorta a izquierda y derecha en fotos verticales y arriba y abajo en horizontales. Con 60,4° o más queda completo.</li>
  <li><b>GPS y rumbo:</b> latitud, longitud, altitud y, si existe, el rumbo de la brújula (GPSImgDirection) pasan al informe, al CSV y a la capa de puntos.</li>
</ul>
""",
    "calibracion": """
<h3>2. Calibración del lente</h3>
<ul>
  <li><b>Círculo de referencia (recomendado):</b> fotografíe un círculo de diámetro <i>D</i> a la distancia <i>H</i>, <b>centrado</b> en la foto y con el teléfono paralelo al círculo. Con el modelo «Lineal» la calibración es exacta en el ángulo del borde del círculo: elija <i>D</i> para que ese borde quede a 20–25° del cenit (a <i>H</i> = 40 cm, <i>D</i> ≈ 30–35 cm), cerca de lo que se analiza. Los círculos de 5–20 cm de GLAMA sirven si se acerca el teléfono: <i>H</i> = <i>D</i>/(2·tan 22°), p. ej. 20 cm a ≈ 25 cm (mida <i>H</i> con cuidado: a menor distancia, el error pesa más).</li>
  <li><b>Con la cámara normal del teléfono (1,0x):</b> «Lente regular / smartphone» + «Lineal»; «Rectilínea» si la prueba de dos círculos lo indica. Los modelos de ojo de pez son solo para lentes ojo de pez.</li>
  <li><b>Procedimiento:</b> soporte rígido con orificio para la cámara; <i>H</i> medida desde el vidrio de la cámara hasta el papel (4 mm ≈ 1 % a 40 cm); nivel de burbuja en el soporte y el suelo; centre con una plomada o la cuadrícula; luz pareja sin sombras; 1,0x, sin encuadre automático ni recortes, misma app y resolución que en el campo, temporizador de 3 s. Mida con <b>ajuste de círculo</b> y 8 puntos.</li>
  <li><b>Prueba con dos círculos</b> (una vez por modelo): dos círculos concéntricos en el mismo papel y una sola foto; calibre cada uno con «Lineal» y compare R (resumen de la calibración). Con 12,2 y 33 cm a 40 cm: diferencia entre −1,5 % y +1,5 % → «Lineal»; entre +3,5 % y +6 % → la lente es rectilínea, use «Rectilínea»; entre +1,5 % y +3,5 % → «Lineal» calibrado con el círculo grande. Confirmación: con «Rectilínea» los dos círculos deben dar la misma <i>f</i> (± 1 %).</li>
  <li><b>Tipo de lente:</b> «Ojo de pez (circular 180°)» si la foto muestra el círculo de imagen completo con el horizonte en su borde (se detecta con la transformada de Hough, θ = 90° en el borde); «Lente regular / smartphone» para la cámara normal del teléfono, calibrada con el círculo D/H. Elija primero el tipo de lente: al cambiarlo se restablece el modelo (Polar o Lineal).</li>
  <li><b>Modelo de proyección</b> (cómo crece el ángulo cenital θ con la distancia r al centro): <b>Lineal</b> (θ ∝ r; por defecto para teléfonos, exacto en el borde del círculo de calibración); <b>Rectilínea</b> (r = f·tan θ; geometría de la cámara principal de casi todos los teléfonos); <b>Polar</b> (r = f·θ), <b>Equisólida</b> (r = 2f·sin(θ/2)), <b>Ortográfica</b> (r = f·sin θ) y <b>Estereográfica</b> (r = 2f·tan(θ/2)) son para lentes ojo de pez. Con la cámara del teléfono, un círculo pequeño (12,2 cm a 40 cm) y «Lineal» desplazan el borde de 30° unos 2,8°; con un círculo de 33 cm, unos 1,4°; con «Rectilínea», 0°. El modelo queda guardado en la calibración y se informa en el reporte.</li>
  <li><b>Medir:</b> modo <b>dos diámetros E–O y N–S</b> (4 puntos) o <b>ajuste de círculo</b> (≥ 5 puntos). Se informa la diferencia entre diámetros (≤ 1 %), el residuo y el desplazamiento del centro.</li>
  <li><b>Recomendaciones para la medición:</b>
    <ul>
      <li>Use la <b>foto original de la cámara</b>, sin recortar ni redimensionar, tomada con la misma app y configuración que las fotos del dosel.</li>
      <li>Ajuste de círculo: <b>8 puntos, uno cada 45°</b>, repartidos en al menos ¾ del círculo (con puntos en un solo arco el ajuste es inestable).</li>
      <li>Haga clic en el <b>centro de la línea</b> del círculo, con zoom, siempre igual.</li>
      <li>Mida <b>H</b> con cuidado (del lente al papel): 1 cm de error a 50 cm es un 2 % de error en R, más que el error de los clics.</li>
      <li>Evite sombras sobre la línea del círculo.</li>
    </ul></li>
  <li><b>Dos diámetros:</b> marque los extremos izquierdo–derecho y superior–inferior <b>del propio círculo</b>, no sobre las guías cian. El diámetro y el centro son los del círculo que pasa por los 4 puntos; si las dos líneas no se cruzan en su punto medio se avisa (una línea no es un diámetro).</li>
  <li><b>Guías:</b> las líneas cian marcan el centro de la <i>foto</i>; el círculo medido, su centro (+) y la línea de desplazamiento se dibujan en naranja. Desplazamiento ≤ 5 %: correcto; 5–15 %: aviso informativo, la calibración es usable; &gt; 15 %: repita la foto.</li>
  <li><b>Radio R:</b> tras calibrar se muestra el radio del hemisferio R (px de la foto) y el % del ancho que ocupa el círculo de referencia. Compruebe que son razonables antes de analizar.</li>
  <li><b>Radio de GLAMA:</b> también puede calibrar con el «Hemisph. radius» de la app. «Lado menor» reproduce los resultados de GLAMA; la geometría correcta es la del círculo D/H.</li>
  <li><b>Fórmula:</b> geometría exacta <code>atan(D/2H)</code>.</li>
  <li><b>Guardar/Cargar:</b> la calibración guarda la foto y el tamaño en que se midió; al cargarla en una foto de otra proporción se avisa.</li>
</ul>
""",
    "umbral": """
<h3>3. Nivel de corte entre píxeles claros y oscuros</h3>
<ul>
  <li><b>Canal:</b> Azul + Rojo (recomendado) o Azul.</li>
  <li><b>Recomendado (log-normal):</b> nivel de corte en el cruce de dos distribuciones log-normales ajustadas a los modos oscuro (dosel) y claro (cielo) del histograma del área analizada; objetivo y reproducible. Implementación independiente en Python del procedimiento del nivel de corte recomendado de la app GLAMA (Tichý 2016), reconstruido a partir de la app y verificado con sus resultados. La búsqueda de los dos modos parte de 128 (convención de CobDosel; busca en ambos sentidos, el corte puede quedar por debajo o por encima) e itera hasta estabilizarse; cada foto obtiene su propio nivel. Se comprueba que el método funcionó (como en el lote, §9); si no, se avisa y el método queda como «no comprobado». Pasos: Ayuda completa §10.</li>
  <li><b>Automático:</b> elija el método y pulse «Calcular». <b>Otsu</b> (1979) maximiza la varianza entre clases. <b>Mínimo</b> (Prewitt y Mendelsohn 1966) suaviza el histograma hasta dejar dos modos (dosel y cielo) y corta en el mínimo entre ellos; fue el más acertado en la comparación de Glatthorn y Beckschäfer (2014) y es más robusto con cielo sobreexpuesto. Si no hay dos modos, o uno de los lados del corte tiene menos del 0,5 % de los píxeles (foto sin cielo o sin dosel), se usa Otsu y se avisa.</li>
  <li><b>Vista previa:</b> compruebe que los claros no se clasifican como dosel ni al revés; modo <b>Claro</b> (cielo en color) u <b>Oscuro</b> (dosel en rojo), con la misma opacidad.</li>
  <li><b>Inspector de píxeles:</b> en la vista previa, al mover el puntero se muestra el valor del píxel en el canal elegido, el corte, si cuenta como cielo o dosel y a cuántas unidades está del corte. Útil para decidir si un píxel claro de una ramilla está cerca del corte o claramente por debajo.</li>
  <li><b>Consistencia:</b> use el mismo criterio en todas las fotos y regístrelo; en fotos de dosel denso el criterio puede cambiar la cobertura varios puntos.</li>
  <li><b>Limpieza morfológica:</b> desactivada por defecto (elimina claros reales de 1–2 px).</li>
</ul>
""",
    "glama": """
<h3>4–6. Máscara, métricas y visualización</h3>
<ul>
  <li><b>Máscara de horizonte:</b> el análisis llega hasta la máscara (también en las esquinas de la foto). Si el círculo de análisis queda parcialmente fuera de la foto se informa el % visible: los píxeles fuera de la foto se excluyen.</li>
  <li><b>Índice CaCo:</b> transmitancia de cada anillo de 1/90 del radio llevada a la vertical (<code>T<sup>cos θ</sup></code>) y ponderada por <code>sin θ · cos θ</code>. Es la cobertura del dosel.</li>
  <li><b>CaCo frente a fracción de claros:</b> la fracción de claros es un conteo de píxeles sin ponderar por el ángulo cenital; no es la cobertura ni se compara con la «apertura del dosel» de otros estudios (con fotos de teléfono, el conteo sin ponderar fue 165 % de la apertura ponderada en Bianchi et al. 2017).</li>
  <li><b>Sectores:</b> fracción de claros por anillo × sector de acimut (S1 arriba, horario).</li>
  <li><b>Geometría de pantalla de GLAMA:</b> opción solo para estudios de transición; reproduce los sesgos de la app.</li>
  <li><b>Anillos cenitales:</b> anillos cada 5° o 10° con etiqueta, cielo en naranja, zona enmascarada en verde azulado, contorno de la máscara y sectores.</li>
  <li><b>LAI efectivo:</b> rango cenital propio (por defecto 0–60°); con rangos &lt; 45° es indicativo.</li>
</ul>
""",
}

FULL_HELP_HTML = """
<h2>Manual de usuario y metodología — CobDosel v__VERSION__</h2>
<p><b>CobDosel</b> — cobertura del dosel a partir de fotografías (basado en Tichý 2016).<br/>
<b>Autor del complemento:</b> Jorge Fallas (<a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a>)<br/>
<b>Método:</b> Lubomír Tichý (2016), <i>Field test of canopy cover estimation by hemispherical photographs taken with a smartphone</i>, Journal of Vegetation Science 27(2): 427–435 (<a href="https://doi.org/10.1111/jvs.12350">doi:10.1111/jvs.12350</a>).</p>

<hr/>
<h3>1. Cobertura y cierre del dosel</h3>
<p>La <b>cobertura del dosel</b> (<i>canopy cover</i>) es la proporción del suelo cubierta por la proyección vertical del dosel; el <b>cierre del dosel</b> (<i>canopy closure</i>) es la proporción del hemisferio celeste obstruida vista desde un punto (Jennings et al., 1999). La fotografía mide <i>canopy cover</i>: los huecos dentro de las copas cuentan como abiertos, por lo que da valores menores que la «cobertura de copas» que trata cada copa como opaca (Korhonen et al., 2006).</p>
<p><b>Valor de cobertura:</b> el <b>Índice CaCo</b> (proyección vertical), no el cierre.</p>

<hr/>
<h3>2. Fundamento (Tichý, 2016)</h3>
<ul>
  <li>El <b>Índice CaCo</b> lleva la transmitancia de cada anillo a la vertical (<code>T<sup>cos θ</sup></code>) y la pondera por proyección horizontal (<code>sin θ · cos θ</code>).</li>
  <li>Con una <b>máscara de horizonte &gt; 45°</b> sobre el horizonte (cenit ≤ 45°), la relación con la cobertura visual tiene intercepto ≈ 0 y pendiente ≈ 1.</li>
  <li>El índice es poco sensible al modelo de cámara o teléfono.</li>
</ul>

<hr/>
""" + """
<h3>3. Tabla 1: Ángulos de Máscara de Horizonte según Parcela y Altura del Dosel</h3>
<p>Cuando la fotografía se toma desde el centro de una parcela cuadrada, Tichý (2015) recomienda los siguientes ángulos de máscara sobre el horizonte (y entre paréntesis su ángulo cenital máximo equivalente <code>θ_máx = 90° − horizonte</code>):</p>
<table border="1" cellspacing="0" cellpadding="6" style="border-collapse: collapse; width: 100%; text-align: center;">
  <tr style="background-color: #e6f2f5;">
    <th>Tamaño de parcela</th>
    <th>Altura dosel 10 m</th>
    <th>Altura dosel 15 m</th>
    <th>Altura dosel 20 m</th>
    <th>Altura dosel 30 m</th>
    <th>Altura dosel 40 m</th>
  </tr>
  <tr>
    <td><b>10 × 10 m</b></td>
    <td>55° (cenit 35°)</td>
    <td>65° (cenit 25°)</td>
    <td>71° (cenit 19°)</td>
    <td>77° (cenit 13°)</td>
    <td>80° (cenit 10°)</td>
  </tr>
  <tr>
    <td><b>15 × 15 m</b></td>
    <td>44° (cenit 46°)</td>
    <td>55° (cenit 35°)</td>
    <td>63° (cenit 27°)</td>
    <td>71° (cenit 19°)</td>
    <td>76° (cenit 14°)</td>
  </tr>
  <tr>
    <td><b>20 × 20 m</b></td>
    <td>36° (cenit 54°)</td>
    <td>47° (cenit 43°)</td>
    <td>55° (cenit 35°)</td>
    <td>65° (cenit 25°)</td>
    <td>71° (cenit 19°)</td>
  </tr>
  <tr>
    <td><b>25 × 25 m</b></td>
    <td>30° (cenit 60°)</td>
    <td>41° (cenit 49°)</td>
    <td>49° (cenit 41°)</td>
    <td>60° (cenit 30°)</td>
    <td>67° (cenit 23°)</td>
  </tr>
</table>
""" + """

<hr/>
<h3>4. Resultados</h3>
<table border="1" cellspacing="0" cellpadding="6" style="border-collapse: collapse; width: 100%;">
  <tr style="background-color: #e6f2f5;"><th>Resultado</th><th>Definición</th></tr>
  <tr><td><b>N.º de píxeles en el círculo (en el fotograma)</b></td><td>Píxeles del círculo virtual de 90° (π·R²) y, entre paréntesis, los que caen dentro de la foto.</td></tr>
  <tr><td><b>N.º de píxeles claros (oscuros)</b></td><td>Claros no enmascarados; oscuros = total del círculo − claros.</td></tr>
  <tr><td><b>Fracción de claros del área seleccionada</b></td><td>Claros / total de píxeles del círculo virtual (verificado con resultados publicados de la app GLAMA). Se informa también la fracción sobre el área analizada sin máscara.</td></tr>
  <tr><td><b>Fracción del hemisferio captada</b></td><td>Fracción visible de cada anillo de 1° ponderada por ángulo sólido (≈ 62 % con fotos de teléfono 4:3).</td></tr>
  <tr><td><b>Apertura / cierre del dosel</b></td><td>Cielo abierto / hemisferio completo (lo enmascarado cuenta como obstruido); cierre = 100 − apertura. También la apertura del área analizada.</td></tr>
  <tr><td><b>Índice CaCo</b> (cobertura del dosel)</td><td><code>100 · (1 − Σ T<sup>cos θ</sup>·sin θ·cos θ / Σ sin θ·cos θ)</code> sobre anillos de 1/90 del radio; los anillos sin claros no entran en las sumas, como en GLAMA. Reproduce los valores publicados de la app (≤ 0.02 pts).</td></tr>
  <tr><td><b>Índice CaCo Modificado</b></td><td>Misma conversión, ponderada solo por <code>sin θ</code>; con lentes de teléfono es casi igual al CaCo.</td></tr>
  <tr><td><b>CaCo lineal (versiones ≤ 0.10)</b></td><td>Índice de versiones anteriores, solo para comparar con resultados antiguos; no lo use como cobertura.</td></tr>
  <tr><td><b>LAI efectivo</b></td><td>Miller (1967) normalizado al rango cenital observado (por defecto 0–60°).</td></tr>
  <tr><td><b>Círculo de análisis visible</b></td><td>% del círculo de la máscara dentro de la foto; si es &lt; 100 %, parte del círculo se excluye.</td></tr>
  <tr><td><b>Tabla por sectores</b></td><td>Fracción de claros por anillo × sector de acimut (S1 = arriba, sentido horario).</td></tr>
</table>
<p><b>Valor que se informa como cobertura:</b> el <b>Índice CaCo</b>, ponderado por el ángulo cenital. La fracción de claros es un conteo de píxeles sin ponderar: con fotos de teléfono, Bianchi et al. (2017) hallaron que ese conteo («total gap») fue en promedio 165 % de la apertura del dosel ponderada de una cámara hemisférica tradicional (diferencia media 0.12), mientras que la apertura calculada con ponderación angular sobre fotos de teléfono unidas fue 102 % (diferencia 0.004). Por eso la fracción de claros no debe usarse como cobertura ni compararse con la apertura del dosel de otros estudios.</p>

<hr/>
<h3>5. Calibración</h3>
<ul>
  <li><b>Círculo D/H:</b> el círculo debe estar centrado y el teléfono paralelo a él. Mida dos diámetros (E–O, N–S; diámetro y centro del círculo que pasa por los 4 puntos, con aviso si las líneas no se cruzan en su punto medio) o ajuste un círculo a ≥ 5 puntos; tolerancias: diferencia ≤ 1 %, residuo ≤ 0.5 %, arco cubierto por los puntos ≥ 180°.</li>
  <li><b>Una calibración por modelo de teléfono:</b> la calibración describe la lente y el sensor, no el protocolo; «1,0x» no es igual entre modelos (lentes principales de ≈ 23 a 28 mm equivalentes, distinta resolución y proporción, recortes en algunos modos). Se puede compartir entre teléfonos del <i>mismo modelo</i> con la misma app, resolución y 1,0x (compruebe que R coincide dentro de 1–2 %); cada otro modelo se calibra. La calibración guarda la huella EXIF de la cámara: las fotos de otro teléfono reciben un aviso o se excluyen en el lote. Usar la de otro modelo introduce un error sistemático (≈ 1–2 puntos de CaCo con 5–10 % de diferencia en R). Guarde cada calibración con el nombre del modelo y la toma (p. ej. «Pixel10_1x_H40»).</li>
  <li><b>Foto del círculo:</b> la foto original de la cámara (sin recortar ni redimensionar), con la misma app y configuración que las fotos del dosel. Una foto recortada cambia la proporción del fotograma y CobDosel no puede convertir la medición («Proporción distinta»).</li>
  <li><b>Distribución y número de puntos (ajuste de círculo):</b> con un error de clic de ± 2 px, el error del radio es ≈ σ/√n con puntos repartidos: 0.17 % con 5 puntos, 0.13 % con 8 y 0.10 % con 16. La <b>distribución</b> pesa más que el número: con 8 puntos, 270° del círculo dan el mismo resultado que el círculo completo; 180° duplican el error; 90° lo multiplican por ocho y en arcos cortos el radio se subestima. Recomendado: 8 puntos, uno cada 45°, en el centro de la línea. Los errores sistemáticos (clic en el borde interior o exterior de la línea, distancia H mal medida) no se reducen con más puntos.</li>
  <li><b>Círculo desplazado:</b> la calibración usa solo el diámetro en píxeles. Con lente regular y el teléfono paralelo al círculo, un desplazamiento no cambia el diámetro (solo lo mueve en la imagen); con ojo de pez lo reduce ligeramente (≈ 0.2 % con 5 %, ≈ 0.5 % con 7.8 %, ≈ 1.8 % con 15 % del diámetro). Por eso: ≤ 5 % sin aviso; 5–15 % aviso informativo; &gt; 15 % se recomienda repetir la foto. La <b>inclinación</b> sí afecta: convierte el círculo en elipse (diámetros E–O y N–S distintos).</li>
  <li><b>Medición en otra foto:</b> si mide el círculo en una foto de otra resolución que la de análisis («Medir desde archivo»), el diámetro se reescala automáticamente. Un diámetro escrito a mano se registra como «manual».</li>
  <li><b>Fórmula:</b> geometría exacta <code>atan(D/2H)</code>. La aproximación <code>atan(D/H)/2</code> sobrestima el radio (+1 % con D/H = 0,2; +10,6 % con 0,714) y ya no se ofrece; las calibraciones antiguas que la usaron se siguen leyendo.</li>
  <li><b>Radio de GLAMA:</b> R_foto = R_GLAMA × lado / 1080. «Lado menor» reproduce los resultados de GLAMA.</li>
</ul>

<hr/>
<h3>6. Diferencias conocidas con la app GLAMA</h3>
<ul>
  <li><b>Recorte cuadrado:</b> la pantalla de análisis de GLAMA muestra el recorte cuadrado central de la foto (1080 px = lado menor), mientras que la pantalla de calibración puede mostrar la foto a lo ancho; en fotos 4:3 la escala difiere en 4/3 y GLAMA sobrestima los ángulos cenitales.</li>
  <li><b>Franja negra:</b> si el círculo de la máscara sale de la foto, GLAMA cuenta la franja negra de su vista como dosel; CobDosel la excluye e informa el % visible.</li>
  <li><b>Resolución:</b> GLAMA clasifica la imagen reducida de su pantalla; CobDosel usa la foto original.</li>
  <li><b>Centro desplazado:</b> en la vista de GLAMA el centro del hemisferio está ≈ 39 px (de 1080) por debajo del centro de la foto; por eso aparece la franja negra solo abajo. El modo «geometría de pantalla de GLAMA» lo reproduce (valor ajustable).</li>
  <li>Con la misma geometría, CobDosel y GLAMA coinciden en ≈ 1–2 puntos de CaCo en las pruebas del autor; la opción «geometría de pantalla de GLAMA» permite estudios pareados de transición.</li>
</ul>

<hr/>
<h3>7. Alcance, validación y convenciones</h3>
<ul>
  <li><b>Fidelidad al método:</b> los índices de Tichý (2016) se reproducen exactamente en casos de prueba y con valores publicados de la app GLAMA.</li>
  <li><b>Máscara por direcciones:</b> 1, 4, 8 o 16 direcciones; dirección 1 arriba, sentido horario, interpolación lineal.</li>
  <li><b>Nivel de corte:</b> todos los índices dependen del umbral; fije un criterio y regístrelo.</li>
  <li><b>Nivel de corte recomendado (log-normal):</b> ver §10.</li>
  <li><b>Ventana y nivel de corte:</b> cerrar la ventana de CobDosel solo la oculta; conserva la configuración (incluida la calibración) hasta cerrar QGIS. Al cargar otra foto, el nivel de corte anterior queda marcado como «heredado»: calcúlelo o ajústelo para la foto nueva. El informe registra el método con que se fijó el corte.</li>
  <li><b>Fotos sin dos modos claros</b> (cielo gris entre ramas finas): los métodos automáticos pueden discrepar mucho. En una foto de prueba, Otsu (97), el recomendado (203, no comprobado) y Mínimo (222) dieron CaCo de 74.7, 92.8 y 95.1 %. Decida con la vista previa y el inspector de píxeles y deje constancia; Otsu tiende a contar como cielo la banda de píxeles mixtos.</li>
  <li><b>Protocolo de campo:</b> cielo uniformemente nublado, o temprano en la mañana o al final de la tarde, sin el sol en el encuadre. Bianchi et al. (2017) señalan que el cielo nublado del Reino Unido favoreció sus fotos de teléfono y que donde el sol directo es frecuente hay que tomar las mismas precauciones que con la cámara tradicional; en Costa Rica esto aplica plenamente. Tome varias fotos por parcela (el lote usa 5) y promedie.</li>
  <li><b>Comparabilidad:</b> los valores de teléfono y los de cámaras hemisféricas tradicionales (ojo de pez de 180°) no son intercambiables sin un modelo de conversión, y ese modelo depende del lente, del procesamiento y de la especie (Bianchi et al. 2017). Compare CobDosel con otros estudios de teléfono o del Índice CaCo; no aplique a CobDosel los modelos de conversión publicados para otros equipos.</li>
  <li><b>Umbral automático y píxeles mixtos:</b> Bianchi et al. (2017) umbralizaron todas las fotos automáticamente; el método IsoData (Ridler y Calvard 1978) en el canal azul clasificó como cielo muchos elementos pequeños de vegetación, que un método con información de color (EnhanceHP, Díaz y Lencinas 2015) identificó correctamente. Los píxeles mixtos de ramillas y bordes de hojas son la principal fuente de diferencias entre criterios de corte.</li>
  <li><b>Validación pendiente:</b> el método no se ha validado en Costa Rica contra una referencia independiente (p. ej. tubo de observación vertical o LiDAR); se recomienda hacerlo antes de un uso oficial.</li>
  <li><b>Formato numérico:</b> punto decimal y espacio de miles en pantalla e informe; el CSV guarda números sin separador.</li>
</ul>

<hr/>
<h3>8. Procesamiento por sitio (lote)</h3>
<p>Menú <b>CobDosel → Procesamiento por sitio (lote)</b>. Procesa todas las fotos de un sitio con una configuración fija y entrega la cobertura del dosel por parcela y del sitio.</p>
<ul>
  <li><b>Diseño de ejemplo:</b> parcelas circulares de 500 m² (radio 12,62 m); 5 fotos por parcela: Centro y N-O (315°), N-E (45°), S-E (135°), S-O (225°) a 8,9 m del centro. Otros diseños sirven igual: el formulario indica a qué parcela y punto pertenece cada foto. El número de parcelas lo indica el usuario.</li>
  <li><b>Entradas:</b> carpeta con las fotos originales (con el nombre que les dio la cámara o la app; no hay que renombrarlas), formulario de fotos (Excel o CSV), calibración guardada y n.º de parcelas planificadas.</li>
  <li><b>Calibración:</b> la del menú «Calibración guardada». Se crea en el diálogo principal (calibrar con una foto de la misma cámara y pulsar «Guardar calibración»); se guarda en <code>~/.cobdosel/calibrations</code>.</li>
  <li><b>Formulario de fotos:</b> una fila por foto con la parcela, el punto y el <i>ID de fotografía</i> (nombre del archivo sin extensión, p. ej. GLAMA_20260627_135741) o la hora de captura. «Guardar plantilla…» entrega la plantilla vacía; <b>«Crear formulario desde las fotos…»</b> la llena con todas las fotos de la carpeta ordenadas por hora (ID y hora ya escritos) y asigna parcelas y puntos por orden (5 fotos por parcela por defecto): revíselo y corríjalo antes de procesar. Las fotos sin fila se avisan («sin fila en el formulario») y no se usan.</li>
  <li><b>Emparejamiento:</b> por <i>ID de fotografía</i> (nombre del archivo); si falta o no existe, por la <i>hora de captura</i> (DD/MM/AAAA HH:MM:SS, p. ej. 17/10/2026 / 19:49:43) frente a la hora EXIF, dentro de la tolerancia (60 s por defecto) y con el desfase del reloj de la cámara. Se avisan fotos sin fila, filas sin foto y horas discrepantes.</li>
  <li><b>Máscara:</b> por defecto <b>fija en 60°</b> sobre el horizonte (análisis hasta 30° del cenit), la recomendada por Tichý (2016) para CaCo y Modif. CaCo; use el mismo valor en todos los sitios. Opcional: máscara desde la altura del dosel, cenit máximo = atan(radio de la huella / (altura − altura de la cámara)), con la altura de referencia del <i>estrato de dosel dominante</i>: 3 Subdosel 5 a &lt; 15 m → 10 m; 4 Dosel principal 15 a &lt; 30 m → 22,5 m; 5 Copas emergentes &gt; 30 m → 30 m; o una altura escrita a mano. Radio de la huella 6,31 m (cuadrante de la parcela).</li>
  <li><b>Fotos con cámara regular:</b> con máscara de 60° el círculo de 30° del cenit no cabe entero en el lado corto de la foto de un teléfono (≈ 85 % visible). CobDosel excluye la parte fuera de la foto y lo informa por foto.</li>
  <li><b>Nivel de corte:</b> recomendado (log-normal), calculado y comprobado en cada foto (§10); las fotos en que el método no funciona quedan «a revisar» (§9). Limpieza morfológica desactivada.</li>
  <li><b>Cálculo:</b> parcela = media de las fotos válidas disponibles (las de calidad «sol directo», «movida» o «repetir» se excluyen); sitio = media de las medias de parcela (Índice CaCo).</li>
  <li><b>Reemplazos:</b> la columna «reemplaza_a» registra la parcela original sustituida; el informe la muestra como «reemplazo de …».</li>
  <li><b>Cámara y resolución:</b> la calibración guarda la cámara (EXIF: modelo, distancia focal, zoom, proporción). Una foto de la misma lente a otra resolución (2560×1920, 4000×3000) o girada (1920×2560) es válida: la calibración se reescala. Una foto de otra lente (otra distancia focal: gran angular, teleobjetivo), con zoom digital, recortada (16:9, cuadrada) o de otro teléfono se excluye con el motivo. Si la calibración no registra la cámara (guardada antes de 0.12.4) use «Registrar cámara…»: toma la cámara del EXIF de las fotos de la carpeta (solo si la calibración se hizo con esa cámara). Si no la registra y hay fotos de varias lentes, el lote se detiene.</li>
  <li><b>Informes:</b> el CSV y el HTML se proponen en la carpeta de fotos (CobDosel_&lt;sitio&gt;_sitio…); al guardar el HTML se ofrece abrirlo.</li>
  <li><b>Salidas:</b> CSV de fotos, parcelas y sitio; informe HTML; capa de puntos de las parcelas unida por ID a la capa del muestreo.</li>
</ul>

<hr/>
<h3>9. Revisión visual de los cortes (lote)</h3>
<ol>
  <li><b>Pasada automática:</b> cada foto recibe su nivel de corte recomendado (§10) y se comprueba que el método funcionó: un modo oscuro por debajo del corte y uno claro por encima, un mínimo claro entre ambos, al menos 0,5 % de píxeles de cielo y de dosel, y el mismo corte (± 2) desde otros puntos de partida (96, 160, 192). Si algo falla, la foto queda <b>«a revisar»</b> y el resultado del sitio se marca como provisional.</li>
  <li><b>«Revisar cortes…»:</b> foto con el cielo en naranja y la zona enmascarada en verde azulado, zoom, histograma con el corte (rojo) y el automático (azul), control deslizante y CaCo aproximado en vivo. El operador <b>acepta</b>, <b>ajusta</b> (mueve el corte y acepta) o <b>excluye</b> la foto (tronco cercano, sol directo, foto movida). Las fotos «a revisar» deben decidirse; las demás pueden revisarse una a una o aceptarse todas.</li>
  <li><b>Registro:</b> las decisiones se guardan en <code>CobDosel_revision_cortes.json</code> en la carpeta de fotos (al volver a procesar se aplican de nuevo). El CSV registra para cada foto <i>corte_auto</i>, <i>corte</i> final, <i>decision</i> (automático, aceptado, ajustado (227 → 220), excluido, pendiente de revisión), operador y nota; el informe resume «20 fotos: 16 automáticas, 2 revisadas sin cambio, 1 ajustada, 1 excluida».</li>
</ol>

<hr/>
<h3>10. Nivel de corte recomendado (log-normal): procedimiento</h3>
<p>Implementación independiente en Python del procedimiento del nivel de corte recomendado de la app GLAMA (Tichý 2016), reconstruido a partir de la app y verificado con sus resultados. Los pasos son:</p>
<ol>
  <li>Desde un punto de partida, buscar el <b>modo oscuro</b> (hacia abajo) y el <b>modo claro</b> (hacia arriba); cada búsqueda se detiene cuando la frecuencia cae por debajo de 1/10 del máximo hallado.</li>
  <li>Hallar el <b>mínimo de frecuencia</b> entre ambos modos.</li>
  <li>Corregir la distinta cantidad de píxeles a cada lado del mínimo.</li>
  <li>Para cada lado, estimar un <b>centro en escala logarítmica</b> y una <b>dispersión</b>: el lado oscuro medido desde 0 y el claro desde 255 (ajustes log-normales).</li>
  <li>Corte = centro oscuro + (centro claro − centro oscuro) × dispersión oscura / (dispersión oscura + dispersión clara): el punto a igual número de dispersiones de ambos centros.</li>
</ol>
<p>La app GLAMA parte de la posición del control deslizante; CobDosel parte de 128 y repite el procedimiento desde cada resultado hasta que cambia ≤ 1 (máx. 6 pasadas). El fundamento general es la clasificación de dos clases por el cruce de sus distribuciones en el histograma, como el umbral de error mínimo de Kittler e Illingworth (1986); el respaldo, si no hay recomendación, es el método de Otsu (1979).</p>
<p><b>Métodos automáticos alternativos</b> (botón «Calcular»): <b>Otsu</b> (1979) y <b>Mínimo</b> (Prewitt y Mendelsohn 1966, implementación de ImageJ: medias móviles de 3 clases repetidas hasta que el histograma tiene exactamente dos máximos; el corte es el valor más bajo del histograma suavizado entre ambos máximos, y cada lado debe tener al menos el 0,5 % de los píxeles). En la comparación de algoritmos de binarización de fotos hemisféricas de Glatthorn y Beckschäfer (2014) el método del mínimo fue el más acertado; Otsu y el de error mínimo fallaron con cielo sobreexpuesto. El nivel recomendado (log-normal) y el mínimo parten del mismo principio (el valle entre los modos de dosel y cielo); en histogramas bimodales claros sus resultados son cercanos.</p>

<hr/>
<h3>11. Referencias</h3>
<ul>
  <li><b>Tichý, L. (2016).</b> Field test of canopy cover estimation by hemispherical photographs taken with a smartphone. <i>Journal of Vegetation Science</i>, 27(2), 427–435. <a href="https://doi.org/10.1111/jvs.12350">doi:10.1111/jvs.12350</a></li>
  <li><b>Tichý, L. (2015).</b> <i>GLAMA – Gap Light Analysis Mobile App. User's manual, version 3.0</i>. Masaryk University, Brno. <a href="https://www.sci.muni.cz/botany/glama/GLAMA%20manual.pdf">PDF</a></li>
  <li><b>Bianchi, S., Cahalan, C., Hale, S., &amp; Gibbons, J. M. (2017).</b> Rapid assessment of forest canopy and light regime using smartphone hemispherical photography. <i>Ecology and Evolution</i>, 7(24), 10556–10566. <a href="https://doi.org/10.1002/ece3.3567">doi:10.1002/ece3.3567</a></li>
  <li><b>Díaz, G. M., &amp; Lencinas, J. D. (2015).</b> Enhanced gap fraction extraction from hemispherical photography. <i>IEEE Geoscience and Remote Sensing Letters</i>, 12(8), 1785–1789.</li>
  <li><b>Ridler, T. W., &amp; Calvard, S. (1978).</b> Picture thresholding using an iterative selection method. <i>IEEE Transactions on Systems, Man, and Cybernetics</i>, 8(8), 630–632.</li>
  <li><b>Jennings, S. B., Brown, N. D., &amp; Sheil, D. (1999).</b> Assessing forest canopies and understorey illumination: canopy closure, canopy cover and other measures. <i>Forestry</i>, 72(1), 59–74.</li>
  <li><b>Korhonen, L., Korhonen, K. T., Rautiainen, M., &amp; Stenberg, P. (2006).</b> Estimation of forest canopy cover: a comparison of field measurement techniques. <i>Silva Fennica</i>, 40(4), 577–588.</li>
  <li><b>Gonsamo, A., D'Odorico, P., &amp; Pellikka, P. (2013).</b> Measuring fractional forest canopy element cover and openness – definitions and methodologies revisited. <i>Oikos</i>, 122(9), 1283–1291.</li>
  <li><b>Kittler, J., &amp; Illingworth, J. (1986).</b> Minimum error thresholding. <i>Pattern Recognition</i>, 19(1), 41–47.</li>
  <li><b>Prewitt, J. M. S., &amp; Mendelsohn, M. L. (1966).</b> The analysis of cell images. <i>Annals of the New York Academy of Sciences</i>, 128(3), 1035–1053.</li>
  <li><b>Glatthorn, J., &amp; Beckschäfer, P. (2014).</b> Standardizing the protocol for hemispherical photographs: accuracy assessment of binarization algorithms. <i>PLoS ONE</i>, 9(11), e111924. <a href="https://doi.org/10.1371/journal.pone.0111924">doi:10.1371/journal.pone.0111924</a></li>
  <li><b>Kåsa, I. (1976).</b> A circle fitting procedure and its error analysis. <i>IEEE Transactions on Instrumentation and Measurement</i>, IM-25(1), 8–14.</li>
  <li><b>Otsu, N. (1979).</b> A threshold selection method from gray-level histograms. <i>IEEE Transactions on Systems, Man, and Cybernetics</i>, 9(1), 62–66.</li>
  <li><b>Miller, J. B. (1967).</b> A formula for average foliage density. <i>Australian Journal of Botany</i>, 15(1), 141–144.</li>
</ul>

<hr/>
<p><b>Autor y contacto:</b> Jorge Fallas — <a href="mailto:jfallas56@gmail.com">jfallas56@gmail.com</a></p>
"""
