# Escritorio Mercado Público PAR · Demo

Prueba una forma de buscar licitaciones y preparar una ficha preliminar de estudio. La demo se ejecuta en tu equipo. Puedes empezar con tres licitaciones ficticias o consultar la [API oficial de ChileCompra](https://www.chilecompra.cl/api/) con tu propio ticket. Proyecto independiente de ChileCompra.

[Descargar la demo para Windows](https://github.com/felipeaviles-web/escritorio-mercado-publico-par-demo/releases/latest)

## Inicio

En Windows, abre `ABRIR_DEMO_PAR.cmd`. El lanzador usa Python del equipo o el entorno de Python de Codex cuando está disponible. Se requiere Python 3.12 y `reportlab`. Si ya tienes Python, puedes instalar la dependencia con `python -m pip install -r requirements.txt` y ejecutar `python demo_par.py`.

La demo abre una dirección `127.0.0.1` en el navegador del mismo equipo. Para cerrar la sesión, presiona Ctrl+C en la ventana de la demo.

## Buscar y generar una ficha

1. Escribe las palabras o frases que quieres incluir, separadas por comas. Basta una coincidencia desde el comienzo de una palabra del título. Por ejemplo, `plaza` encuentra `plazas` y evita `desplazamiento`.
2. Indica qué palabras quieres excluir y, si te sirve, la última fecha de cierre que te interesa.
3. Pulsa **Buscar en ejemplos** y abre una coincidencia. Por ejemplo, incluye `plaza` y excluye `luminarias`.
4. Incorpora las bases y el itemizado de ejemplo, revisa la nota y genera la ficha PDF.

Para buscar datos reales, abre **Buscar licitaciones activas con mi ticket**, ingresa tu ticket personal y pulsa **Buscar licitaciones activas**. Después puedes filtrar nuevamente el listado de esa sesión con el campo de ticket vacío. Los resultados usan información básica de la API. Para consultar el detalle, usa **Consultar por código** bajo **Otras formas de abrir una licitación**. Incorpora los anexos que hayas descargado del portal.

## Datos y archivos

El ticket se utiliza para la consulta HTTPS a la API oficial de ChileCompra y se descarta al terminar la petición. Los criterios y los resultados de búsqueda se mantienen en memoria durante la sesión. Los anexos incorporados se guardan temporalmente. Descarga el PDF antes de cerrar si quieres conservarlo.

## Aportar

Prueba el recorrido con datos de ejemplo. Si un paso te resulta confuso, abre un issue con lo que intentaste, dónde te detuviste y qué esperabas que ocurriera. Usa datos ficticios al compartir capturas, ejemplos y propuestas.

Puedes enviar correcciones por pull request. Ejecuta las pruebas del filtro con `python -m unittest discover -v`.

## Licencia

El código y los ejemplos de este repositorio se comparten bajo la [licencia MIT](LICENSE).
