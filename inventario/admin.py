from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Filamento,
    Pieza,
    Producto,
    ComposicionProducto,
    Cliente,
    Pedido,
    ItemPedido,
    ItemPedido,
    Logo,
    Insumo,
    ComposicionInsumo,
)

admin.site.register(Insumo)

admin.site.register(Filamento)

admin.site.register(Cliente)

admin.site.register(Logo)


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


class ComposicionInsumoInline(admin.TabularInline):
    model = ComposicionInsumo
    extra = 1
    autocomplete_fields = ["insumo"] # Busca insumos por nombre (necesita search_fields en InsumoAdmin)

class InsumoAdmin(admin.ModelAdmin):
    search_fields = ["nombre"]
    list_display = ("nombre", "stock", "unidad", "costo_unitario")

admin.site.unregister(Insumo) # Evitar doble registro si lo hice arriba simple
admin.site.register(Insumo, InsumoAdmin)

# Asegúrate de importar los nuevos modelos
class ProductoAdmin(admin.ModelAdmin):
    # ESTA LÍNEA ES LA CURA DEL ERROR:
    search_fields = ["nombre"]

    # Opcional: Para que se vea bonito el listado de productos
    list_display = ("nombre", "precio", "stock_armado")

    inlines = [ComposicionInline, ComposicionInsumoInline]


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
        "fecha_entrega_estimada",
        "resumen_productos",
        "estado_pago",
        "estado_entrega",
        "total_calculado",
    )
    list_filter = ("estado_pago", "estado_entrega", "fecha_entrega_estimada")
    search_fields = ("cliente__nombre", "id", "fecha_entrega_estimada")
    inlines = [ItemPedidoInline]  # <--- AQUÍ CONECTAMOS LA TABLITA

    # Un truco para mostrar el total calculado en la lista del admin
    def total_calculado(self, obj):
        return f"S/ {obj.total_pedido}"

    total_calculado.short_description = "Total"

    def resumen_productos(self, obj):
        # 1. Obtenemos todos los items de este pedido
        # Usamos .select_related para que sea rápido y no haga mil consultas
        items = obj.items.all()

        # 2. Creamos una lista de textos (Ej: "2x Molino SAG")
        lista_html = []
        for item in items:
            lista_html.append(
                f"• <strong>{item.cantidad}x</strong> {item.producto.nombre}"
            )

        # 3. Unimos todo con un salto de línea HTML (<br>)
        return format_html("<br>".join(lista_html))

    resumen_productos.short_description = "Contenido del Pedido"

    # OPTIMIZACIÓN (Tip Pro):
    # Esto evita que el Admin se vuelva lento si tienes muchos pedidos.
    # Le dice a Django: "Trae los items y los productos de una sola vez".
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related("items__producto")


# 3. Registramos todo
# ItemPedido no hace falta registrarlo solo, porque ya vive dentro de PedidoAdmin

admin.site.register(Pedido, PedidoAdmin)
