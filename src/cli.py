import sys
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env
load_dotenv()

from src.database.loader import init_db
from src.services.agent_service import get_agent_service

def main():
    print("=== Inicializando Base de Datos ===")
    init_db()
    
    print("\n=== Inicializando Agente SQL con Gemini ===")
    try:
        agent_svc = get_agent_service()
    except Exception as e:
        print(f"Error de inicialización: {e}")
        print("Asegúrate de configurar GEMINI_API_KEY en tu archivo .env o en tus variables de entorno.")
        sys.exit(1)
        
    print("\n=== Conectando con Alura Agente ===")
    # Generar un saludo inicial conversacional automatizado al arrancar el programa
    try:
        saludo_inicial = agent_svc.ask("hola")
        print(f"\nAgente: {saludo_inicial['answer']}\n")
    except Exception as e:
        print(f"\nAgente: ¡Hola! Soy el Alura Agente de Andes Cargo. ¿En qué puedo ayudarte hoy? (Error de conexión: {e})\n")
    
    print("(Escribe tu pregunta o 'salir' para terminar)\n")
    
    while True:
        try:
            query = input("Colaborador: ")
            if query.lower().strip() in ["salir", "exit", "quit"]:
                print("¡Hasta luego!")
                break
                
            if query.lower().strip() in ["limpiar", "clear"]:
                agent_svc.clear_history()
                print("\n[Sistema: El historial de conversación ha sido limpiado. ¡Iniciamos una nueva sesión!]\n")
                continue
                
            if not query.strip():
                continue
                
            print("Agente pensando...")
            result = agent_svc.ask(query)
            
            # Imprimir siempre la respuesta conversacional formulada de forma limpia
            print(f"\nAgente: {result['answer']}\n")
        except KeyboardInterrupt:
            print("\n¡Hasta luego!")
            break
        except Exception as e:
            print(f"\nOcurrió un error inesperado: {e}\n")

if __name__ == "__main__":
    main()
