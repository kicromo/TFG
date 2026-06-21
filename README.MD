Título: Diseño e implementación de una arquitectura IoT segura y tolerante a fallos para transmisión distribuida de vídeo
Título en inglés: Design and Implementation of a Secure and Fault-Tolerant IoT Architecture for Distributed Video Transmission
Trabajo individual (no en grupo)
Fecha: Málaga, 26 de febrero de 2026 (firmado por el tutor)

Introducción

En entornos IoT distribuidos es habitual transmitir datos entre nodos en redes separadas geográficamente, pero suele depenerse de infraestructuras centralizadas o servicios cloud comerciales, generando problemas de privacidad, dependencia de terceros y poca tolerancia a fallos. El TFG propone una arquitectura distribuida para transmisión segura de datos (caso de uso: vídeo) entre nodos IoT en redes distintas. El foco no es la cámara en sí, sino los mecanismos de:

Tolerancia a fallos ante pérdida de conectividad
Almacenamiento temporal local (buffer)
Sincronización diferida tras recuperación
Seguridad del canal y control de acceso

Se diseñará con vocación de uso real en entornos domésticos, priorizando bajo coste, simplicidad de despliegue y control local de datos.
Objetivos

Objetivo general: diseñar, implementar y evaluar experimentalmente una arquitectura IoT segura y tolerante a fallos para transmisión distribuida de datos entre nodos en redes independientes.
Objetivos específicos:

Diseñar la arquitectura general (nodo remoto + nodo central)
Implementar transmisión cifrada entre nodos
Implementar detección automática de fallo de conectividad
Diseñar e implementar almacenamiento temporal local (buffer)
Implementar sincronización segura tras recuperación de conexión
Garantizar integridad de los datos sincronizados (hash/verificación)
Implementar autenticación local mediante archivo de credenciales cifrado (bcrypt)
Registrar accesos y eventos relevantes del sistema
Evaluar experimentalmente: tiempo de detección de fallo, tiempo de recuperación, pérdida de datos, impacto en latencia, consumo energético/CPU (RPi), throughput efectivo durante sincronización, tiempo máximo de desconexión soportado antes de pérdida
Análisis basado en STRIDE o similar
Gestión de recursos del buffer

Entregables

Código fuente del sistema (nodo IoT y nodo central)
Scripts de configuración y despliegue
Documentación técnica de arquitectura
Resultados experimentales (mediciones y análisis)
Memoria completa del TFG
Manual básico de instalación y uso
Repositorio Git con historial de desarrollo

Métodos y fases de trabajo
Metodología: iterativa con hitos intermedios. Cada fase incluye: diseño conceptual, implementación incremental, pruebas funcionales, evaluación de resultados, revisión técnica. Se realizará evaluación experimental controlada simulando: pérdida de conectividad, interrupciones prolongadas, reconexión, transferencia diferida.
Fases de trabajo:

Fase 1 – Estudio y diseño de arquitectura: análisis de arquitecturas IoT distribuidas, estudio de protocolos seguros de transmisión, diseño preliminar del sistema, modelo de amenazas inicial.
Fase 2 – Implementación del nodo remoto (RPi): captura y codificación de vídeo, implementación de canal cifrado, implementación de detección de fallo, implementación en disco/buffer local.
Fase 3 – Implementación del nodo central: recepción del stream, almacenamiento persistente, sistema de autenticación local, registro de eventos.
Fase 4 – Sincronización y recuperación: implementación de sincronización diferida, verificación de integridad, gestión de limpieza de buffer.
Fase 5 – Evaluación experimental: simulación de caídas de red, medición de tiempos, análisis de resultados, evaluación de resiliencia.
Fase 6 – Análisis de seguridad: identificación de amenazas, evaluación de superficie de ataque, propuestas de mejora, discusión de limitaciones.

Temporización (horas)
FaseHorasFase 140Fase 260Fase 360Fase 450Fase 550Fase 636Total296
Entorno tecnológico
Tecnologías empleadas:

Python (backend y control) + C
FFMPEG / herramientas de streaming
Protocolos seguros (VPN / WebRTC / MQTT + TLS / TCP tunelizado / similar)
JWT para autenticación
Linux (Ubuntu)
Hash seguro (bcrypt o similar)

Recursos software y hardware:

Raspberry Pi 4 (nodo remoto)
Cámara USB compatible Linux
PC con Ubuntu (nodo central)
Discos de almacenamiento (posible RAID 1)
VS Code
Git
Herramientas de monitorización de red

Referencias

TCP / Modelo de transporte (RFC 9293)
MQTT v5.0 (OASIS)
Mosquitto (documentación)
TLS / Seguridad de canal (RFC 8446)
OWASP TLS Cheat Sheet
WireGuard (sitio oficial y whitepaper)
NAT y Firewalls (RFC 3022)
RFC 4787 – NAT Behavioral Requirements
Netfilter / iptables (documentación)
bcrypt documentation (Auth0 blog)
WebRTC (sitio oficial)
RFC 8825 – WebRTC Overview
FFmpeg (documentación)
Tanenbaum – Distributed Systems
OWASP IoT Top 10
NIST IoT Security Framework
RFC 7519 – JWT