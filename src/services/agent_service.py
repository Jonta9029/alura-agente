import os
import re
import json
from sqlalchemy import text
from langchain_google_genai import ChatGoogleGenerativeAI
from src.database.connection import engine
from src.config import settings

class AgentService:
    def __init__(self):
        # 1. Validar la API Key de Gemini
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "tu_gemini_api_key_aqui":
            raise ValueError(
                "La variable de entorno GEMINI_API_KEY no está configurada o contiene el valor por defecto."
            )
        
        # 2. Inicializar el LLM de Google Gemini 3.1 Flash-Lite
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.0,
            max_retries=1
        )

        # Listado de tablas permitidas por seguridad
        self.allowed_tables = [
            "empleados", "pedidos", "sucursales", "rutas", 
            "politica_envios", "politica_reembolsos_siniestros", 
            "procedimiento_rastreo", "preguntas_frecuentes", "reclamos",
            "tarifas_envios"
        ]
        
        # Historial de conversación en memoria (Sesión lineal)
        self.chat_history = []
        
        # [OPTIMIZACIÓN] Guardar el nombre de usuario localmente en Python para ahorrar tokens de contexto
        self.user_name = None

    def clear_history(self):
        """Limpia el historial de chat para iniciar una nueva conversación."""
        self.chat_history = []
        self.user_name = None

    def _get_history_context(self) -> str:
        """Formatea el historial de conversación para inyectarlo como contexto en los prompts."""
        if not self.chat_history:
            return "No hay historial previo de conversación."
        
        formatted = []
        for msg in self.chat_history[-4:]:  # Mantenemos memoria de los últimos 4 mensajes
            role = "Colaborador" if msg["role"] == "user" else "Agente"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)

    def _classify_intent(self, query: str) -> dict:
        """
        [OPTIMIZACIÓN] Intercepta intenciones comunes localmente con expresiones regulares
        para ahorrar llamadas (requests) innecesarias a la API de Gemini.
        """
        query_clean = query.lower().strip()
        
        # 1. Heurística Local: Saludos e interacciones conversacionales básicas
        saludos_patterns = [
            r"^(hola|buenos dias|buenas tardes|buenas noches|hey|hello|saludos|que tal|holaaa+)(.*)$",
            r"^(gracias|muchas gracias|entendido|perfecto|excelente|listo|de acuerdo)(.*)$",
            r"^(quien eres|quién eres|como te llamas|cómo te llamas|tu nombre)(.*)$"
        ]
        
        for pattern in saludos_patterns:
            if re.match(pattern, query_clean):
                return {
                    "category": "GENERAL_CONVERSATION",
                    "reason": "Coincidencia de patrón de saludo/agradecimiento local en Python"
                }

        # 2. Heurística Local: Selección numérica de opciones del menú (1 al 5)
        # Esto ahorra clasificación de API si el colaborador elige una opción del menú directamente
        if query_clean in ["1", "2", "3", "4", "5", "opcion 1", "opción 1", "opcion 2", "opción 2", "opcion 3", "opción 3", "opcion 4", "opción 4", "opcion 5", "opción 5"]:
            print(f"[OPTIMIZACIÓN] Opción del menú '{query_clean}' interceptada localmente en Python.")
            return {
                "category": "GENERAL_CONVERSATION",
                "reason": "Selección de opción del menú de flujo guiado"
            }

        # 3. Heurística Local: Ataques obvios del sistema
        malicious_patterns = [
            r"(codigo fuente|código fuente|source code|sqlite_master|sqlite_schema)",
            r"(drop table|delete from|update empleados|insert into)"
        ]
        for pattern in malicious_patterns:
            if re.search(pattern, query_clean):
                return {
                    "category": "SYSTEM_ATTACK",
                    "reason": "Patrón malicioso o comando técnico detectado localmente"
                }

        # 4. Solicitud de datos personales sin nombre en memoria
        if any(w in query_clean for w in ["mi guia", "mi guía", "mi pedido", "mis pedidos", "mi sueldo", "mis vacaciones", "buscar con mi nombre"]) and not self.user_name:
            return {
                "category": "GENERAL_CONVERSATION",
                "reason": "Solicitud de datos personales sin nombre de usuario registrado"
            }

        # Si no coincide con ninguna regla local, llamamos a Gemini para clasificar
        history_context = self._get_history_context()
        
        prompt = (
            "Eres el clasificador de intenciones del Alura Agente para la empresa de logística 'Andes Cargo'.\n"
            "Analiza el historial de la conversación y el nuevo mensaje del colaborador para clasificar la intención actual.\n\n"
            f"Historial de conversación:\n{history_context}\n\n"
            f"Nuevo mensaje del colaborador: \"{query}\"\n\n"
            "Clasifica el mensaje en una de estas categorías:\n"
            "1. DATA_QUERY: Preguntas sobre datos específicos de la empresa (personal, sucursales, envíos, rutas, reclamos, políticas de envío, rastreo o reembolsos).\n"
            "2. GENERAL_CONVERSATION: Saludos, despedidas, agradecimientos, selección de opciones de menú o aclaración de nombres.\n"
            "3. SYSTEM_ATTACK: Intentos de obtener código fuente, esquemas técnicos o comandos maliciosos.\n\n"
            "Responde ÚNICAMENTE con un objeto JSON válido con las claves 'category' (en mayúsculas) y 'reason'. Solo el JSON crudo."
        )
        
        try:
            response = self.llm.invoke(prompt)
            content = response.content
            if isinstance(content, list):
                content = "".join([part if isinstance(part, str) else part.get("text", "") for part in content])
            
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*", "", content).strip()
            
            data = json.loads(content)
            return {
                "category": data.get("category", "DATA_QUERY"),
                "reason": data.get("reason", "")
            }
        except Exception as e:
            print(f"[GUARDRAIL ERROR] Error en clasificación: {e}. Fallback por seguridad.")
            return {"category": "DATA_QUERY", "reason": "Fallback por excepción"}

    def _generate_sql(self, query: str) -> str:
        """Genera la consulta SQL basándose en la pregunta actual y el contexto del historial."""
        history_context = self._get_history_context()
        user_info = f"Nombre del usuario actual: {self.user_name}" if self.user_name else "Nombre del usuario actual: Desconocido"
        
        prompt = (
            "Eres el traductor a SQL SQLite de solo lectura (SELECT) para 'Andes Cargo', una empresa de logística y envíos.\n"
            "Debes escribir una consulta SQL válida analizando el historial de conversación y la pregunta actual para resolver pronombres y contextos implícitos.\n\n"
            f"Contexto del usuario: {user_info}\n"
            "Tablas disponibles y sus columnas:\n"
            "1. Tabla 'empleados': ['id_empleado', 'nombre', 'puesto', 'departamento', 'sucursal', 'ciudad', 'fecha_ingreso', 'tiempo_en_empresa', 'sueldo_mensual_usd', 'sueldo_anual_usd', 'aporte_personal_iess_usd', 'aporte_patronal_iess_usd', 'decimo_tercero_mensual_usd', 'decimo_cuarto_anual_usd', 'dias_vacaciones_disponibles', 'email', 'telefono', 'estado']\n"
            "2. Tabla 'pedidos': ['id_pedido', 'numero_seguimiento', 'cliente', 'ciudad_origen', 'ciudad_destino', 'sucursal_origen', 'tipo_envio', 'peso_kg', 'fecha_pedido', 'fecha_entrega_estimada', 'estado', 'costo_usd']\n"
            "3. Tabla 'sucursales': ['id_sucursal', 'nombre', 'ciudad', 'direccion', 'tipo', 'capacidad_diaria_paquetes', 'gerente', 'telefono', 'email', 'horario_atencion']\n"
            "4. Tabla 'rutas': ['id_ruta', 'origen', 'destino', 'transportista', 'tipo_vehiculo', 'distancia_km', 'tiempo_estimado_horas', 'costo_base_usd', 'frecuencia_semanal']\n"
            "5. Tabla 'politica_envios': ['id', 'tipo_envio', 'descripcion', 'tiempo_entrega_dias', 'peso_maximo_kg', 'cobertura', 'costo_base_usd', 'restricciones']\n"
            "6. Tabla 'procedimiento_rastreo': ['id', 'paso', 'nombre_paso', 'descripcion', 'responsable', 'canal', 'tiempo_estimado']\n"
            "7. Tabla 'politica_reembolsos_siniestros': ['id', 'tipo_incidente', 'descripcion', 'plazo_reclamo_dias', 'porcentaje_reembolso', 'requisitos', 'tiempo_resolucion_dias']\n"
            "8. Tabla 'preguntas_frecuentes': ['id', 'categoria', 'pregunta', 'respuesta']\n"
            "9. Tabla 'reclamos': ['id_reclamo', 'id_pedido', 'cliente', 'fecha_reclamo', 'tipo_reclamo', 'descripcion', 'estado', 'agente_asignado', 'fecha_resolucion']\n"
            "10. Tabla 'tarifas_envios': ['id_tarifa', 'tipo_envio', 'rango_peso_kg', 'rango_volumen_m3', 'costo_base_usd', 'costo_adicional_kg_usd', 'costo_adicional_km_usd', 'descripcion']\n\n"
            f"Historial de conversación:\n{history_context}\n\n"
            f"Pregunta actual del colaborador: \"{query}\"\n\n"
            "Instrucciones críticas:\n"
            "1. Resuelve pronombres usando el historial.\n"
            "2. Escribe una consulta SQL válida para SQLite. Solo SELECT.\n"
            "3. IMPORTANTE: Devuelve únicamente la consulta SQL limpia. Sin explicaciones ni marcas de bloque de código Markdown.\n"
            "4. En comparaciones de texto, las constantes en las cláusulas WHERE NO llevan tildes ni acentos.\n"
            "5. Si combinas tablas usando UNION, selecciona únicamente columnas compatibles en número y tipo. NUNCA uses SELECT * en un UNION.\n"
            "6. RELACIONES Y JOINs: Realiza JOINs explícitos. La columna 'numero_seguimiento' NO pertenece a 'reclamos'.\n"
            "7. COTIZACIÓN DE ENVÍOS (REGLA DE OPCIONES MÚLTIPLES): Si te piden cotizar un envío, NO asumas por defecto un único tipo de envío (como 'Estandar') ni filtres rígidamente por él en el WHERE. Escribe una consulta SELECT para recuperar la distancia de la ruta (distancia_km de la tabla 'rutas') y todos los registros aplicables de la tabla 'tarifas_envios' para los diferentes tipos de envío (ej: SELECT tipo_envio, costo_base_usd, costo_adicional_kg_usd, costo_adicional_km_usd, rango_peso_kg FROM tarifas_envios). Esto permitirá que la fase de respuesta final en lenguaje natural calcule y le presente al colaborador un abanico comparativo de opciones (Estándar, Express, Mismo Día, etc.) para que elija conversacionalmente.\n"
            "8. REGLA DE UNA SOLA SENTENCIA: Tienes ESTRICTAMENTE PROHIBIDO generar múltiples consultas SQL secuenciales separadas (ej. un SELECT debajo de otro). Si el colaborador te hace una pregunta compuesta con múltiples temas (ej. precios, sucursales y políticas), escribe una ÚNICA consulta SELECT unificada usando UNION y columnas de texto genéricas con alias comunes (por ejemplo: SELECT 'Tarifa' AS tipo, costo_base_usd || ' USD base' AS informacion FROM tarifas_envios WHERE tipo_envio = 'Estandar' UNION SELECT 'Sucursal' AS tipo, nombre || ': ' || direccion AS informacion FROM sucursales WHERE ciudad = 'Guayaquil' UNION SELECT 'Politica' AS tipo, restricciones AS informacion FROM politica_envios WHERE tipo_envio = 'Estandar').\n"
            "9. CONSULTAS DE SUCURSALES COMPLETAS: Si el colaborador pregunta por cualquier aspecto de una sucursal, su ubicación, su personal o quién atiende en ella, escribe una consulta que seleccione las columnas completas (nombre, direccion, gerente, telefono, email, horario_atencion) de la tabla 'sucursales'. Evita seleccionar solo una columna aislada (como el gerente o la dirección) para no omitir datos importantes y evitar que el colaborador tenga que repreguntar.\n"
        )
        
        response = self.llm.invoke(prompt)
        content = response.content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
            sql_query = "".join(text_parts).strip()
        else:
            sql_query = content.strip()
            
        sql_query = re.sub(r"```sql\s*", "", sql_query)
        sql_query = re.sub(r"```\s*", "", sql_query)
        sql_query = sql_query.strip().replace(";", "")
        
        return sql_query

    def _execute_sql(self, sql_query: str) -> list:
        """Ejecuta la consulta SQL generada en SQLite de forma segura."""
        clean_query = sql_query.upper().strip()
        if not clean_query.startswith("SELECT"):
            raise PermissionError("Solo se permiten consultas de lectura (SELECT).")
            
        forbidden_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "REPLACE"]
        for keyword in forbidden_keywords:
            if re.search(r"\b" + keyword + r"\b", clean_query):
                raise PermissionError(f"Comando '{keyword}' no permitido.")

        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            return [dict(row._mapping) for row in result]

    def _generate_response(self, query: str, sql_query: str, data: list) -> str:
        """Formula la respuesta final en lenguaje natural basándose en el historial y datos."""
        history_context = self._get_history_context()
        user_info = f"Nombre del usuario actual: {self.user_name}" if self.user_name else ""
        
        prompt = (
            "Eres el Alura Agente, el asistente de IA conversacional de la empresa de logística 'Andes Cargo'.\n"
            "Tu objetivo es formular respuestas claras, amigables y de excelente actitud basándote en los datos recuperados de la base de datos.\n\n"
            f"Contexto del usuario: {user_info}\n"
            "Instrucciones críticas de tono y personalidad:\n"
            "1. Tono General: Semiformal, alegre, dinámico y conversacional. Usa transiciones naturales y sutiles en español (ej. '¡Por supuesto!', 'Déjame revisar eso en el sistema...', '¡Excelente pregunta! Encontré esto para ti...') y emojis amigables de forma muy moderada (como 😊 o 📦) para que se sienta vivo y humano.\n"
            "2. REGLA DE TUTEO (SIEMPRE TRATAR DE 'TÚ'): Debes tratar siempre al colaborador de 'tú' (tuteo). NUNCA lo trates de 'usted' ni uses pronombres formales como 'su consulta', 'sus gestiones', 'lamento su inconveniente'. Usa 'tu consulta', 'tus gestiones', 'ayudarte'.\n"
            "3. DETECCIÓN DE MOLESTIA REAL: Si en el historial de conversación o en el mensaje actual el usuario se muestra molesto de verdad, frustrado con rabia, insulta o tiene quejas graves por paquetes perdidos o demoras críticas, cambia de inmediato a un tono SERIO, formal y empático. Sin embargo, comentarios casuales, recordatorios de datos omitidos (ej. 'no me dijiste el horario' o 'te faltó el teléfono') o correcciones tranquilas del usuario NO constituyen molestia. Ante estos descuidos menores, mantén el tono alegre y sé simpático, relajado y natural: '¡Ay, tienes toda la razón! Qué despistado de mi parte. 😊 Aquí tienes...' o similar. EVITA a toda costa disculpas corporativas rígidas, dramáticas o redundantes.\n"
            "4. NO ALUCINACIÓN COMERCIAL: NUNCA inventes ofertas, promociones, convenios de descuento corporativo, ni comprometas al personal de la sucursal o agencia a dar descuentos manuales que no consten explícitamente en la base de datos de 'tarifas_envios' o 'preguntas_frecuentes'. Si no existen promociones en los datos recuperados, indica con total honestidad y buena actitud que actualmente no contamos con promociones vigentes para esa ruta o rango de peso.\n"
            "5. CÁLCULO Y PRESENTACIÓN DE COTIZACIONES DE ENVÍO: Si te piden cotizar un envío y recuperaste múltiples tarifas (por ejemplo, Estándar, Express, Mismo Día, etc.) y la distancia de la ruta, calcula el precio final para cada una de las opciones de envío disponibles que correspondan al rango de peso del paquete (ej. para 3.2 kg aplica el rango '0-5' de cada tipo de envío. El cálculo es: costo_base_usd + (distancia_km * costo_adicional_km_usd)). Presenta al colaborador un menú claro y comparativo de las opciones (ej. detallando precios y tiempos de Estándar, Express y Mismo Día) para que elija conversacionalmente. Si no hay ruta en el catálogo, realiza el cálculo estimado únicamente en base a la tarifa base.\n"
            "6. PRECISIÓN DE RUTAS: Si los datos obtenidos de la base de datos contienen una distancia de ruta válida (distancia_km mayor a 0, ej: 410 km), afirma con total seguridad que la ruta directa está registrada y operativa en el sistema de Andes Cargo. NUNCA digas que no existe la ruta o que es una estimación base por falta de trayecto en tu respuesta si la base de datos te entregó la distancia exacta. Tampoco mezcles conceptos diciendo cosas como 'ruta directa con peso específico'.\n"
            "7. CONTINUIDAD: NO saludes ni te despidas formalmente en cada mensaje. Como es un chat continuo, responde directamente y con agilidad, eliminando introducciones repetitivas si ya saludaste en el historial.\n"
            "8. Preguntas de seguimiento proactivas: Al final de tu respuesta (si el usuario no está molesto), haz una pregunta de seguimiento útil para mantener el chat vivo. Si el usuario está molesto, haz una pregunta de seguimiento seria enfocada únicamente en ayudar a resolver su incidencia.\n"
            "9. Datos vacíos: Si los datos obtenidos son [], responde con excelente actitud, indicando amablemente que no posees ese registro exacto y ofrécete a ayudarle con empleados, envíos, rutas o reclamos de forma muy atenta.\n"
            "10. Cita sutilmente la fuente (ej. 'Según nuestro registro de rutas...', 'De acuerdo con el manual de reembolsos...').\n\n"
            f"Historial de conversación:\n{history_context}\n\n"
            f"Pregunta del colaborador: \"{query}\"\n"
            f"Consulta SQL ejecutada: {sql_query}\n"
            f"Datos obtenidos: {data}\n"
        )
        
        response = self.llm.invoke(prompt)
        content = response.content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
            return "".join(text_parts).strip()
        else:
            return content.strip()

    def ask(self, query: str) -> dict:
        """Punto de entrada principal. Mantiene la memoria e inyecta fluidez al chat."""
        try:
            query_clean = query.lower().strip()
            
            # [OPTIMIZACIÓN] Detección local del nombre del usuario mediante expresiones regulares en Python.
            name_match = re.search(r"(?:me llamo|soy|mi nombre es|gusto soy)\s+([A-Za-zñÑáéíóúÁÉÍÓÚ\s]{3,35})", query_clean)
            if name_match:
                raw_name = name_match.group(1).strip()
                stop_words = ["queria", "quería", "quiero", "cotizar", "enviar", "un", "una", "paquete", "guia", "guía", "como", "cómo", "hola", "pregunta", "el", "la", "un", "una", "de", "del"]
                words = [w for w in raw_name.split() if w.lower() not in stop_words]
                if words:
                    self.user_name = " ".join([w.capitalize() for w in words[:2]])
                    print(f"[OPTIMIZACIÓN] Nombre de usuario detectado localmente por RegEx: '{self.user_name}'")

            # 1. Guardrail de Clasificación (con interceptores locales)
            intent = self._classify_intent(query)
            category = intent["category"]
            print(f"[GUARDRAIL] Categoría detectada: {category} (Razón: {intent['reason']})")
            
            # 2. Manejo de ataques
            if category == "SYSTEM_ATTACK":
                answer = (
                    "Lo siento, por políticas de seguridad corporativas no puedo revelar información técnica, "
                    "código fuente, ni detalles de la estructura de la base de datos interna. "
                    "¿Hay alguna consulta de negocio sobre envíos, rutas o nuestro personal en la que pueda ayudarte?"
                )
                self.chat_history.append({"role": "user", "content": query})
                self.chat_history.append({"role": "model", "content": answer})
                return {"success": True, "query": query, "answer": answer, "error": None}
                # 3. Manejo conversacional o solicitudes de datos faltantes (GENERAL_CONVERSATION)
            if category == "GENERAL_CONVERSATION":
                history_context = self._get_history_context()
                prompt = (
                    "Eres el Alura Agente, el asistente de IA conversacional ultra dinámico, alegre, humanista y muy servicial de 'Andes Cargo'.\n"
                    "Responde al mensaje conversacional en español con un tono súper cercano, alegre y entusiasta. Usa emojis amigables como 😊 o 📦 de forma natural y sutil.\n"
                    "REGLA DE SOLICITUD DE NOMBRE ORGÁNICA: Si el nombre del usuario es desconocido, DEBES pedirle su nombre en tu primera respuesta de una manera muy dulce y orgánica: '¡Hola! Qué alegría saludarte. 😊 Soy el Alura Agente, tu asistente de Andes Cargo. ¿Con quién tengo el gusto de hablar hoy para poder darte una atención personalizada?'\n"
                    "REGLA DE MENÚ DE OPCIONES: Si el colaborador ya se presentó (ej. 'hola soy steven' o ya conoces su nombre), dale una cálida bienvenida personalizada (ej. '¡Mucho gusto, Steven! Qué alegría tenerte por acá. 😊') y preséntale con excelente actitud el menú interactivo de opciones numeradas para que elija:\n"
                    "   Por favor, selecciona una de las siguientes opciones ingresando el número correspondiente:\n"
                    "   1. 📦 **Cotizar un envío** (calcular tarifas por peso y distancia)\n"
                    "   2. 🔍 **Rastrear un paquete** (ver estado actual por número de guía)\n"
                    "   3. ⚠️ **Ver estado de un reclamo** (consultar estado e información de incidencias)\n"
                    "   4. 🏢 **Ubicar una sucursal** (direcciones y horarios de atención)\n"
                    "   5. 👤 **Consultar personal / empleados** (información del equipo o sucursales)\n\n"
                    "REGLA DE FLUJO GUIADO: Si el colaborador responde con un número del 1 al 5 o menciona una de estas opciones:\n"
                    "   - Opción 1: Respóndele con muchísimo entusiasmo y pídele de forma muy clara y amable que te indique: la ciudad de origen, la ciudad de destino y el peso aproximado (o tipo de paquete) para realizar la cotización.\n"
                    "   - Opción 2: Pídele amablemente que te proporcione el número de guía o seguimiento del paquete.\n"
                    "   - Opción 3: Pídele que te facilite el ID del reclamo o el número de guía asociado al inconveniente.\n"
                    "   - Opción 4: Pregúntale en qué ciudad o provincia se encuentra para mostrarle las agencias disponibles.\n"
                    "   - Opción 5: Pregúntale el nombre del empleado o la sucursal de la que desea información.\n"
                    "DIRECTRIZ DE NATURALIDAD Y HUMOR: Si el colaborador te hace un comentario ingenioso, bromas o reclamos ligeros en el chat (por ejemplo, si te reclama que no lo saludaste como 'hola no me saludaste'), responde con frescura, naturalidad, buen humor y una actitud muy simpática y ligera. EVITA disculpas corporativas rígidas o dramáticas. En su lugar, sé simpático: '¡Ups, tienes toda la razón! ¡Hola, hola! Qué distraído de mi parte. 😊 Ahora sí...' o similar.\n"
                    "DETECCIÓN DE MOLESTIA: Si en el historial o en el mensaje actual el usuario se muestra molesto, enojado, frustrado o preocupado, cambia tu tono de inmediato a uno serio, formal, sumamente profesional y empático. No uses emojis ni palabras alegres en ese caso.\n"
                    "REGLA CRÍTICA DE CONTINUIDAD: No uses saludos repetitivos ni te vuelvas a presentar si ya lo hiciste en el historial de la conversación. Mantén el chat ágil.\n\n"
                    f"Historial de conversación:\n{history_context}\n\n"
                    f"Nuevo mensaje del colaborador: \"{query}\""
                )
                response = self.llm.invoke(prompt)
                content = response.content
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict) and "text" in part:
                            text_parts.append(part["text"])
                    answer = "".join(text_parts).strip()
                else:
                    answer = content.strip()
                
                self.chat_history.append({"role": "user", "content": query})
                self.chat_history.append({"role": "model", "content": answer})
                return {"success": True, "query": query, "answer": answer, "error": None}

            # 4. DATA_QUERY: Generar y validar la consulta SQL con memoria
            sql_query = self._generate_sql(query)
            print(f"[SQL GENERADO]: {sql_query}")
            
            query_lower = sql_query.lower()
            if any(term in query_lower for term in ["sqlite_master", "sqlite_schema", "sqlite_sequence", "sqlite_temp_master"]):
                raise PermissionError("Acceso denegado: Intento de lectura de tablas del sistema.")
            
            referred_tables = re.findall(r"\bfrom\s+(\w+)|\bjoin\s+(\w+)", query_lower)
            referred_tables = [t for tuple_t in referred_tables for t in tuple_t if t]
            
            for table in referred_tables:
                if table not in self.allowed_tables:
                    raise PermissionError(f"Acceso denegado: La tabla '{table}' no es válida.")

            # 5. Ejecutar de forma segura
            data = self._execute_sql(sql_query)
            print(f"[DATOS RECUPERADOS]: {data}")
            
            # 6. Formular la respuesta
            answer = self._generate_response(query, sql_query, data)
            
            self.chat_history.append({"role": "user", "content": query})
            self.chat_history.append({"role": "model", "content": answer})
            
            return {
                "success": True,
                "query": query,
                "answer": answer,
                "error": None
            }
        except Exception as e:
            print(f"[AGENT ERROR] Fallo en la cadena de ejecución: {e}")
            
            error_prompt = (
                "Eres el Alura Agente de 'Andes Cargo'. Ha ocurrido una pequeña interrupción temporal al conectar con la base de datos.\n"
                "Redacta una respuesta de disculpas sumamente atenta, empática, amigable y fluida en español, reorientando la ayuda.\n"
                "REGLA CRÍTICA: NO saludes ni te presentes formalmente. Dado que la conversación ya está en curso, ve directo al grano disculpándote y ofreciendo ayuda en temas de empleados, envíos, rutas o reclamos de forma muy proactiva.\n\n"
                f"Pregunta del colaborador: \"{query}\""
            )
            try:
                response = self.llm.invoke(error_prompt)
                content = response.content
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict) and "text" in part:
                            text_parts.append(part["text"])
                    answer = "".join(text_parts).strip()
                else:
                    answer = content.strip()
            except Exception:
                answer = (
                    "Lamento la interrupción técnica temporal con nuestros registros de Andes Cargo. "
                    "¿Te puedo ayudar con alguna otra consulta sobre nuestro personal, rutas o reclamos?"
                )
                
            self.chat_history.append({"role": "user", "content": query})
            self.chat_history.append({"role": "model", "content": answer})
            
            return {
                "success": True,
                "query": query,
                "answer": answer,
                "error": str(e)
            }

# Instancia singleton para su uso en la API
agent_service = None

def get_agent_service():
    global agent_service
    if agent_service is None:
        agent_service = AgentService()
    return agent_service
