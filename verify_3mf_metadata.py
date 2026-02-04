import os
import django
import zipfile
from io import BytesIO
from django.core.files.base import ContentFile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_3d.settings')
django.setup()

from inventario.models import Pieza, Filamento

# 1. Crear contenido Dummy 3MF (Zip)
buffer = BytesIO()
with zipfile.ZipFile(buffer, 'w') as z:
    # Simular Metadata/slice_info.config de Bambu (Formato XML Nuevo)
    config_content = """
    <metadata key="header" value="header"/>
    <metadata key="weight" value="45.50"/>
    <metadata key="estimated_time" value="7265"/>
    <metadata key="consumption_weight" value="45.50"/>
    """
    z.writestr("Metadata/slice_info.config", config_content)
    
    # Agregar un archivo dummy gcode por si acaso
    z.writestr("Metadata/plate_1.gcode", "; dummy gcode")

buffer.seek(0)

# 2. Crear Pieza con ese archivo
try:
    print("Creando Pieza de prueba...")
    # Necesitamos un material dummy si es required, filamento puede ser nulo o existente
    filamento = Filamento.objects.first() # Usar el primero que haya
    
    pieza = Pieza(nombre="Test 3MF Metadata", material=filamento)
    pieza.archivo_gcode.save("test_metadata.3mf", ContentFile(buffer.getvalue()), save=False)
    
    # 3. Probar Extracción
    print("Probando extracción de PESO...")
    peso = pieza.extraer_peso_gcode()
    print(f"Peso extraído: {peso} (Esperado: 45.50)")
    
    print("Probando extracción de TIEMPO...")
    tiempo = pieza.extraer_tiempo()
    print(f"Tiempo extraído: {tiempo} (Esperado: 2h1m)")
    
    if peso == 45.50 and tiempo == "2h1m":
        print("✅ ÉXITO: Metadata leída correctamente")
    else:
        print("❌ FALLO: Valores incorrectos")

except Exception as e:
    print(f"Error en el test: {e}")
