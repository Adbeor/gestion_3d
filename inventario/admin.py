from django.contrib import admin

from .models import (
    Filamento,
    Pieza,
    Producto,
    ComposicionProducto,
    Cliente,
    Pedido,
    ItemPedido,
)

admin.site.register(Filamento)

admin.site.register(Cliente)


class PiezaAdmin(admin.ModelAdmin):
    search_fields = ["nombre"]  # <--- Obligatorio para el autocompletado
    list_display = ("nombre", "material", "peso_gramos", "stock_fisico")


# 2. Configuración de la "Tablita" (Inline) de la Receta
class ComposicionInline(admin.TabularInline):
    model = ComposicionProducto
    extra = 1
    autocomplete_fields = ["pieza"]  # Esto permite buscar la pieza escribiendo


admin.site.register(Pieza, PiezaAdmin)  # Registramos Pieza con su buscador


# 3. Configuración de PRODUCTO (Con la tablita adentro)


# Asegúrate de importar los nuevos modelos
class ProductoAdmin(admin.ModelAdmin):
    # ESTA LÍNEA ES LA CURA DEL ERROR:
    search_fields = ["nombre"]

    # Opcional: Para que se vea bonito el listado de productos
    list_display = ("nombre", "precio", "stock_armado")

    inlines = [ComposicionInline]


admin.site.register(Producto, ProductoAdmin)


# 1. Creamos el "Inline" (la tablita dentro del pedido)
class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 1  # Cuántas filas vacías mostrar por defecto
    autocomplete_fields = [
        "producto"
    ]  # Útil si tienes muchos productos (requiere config extra, opcional)


# 2. Configuramos el Admin del Pedido
class PedidoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cliente",
        "fecha_creacion",
        "estado_pago",
        "estado_entrega",
        "total_calculado",
    )
    list_filter = ("estado_pago", "estado_entrega", "fecha_creacion")
    search_fields = ("cliente__nombre", "id")
    inlines = [ItemPedidoInline]  # <--- AQUÍ CONECTAMOS LA TABLITA

    # Un truco para mostrar el total calculado en la lista del admin
    def total_calculado(self, obj):
        return f"S/ {obj.total_pedido}"

    total_calculado.short_description = "Total"


# 3. Registramos todo
# ItemPedido no hace falta registrarlo solo, porque ya vive dentro de PedidoAdmin

admin.site.register(Pedido, PedidoAdmin)
