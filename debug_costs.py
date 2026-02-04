import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_3d.settings')
django.setup()

from inventario.models import Producto, Pieza, Filamento

try:
    p = Producto.objects.get(id=2)
    print(f"Producto: {p.nombre} | ID: {p.id}")
    print(f"Precio Venta: {p.precio}")
    print(f"Costo Total Calc: {p.costo_total}")
    print("-" * 30)

    for item in p.composicionproducto_set.all():
        pieza = item.pieza
        mat = pieza.material
        print(f"Pieza: {pieza.nombre}")
        print(f"  - Peso (g): {pieza.peso_gramos}")
        print(f"  - Material: {mat.tipo} {mat.color}")
        print(f"  - Costo Rollo: {mat.costo_rollo}")
        print(f"  - Costo/g: {mat.costo_por_gramo}")
        print(f"  - Costo Estimado Pieza: {pieza.costo_estimado}")
        print("-" * 10)

    print("-" * 30)

except Producto.DoesNotExist:
    print("Producto ID 2 no encontrado")

print("-" * 30)
print("All Filaments:")
for f in Filamento.objects.all():
    print(f"ID: {f.id} | {f.tipo} {f.color} | Costo: {f.costo_rollo}")
