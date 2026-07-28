import time
import json
import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "execution.jsonl")

class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Asegurarnos de que el directorio de logs exista
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
            
        start_time = time.time()
        
        # Procesar la petición
        response = await call_next(request)
        
        # Solo auditar si es la ruta de preguntas /api/ask
        if request.url.path == "/api/ask" and request.method == "POST":
            duration = time.time() - start_time
            
            # Intentar leer el request body
            # Nota: leer el body en un middleware puede interferir si no se maneja con cuidado,
            # pero dado que el request de FastAPI para JSON es pequeño, podemos registrarlo.
            # Alternativamente, delegamos el registro al endpoint para evitar problemas de consumo del stream del body.
            pass
            
        return response

def log_agent_execution(query: str, response_data: dict, duration: float):
    """
    Registra en un archivo JSON Lines cada consulta enviada al agente,
    la respuesta obtenida, el estatus y el tiempo de ejecución.
    """
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "query": query,
        "success": response_data.get("success", False),
        "answer": response_data.get("answer", ""),
        "error": response_data.get("error"),
        "latency_seconds": round(duration, 4)
    }
    
    # Escribir en el archivo JSON Lines
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
    print(f"[AUDIT LOG] Registrada consulta: '{query}' en {round(duration, 2)}s.")
