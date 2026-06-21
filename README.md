# TFG
Diseño e implementación de una arquitectura IoT segura y tolerante a fallos para transmisión distribuida de vídeo


🧠 1. Qué tipo de TFG tienes (clave para la memoria)

Tu proyecto NO es solo “una cámara con streaming”. Es:

👉 Sistema distribuido IoT tolerante a fallos + seguridad + sincronización

Esto cambia totalmente cómo debes escribir la memoria.

📚 2. Índice recomendado (basado en tu anteproyecto)

Te dejo un índice que encaja PERFECTO con lo que ya has definido (puedes usarlo directamente):

📑 CAPÍTULO 1: Introducción

1.1 Motivación

Problema: monitorización remota en IoT
Problemas actuales:
Dependencia de cloud (Google, AWS…)
Falta de control de datos
Fallos de conexión

1.2 Objetivo del proyecto
(Aquí reutilizas casi literal tu objetivo del anteproyecto)

1.3 Alcance

Qué incluye:
Streaming de vídeo
Arquitectura distribuida
Seguridad
Tolerancia a fallos
Qué NO incluye (muy importante para acotar)

1.4 Estructura del documento

🌐 CAPÍTULO 2: Estado del arte

Aquí es donde muchos TFG fallan, pero tú lo tienes fácil:

2.1 Sistemas de videovigilancia actuales

Cámaras IP comerciales
Sistemas cloud

2.2 Arquitecturas IoT

Centralizadas vs distribuidas

2.3 Protocolos de comunicación

MQTT
WebRTC
TCP/HTTP streaming

2.4 Problemas en redes reales

NAT
Firewalls
Latencia

2.5 Seguridad en IoT

TLS
Autenticación
OWASP IoT
🏗️ CAPÍTULO 3: Diseño del sistema

🔥 ESTE ES TU CAPÍTULO MÁS IMPORTANTE

3.1 Visión general de la arquitectura

Nodo remoto (RPi)
Nodo central
Cliente

👉 Aquí deberías incluir un diagrama (te lo puedo hacer si quieres)

3.2 Diseño del nodo remoto

Captura de vídeo
Buffer local
Detección de fallo

3.3 Diseño del nodo central

Recepción de datos
Almacenamiento
Autenticación

3.4 Mecanismo de tolerancia a fallos

Qué pasa cuando se pierde conexión
Buffer
Reconexión

3.5 Seguridad del sistema

Cifrado
JWT
Hash de contraseñas (bcrypt)
⚙️ CAPÍTULO 4: Implementación

Aquí explicas cómo lo hiciste realmente

4.1 Tecnologías utilizadas
(Aquí copias lo de tu anteproyecto y lo amplías)

Python
FFmpeg
Raspberry Pi
etc.

4.2 Implementación del nodo remoto

Código clave
Cómo capturas vídeo
Cómo detectas fallos

4.3 Implementación del nodo central

API
Recepción
BD

4.4 Sincronización

Cómo envías datos pendientes
🧪 CAPÍTULO 5: Evaluación experimental

💥 Este capítulo te da MUCHOS puntos

Puedes usar EXACTAMENTE lo que ya has puesto:

Tiempo de detección de fallo
Tiempo de recuperación
Pérdida de datos
Latencia
CPU en RPi

👉 Aquí metes gráficas

🔐 CAPÍTULO 6: Análisis de seguridad
Modelo STRIDE (ya lo tienes en el anteproyecto)
Ataques posibles:
Intercepción
Acceso no autorizado
Mitigaciones
📊 CAPÍTULO 7: Resultados y discusión
¿Funciona bien?
¿Dónde falla?
Limitaciones
🚀 CAPÍTULO 8: Conclusiones y trabajo futuro
Añadir IA (detección de movimiento)
Mejorar escalabilidad
Más dispositivos
