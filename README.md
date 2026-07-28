# Alura Agente - Andes Cargo 🤖📦

Este proyecto es la solución definitiva al **Desafío Final de Alura Agentes**, diseñado como un asistente de Inteligencia Artificial corporativo, alegre y altamente conversacional para la empresa de logística y envíos **Andes Cargo**. 

Permite a los colaboradores y personal de operaciones realizar preguntas en lenguaje natural sobre el estado de los pedidos, cotización de tarifas comparativas, horarios y gerentes de agencias, rutas de transporte, reclamos de clientes y políticas internas, devolviendo respuestas precisas, inmediatas y respaldadas por los registros oficiales en milisegundos.

---

## 🏗️ Arquitectura del Sistema

La solución implementa una **arquitectura por capas desacoplada** para garantizar mantenibilidad, rapidez y seguridad:

```mermaid
graph TD
    User[Colaborador / Cliente] -->|HTTP POST /api/ask| API[FastAPI Web API Layer]
    API -->|Validación & Middleware| Routes[API Routes & Middleware]
    Routes -->|Query en Lenguaje Natural| Agent[Agent Service Layer]
    Agent -->|Guardrail 1: Clasificación de Intención| Intent[Intent Classifier - Gemini]
    Intent -->|GENERAL_CONVERSATION| Conversational[Respuesta Conversacional Directa]
    Intent -->|SYSTEM_ATTACK| Blocked[Rechazo de Seguridad]
    Intent -->|DATA_QUERY| SQLGen[Traductor Text-to-SQL - Gemini]
    SQLGen -->|Consulta SQL Cruda| Guardrail2[Guardrail 2: Validador SQL Python]
    Guardrail2 -->|¿Contiene tablas/comandos no permitidos? Sí| Error[Acceso Denegado]
    Guardrail2 -->|¿Seguro? Sí| SQLite[(Base de Datos SQLite)]
    CSV[data/*.csv] -->|Carga Inicial / Bootstrapping| SQLite
    SQLite -->|Resultados Crudos| Formulate[Generador de Respuesta - Gemini]
    Formulate -->|Respuesta Final en Español| Routes
    Routes -->|Registra Logs de Auditoría| Logs[execution.jsonl - JSON Lines]
```

### Componentes Clave:
1.  **FastAPI (Presentación)**: Expone endpoints rápidos y documentados (`/api/ask`, `/api/health`).
2.  **Capa de IA (Google Gemini 3.1 Flash-Lite)**:
    *   **Clasificador de Intenciones**: Categoriza la pregunta en consultas de datos (`DATA_QUERY`), respuestas triviales y flujos guiados (`GENERAL_CONVERSATION`), o intentos de explotación (`SYSTEM_ATTACK`). Cuenta con interceptores de expresiones regulares locales para optimizar los consumos de la API (RPD/TPM).
    *   **Traductor Text-to-SQL**: Genera consultas SQL SQLite de solo lectura de forma determinista basándose en el esquema del negocio.
    *   **Formulador de Respuestas**: Traduce los datos crudos a lenguaje natural con excelente actitud y fluidez, tuteando siempre al colaborador.
3.  **SQLite (Persistencia)**: Base de datos ligera que sincroniza dinámicamente todos los archivos CSV de la carpeta [data/](file:///home/jonta/Proyectos/alura-agente/data/) en el arranque en menos de 0.2 segundos.
4.  **JSON Lines Audit Logging (Observabilidad)**: Guarda un registro exacto de cada transacción, latencia y estatus en `logs/execution.jsonl`.

---

## 📊 Estructura de la Base de Datos (Esquema del Negocio)

El agente opera sobre **10 tablas** sincronizadas a partir de los archivos CSV corporativos:
*   `empleados`: Datos de nómina, salarios, puestos y vacaciones de los 130 colaboradores.
*   `pedidos`: Registro de 320 envíos, ciudades origen/destino, costos, pesos y estados de entrega.
*   `sucursales`: Detalles de ubicación, capacidad diaria de paquetes, horarios y gerentes de las 12 agencias.
*   `rutas`: Distancias, transportistas, vehículos y costos bases de transporte a nivel nacional (incluye rutas bidireccionales de ida/vuelta).
*   `politica_envios`: Tiempos oficiales, costos y restricciones por tipo de envío (Estándar, Express, Mismo Día, Internacional, Carga Pesada).
*   `procedimiento_rastreo`: Pasos y tiempos estimados para el seguimiento de paquetes en el canal logístico.
*   `politica_reembolsos_siniestros`: Directrices y plazos para resolver reclamos por paquetes perdidos o dañados.
*   `preguntas_frecuentes`: Base de conocimiento general para la resolución de dudas típicas.
*   `reclamos`: Registro de 90 quejas de atención al cliente, agentes asignados y fechas de resolución.
*   `tarifas_envios`: Matriz detallada de costos base, recargos por peso y km por modalidad de envío (Estándar, Express, Mismo Día, Internacional, Carga Pesada).

---

## 💬 Flujo Conversacional y Funcionalidades Clave

### 1. Saludo Orgánico y Detección de Nombre
Cuando inicias el chat en frío, el agente te recibe cálidamente y te pregunta tu nombre de forma orgánica para establecer una relación personalizada. Una vez que te presentas (ej. *"Hola, soy Steven"*), te saluda con entusiasmo e introduce el menú principal. El backend limpia y extrae el nombre localmente con expresiones regulares y una lista de exclusión (*stop words* como `queria`, `cotizar`), evitando capturar verbos.

### 2. Menú de Opciones y Flujo Guiado
Al presentarse, el agente expone un menú interactivo numerado de opciones de negocio:
1. 📦 **Cotizar un envío**
2. 🔍 **Rastrear un paquete**
3. ⚠️ **Ver estado de un reclamo**
4. 🏢 **Ubicar una sucursal**
5. 👤 **Consultar personal / empleados**

Si seleccionas una de las opciones por número (ej: `1`) o escribes la intención de forma libre, el bot te guía de inmediato pidiéndote los parámetros mínimos necesarios paso a paso.

### 3. Cotizaciones Comparativas Multi-Modalidad
Al ingresar los datos de un paquete (origen, destino y peso), el bot **no asume un tipo de envío único** (como Estándar). Consulta la base de datos de tarifas y te presenta un **menú comparativo de costos y tiempos** para que elijas conversacionalmente:
*   **Estándar** (3-5 días hábiles)
*   **Express** (1-2 días hábiles)
*   **Mismo Día** (entrega urgente local)

### 4. Consultas de Sucursales Completas
Para evitar omitir datos de contacto o forzar al usuario a repreguntar, cuando consultas por cualquier sucursal (ej: *"quién atiende en Alborada"*), el agente recupera y despliega de inmediato la **ficha completa** (Nombre, Dirección, Gerente, Contactos y Horario de Atención completo).

### 5. Control Emocional e Inteligencia de Tono
El agente mantiene una actitud alegre y dinámica (tuteando al usuario de "tú" y usando emojis moderados). Sin embargo, si el cliente muestra frustración o quejas serias por demoras o pérdidas, el bot cambia inmediatamente a un tono **profesional, serio y resolutivo**, suprimiendo emojis y chistes para dar una atención empática y formal.

---

## 🛡️ Seguridad Avanzada contra Inyección SQL
El sistema está protegido mediante múltiples capas defensivas:
1.  **Arquitectura Indirecta (No-Concatenación)**: El input de texto se pasa al LLM como parámetro, evitando la manipulación directa de cadenas de conexión.
2.  **Clasificación de Jailbreaks**: El clasificador de intenciones (`SYSTEM_ATTACK`) bloquea solicitudes de código, esquemas de bases de datos o manipulación técnica antes de generar código SQL.
3.  **Regla de una Sola Sentencia (SQLite)**: El backend tiene prohibido generar múltiples sentencias SQL en cascada (un SELECT debajo de otro) para evitar errores de sintaxis y la inyección de consultas apiladas (*Stacked Queries*).
4.  **Lista Blanca de Tablas**: Se restringe la consulta estrictamente a las 10 tablas del negocio, bloqueando el acceso a tablas del sistema como `sqlite_master`.
5.  **Regla de Simplicidad SQL**: El traductor Text-to-SQL recupera parámetros crudos y evita realizar cálculos matemáticos complejos con `SUM` o `OR EXISTS` condicionales propensos a sumar todas las filas del catálogo relacional. La matemática final se calcula en lenguaje natural, garantizando cotizaciones baratas y exactas.

---

## 🚀 Instrucciones para Ejecución Local

### Prerrequisitos
1.  Python 3.11 o superior instalado.
2.  Una API Key de **Google Gemini** (puedes obtenerla gratis en [Google AI Studio](https://aistudio.google.com/)).

### Configuración Inicial

1.  **Clonar el repositorio y entrar al directorio:**
    ```bash
    git clone <tu-repositorio>
    cd alura-agente
    ```

2.  **Crear e iniciar el entorno virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar Variables de Entorno (.env):**
    Crea el archivo `.env` en la raíz del proyecto y añade tu API Key:
    ```env
    GEMINI_API_KEY=tu_api_key_real_de_gemini
    DATABASE_URL=sqlite:///./alura_agente.db
    PORT=8000
    ```

5.  **Correr el CLI conversacional interactivo:**
    ```bash
    python -m src.cli
    ```
    *Nota: Puedes escribir `limpiar` o `clear` dentro del chat para borrar el historial de conversación y empezar de cero de forma inmediata.*

6.  **Levantar el servidor web API (FastAPI):**
    ```bash
    python -m src.main
    ```
    *   Visita `http://localhost:8000/` para interactuar con la **Interfaz de Chat Web Interactiva** (una UI premium con diseño moderno, menú de acciones interactivo, sugerencias y monitoreo de salud del servidor).
    *   Visita `http://localhost:8000/docs` para interactuar con la interfaz Swagger UI y probar los endpoints directamente.

---

## ☁️ Despliegue en la Nube con Docker
Para desplegar la aplicación containerizada en producción:
1.  Configurar las reglas de Ingress para abrir tráfico en el puerto **8000**.
2.  Levantar el contenedor:
    ```bash
    sudo docker-compose up -d --build
    ```

---

## 📝 Guía de Pruebas y Preguntas de Ejemplo (Datos Reales)

Para probar el agente de forma rápida y efectiva, utiliza estos **casos reales de prueba** extraídos directamente del conjunto de datos corporativos:

### 1. 🔍 Rastreo de Pedido Existente
*   **Pregunta:** `Rastrear el envío AC551646166EC`
*   **Qué esperar:** El agente debe conectarse a la tabla `pedidos`, identificar que pertenece a *Karla Villacis* con origen *Cuenca* y destino *Portoviejo*, y reportar su estado actual (`Entregado`).

### 2. 🏢 Información de Sucursales
*   **Pregunta:** `¿Quién es el gerente de la sucursal Matriz Norte y cuál es su horario?`
*   **Qué esperar:** El agente debe retornar la ficha de la sucursal indicando que el gerente es *Paola Rivadeneira* y el horario completo (`Lunes a Viernes 08:00-18:00, Sabados 08:00-13:00`).

### 3. ⚠️ Verificación de Reclamos
*   **Pregunta:** `Ver el estado del reclamo REC-0001`
*   **Qué esperar:** El agente buscará en la tabla `reclamos`, encontrará la incidencia del cliente *Luis Mendoza* vinculada al pedido `PED-00152` e informará que se encuentra `En Proceso` bajo la atención de *Katherine Salinas*.

### 4. 📦 Cotizaciones Comparativas Automáticas
*   **Pregunta:** `¿Cuánto cuesta un envío estándar de Guayaquil a Cuenca para un paquete de 5kg?`
*   **Qué esperar:** El agente calculará el costo base y los adicionales usando la distancia real de la ruta (`190 km`) y la tarifa correspondiente. Además, ofrecerá el desglose y las alternativas disponibles.

### 5. 👤 Consulta de Personal
*   **Pregunta:** `¿En qué ciudad trabaja la empleada Nicole Abigail Naranjo Delgado?`
*   **Qué esperar:** El agente consultará la tabla `empleados` y responderá que Nicole trabaja en la ciudad de *Machala*.

