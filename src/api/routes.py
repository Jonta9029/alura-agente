import time
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from src.database.connection import get_db
from src.services.agent_service import get_agent_service, AgentService
from src.api.middleware import log_agent_execution

router = APIRouter(prefix="/api")

class QueryRequest(BaseModel):
    query: str = Field(..., description="La pregunta en lenguaje natural para el agente de IA corporativo.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "¿Cuál es el empleado con mayor salario en el departamento de Tecnología?"
            }
        }
    }

class QueryResponse(BaseModel):
    success: bool
    query: str
    answer: str
    latency_seconds: float

class HealthResponse(BaseModel):
    status: str
    database: str
    agent: str

@router.post("/ask", response_model=QueryResponse, status_code=status.HTTP_200_OK)
async def ask_agent(
    request: QueryRequest,
    agent_svc: AgentService = Depends(get_agent_service)
):
    """
    Ruta para enviar una pregunta al agente corporativo.
    Procesa la pregunta, genera la consulta SQL, ejecuta contra SQLite
    y devuelve la respuesta formulada en lenguaje natural.
    """
    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La pregunta no puede estar vacía."
        )
        
    start_time = time.time()
    
    # Procesar con el agente
    result = agent_svc.ask(request.query)
    
    duration = time.time() - start_time
    
    # Registrar auditoría de ejecución
    log_agent_execution(request.query, result, duration)
    
    if not result["success"]:
        # Aunque falle internamente, devolvemos success=False con el mensaje de error mitigado
        return QueryResponse(
            success=False,
            query=request.query,
            answer=result["answer"],
            latency_seconds=round(duration, 4)
        )
        
    return QueryResponse(
        success=True,
        query=request.query,
        answer=result["answer"],
        latency_seconds=round(duration, 4)
    )

@router.post("/clear", status_code=status.HTTP_200_OK)
async def clear_history(agent_svc: AgentService = Depends(get_agent_service)):
    """
    Ruta para limpiar el historial de conversación del agente.
    """
    agent_svc.clear_history()
    return {"message": "Historial de conversación limpiado exitosamente."}

@router.get("/health", response_model=HealthResponse)
async def health_check(db = Depends(get_db)):
    """
    Verifica el estado del servicio, base de datos SQLite y agente de IA.
    """
    db_status = "OK"
    agent_status = "OK"
    
    # 1. Validar conexión a DB
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"ERROR: {str(e)}"
        
    # 2. Validar que el agente de IA esté listo
    try:
        get_agent_service()
    except Exception as e:
        agent_status = f"ERROR: {str(e)}"
        
    if db_status != "OK" or agent_status != "OK":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "database": db_status,
                "agent": agent_status
            }
        )
        
    return HealthResponse(
        status="healthy",
        database=db_status,
        agent=agent_status
    )
