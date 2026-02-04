import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_3d.settings')
django.setup()

from inventario.models import Producto, Insumo, ComposicionInsumo

# 1. Crear Insumo
nombre = "Imán Neodimio Test"
insumo, created = Insumo.objects.get_or_create(
    nombre=nombre,
    defaults={'stock': 10, 'costo_unitario': 2.50, 'unidad': 'unidad'}
)
print(f"Insumo: {insumo.nombre} | Stock: {insumo.stock} | Costo: {insumo.costo_unitario}")

# 2. Asignar a Producto ID 2
try:
    producto = Producto.objects.get(id=2)
    # Limpiar previos para test limpio
    ComposicionInsumo.objects.filter(producto=producto, insumo=insumo).delete()
    
    # Crear dos enlaces: uno obligatorio y uno opcional
    comp_ob = ComposicionInsumo.objects.create(producto=producto, insumo=insumo, cantidad=2, es_opcional=False)
    # Crear otro insumo opcional
    insumo_op, _ = Insumo.objects.get_or_create(nombre="Acrílico Cover Test", defaults={'costo_unitario': 20.00})
    comp_op = ComposicionInsumo.objects.create(producto=producto, insumo=insumo_op, cantidad=1, es_opcional=True)
    
    print(f"Asignado a Producto: {producto.nombre}")
    
    # 3. Verificar Costo (Solo debe sumar los obligatorios)
    # Costo previo de piezas (sabíamos que era 0.0 + 65.00 de PLA que corregimos manual, espera, PLA costaba por gramo)
    # Asumamos que piezas cuestan X. El insumo suma 2 * 2.50 = 5.00
    costo_total = producto.costo_total
    print(f"Costo Total del Producto: {costo_total}")
    
    # 4. Verificar Disponibilidad
    # Insumo stock = 10. Necesita 2. Debe ser viable.
    analisis = producto.analizar_disponibilidad_completa()
    print(f"Viabilidad: {analisis['viable']}")
    
    if analisis['viable']:
        print("✅ Viabilidad OK")
        
    # Test Fallo: Reducir stock insumo
    insumo.stock = 1
    insumo.save()
    analisis_fail = producto.analizar_disponibilidad_completa()
    print(f"Viabilidad (Stock bajo): {analisis_fail['viable']}")
    if not analisis_fail['viable']:
         print("✅ Detectó falta de insumo correctamente")
         
    # Restaurar
    insumo.stock = 10
    insumo.save()

except Producto.DoesNotExist:
    print("Producto 2 no existe")
except Exception as e:
    print(f"Error: {e}")
