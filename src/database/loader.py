import os
import pandas as pd
from src.database.connection import engine

DATA_DIR = "data"

def init_db():
    # 1. Validar la existencia de la carpeta de datos
    if not os.path.exists(DATA_DIR):
        print(f"[DB] Error: No se encontró el directorio de datos: {DATA_DIR}")
        return
        
    # 2. Listar todos los archivos CSV en la carpeta data/
    csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]
    if not csv_files:
        print("[DB] No se encontraron archivos CSV para cargar en la base de datos.")
        return
        
    print(f"[DB] Inicializando base de datos SQLite con {len(csv_files)} archivos CSV...")
    
    # 3. Cargar dinámicamente cada CSV en una tabla de SQLite
    for filename in csv_files:
        table_name = os.path.splitext(filename)[0]
        filepath = os.path.join(DATA_DIR, filename)
        
        try:
            print(f"[DB] Cargando '{filename}' en la tabla '{table_name}'...")
            
            # Cargar con pandas
            df = pd.read_csv(filepath)
            
            # Convertir columnas que parezcan fechas a formato string estandar de fecha para SQLite
            for col in df.columns:
                if 'fecha' in col.lower() or 'estimada' in col.lower() or 'entrega' in col.lower():
                    try:
                        df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d')
                    except Exception:
                        pass # Si falla, dejar el tipo por defecto
            
            # Guardar en SQLite (Reemplaza la tabla si existe para mantenerla sincronizada con los CSVs)
            df.to_sql(table_name, engine, if_exists="replace", index=False)
            
            # Obtener conteo de registros insertados
            print(f"[DB] Tabla '{table_name}' creada/actualizada exitosamente con {len(df)} registros.")
            
        except Exception as e:
            print(f"[DB] Error cargando tabla '{table_name}': {e}")
            
    print("[DB] Sincronización de base de datos relacional finalizada con éxito.")

if __name__ == "__main__":
    init_db()
