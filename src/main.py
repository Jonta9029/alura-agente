import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env antes de cualquier otra importación
load_dotenv()

from src.config import settings
from src.database.loader import init_db
from src.api.routes import router

# 1. Inicializar base de datos SQLite y cargar datos del CSV
print("[STARTUP] Inicializando base de datos SQLite...")
init_db()

# 2. Configurar la aplicación FastAPI
app = FastAPI(
    title="Alura Agente Corporativo",
    description=(
        "API para un agente de Inteligencia Artificial que responde preguntas sobre la base de datos "
        "corporativa usando procesamiento de lenguaje natural (RAG estructurado con SQLite y Google Gemini)."
    ),
    version="1.0.0"
)

# 3. Middleware CORS (Modificable según producción)
# En OCI podemos acotar el origen si se conecta con un frontend específico,
# pero dejamos wildcard temporal para pruebas de integración iniciales.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Incluir rutas de la API
app.include_router(router)

# 5. Montar archivos estáticos para la interfaz de usuario
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Alura Agente Corporativo</h1><p>Interfaz no encontrada en src/static/index.html. Por favor cree este archivo.</p>")

if __name__ == "__main__":
    # Levantar el servidor Uvicorn en el puerto definido
    print(f"[STARTUP] Servidor corriendo en http://localhost:{settings.PORT}")
    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
