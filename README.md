# Banco de pruebas: TV + celular

Mide si la arquitectura "el juego corre en el televisor, el celular es el mando"
es viable **en tu televisor concreto**, antes de escribir el producto.

No es un juego. Es un instrumento de medición.

## Qué mide

El celular manda su posición 60 veces por segundo por **dos rutas al mismo tiempo**,
y el televisor le devuelve cada paquete inmediatamente:

| Ruta | Camino | Color |
|---|---|---|
| Por el servidor | celular → servidor → TV → servidor → celular | ámbar |
| Directo | celular → TV, sin intermediarios | menta |

En pantalla verás dos cuadros corriendo la misma carrera. El que se quede atrás
es la ruta lenta. Los números están abajo.

## Desplegarlo

Necesitas HTTPS. Safari no entrega los datos del giroscopio sin él, y sin HTTPS
tampoco funciona WebRTC. Por eso no sirve abrirlo desde la IP local del portátil.

Cualquier host gratuito con Node sirve. Con Render:

1. Sube esta carpeta a un repositorio de GitHub
2. En Render: New → Web Service → conecta el repo
3. Build: `npm install` · Start: `npm start`
4. Te queda una URL tipo `https://algo.onrender.com`

En el plan gratuito el servicio se duerme; la primera carga tarda medio minuto.

## Usarlo

1. Abre la URL en el **navegador del televisor**. Sale un código de 4 letras.
2. Abre `esa-url/pad` en el iPhone y escribe el código.
3. Toca "Activar sensor de movimiento" y acepta el permiso.
4. Arrastra el dedo por el área grande **mirando el televisor**, no el celular.

Antes de medir, entra a los ajustes del televisor y activa el **modo Juego**.
Según el modelo eso solo puede quitar entre 20 y 100 ms.

## Leer los resultados

Los números son ida y vuelta. La latencia que siente el jugador es
aproximadamente **la mitad**, más un cuadro de render (~16 ms), más el retardo
del panel del televisor.

| Total percibido | Veredicto |
|---|---|
| menos de 50 ms | excelente, sirve hasta para juegos de precisión |
| 50 a 100 ms | bien para arcade |
| 100 a 150 ms | jugable, se nota |
| más de 150 ms | hay que rediseñar |

Mira **p95 y máximo**, no solo la mediana. Una mediana de 30 ms con picos de
200 ms se siente peor que 60 ms estables. El temblor molesta más que el retraso.

## Las tres respuestas que buscas

1. **¿El navegador del TV abre la página?** Si no, no hay proyecto en ese modelo.
2. **¿WebRTC conecta?** Es el mayor riesgo técnico. Si en el panel menta dice
   "no hubo conexión directa" o "este TV no soporta WebRTC", todo el tráfico
   tendría que pasar por tu servidor, y eso cambia el costo y la latencia del producto.
3. **¿Se siente bien?** Los números importan, pero mueve el dedo mirando el
   televisor y fíjate si te molesta. Esa impresión vale tanto como la medición.

Anota los tres resultados. Definen la arquitectura del producto.

## Después de esto

Si sale bien, la Fase 2 es un solo juego, sin catálogo ni menú: Pong para dos
jugadores, reusando el emparejamiento por código que ya está aquí.

Si WebRTC falla en tu televisor, antes de rendirte prueba la misma URL en el
navegador de un portátil conectado por Wi-Fi. Eso separa "el problema es el
televisor" de "el problema es mi red".
