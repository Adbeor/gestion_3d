from django.contrib import admin

from .models import Filamento, Pieza, Producto, ComposicionProducto

admin.site.register(Filamento)
admin.site.register(Pieza)
admin.site.register(Producto)
admin.site.register(ComposicionProducto)


