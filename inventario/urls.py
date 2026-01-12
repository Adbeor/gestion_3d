from django.urls import path
from . import views

# inventario/urls.py
urlpatterns = [
    path("", views.dashboard_simple, name="dashboard"),  # Cambiamos a una vista simple
    path(
        "producto/<int:producto_id>/", views.detalle_producto, name="detalle_producto"
    ),  # Nueva vista detalle
    # Mantenemos las acciones de imprimir/armar/vender pero ocultas de la URL principal
    path(
        "imprimir/<int:pieza_id>/", views.accion_imprimir_pieza, name="imprimir_pieza"
    ),
    path(
        "armar/<int:producto_id>/", views.accion_armar_producto, name="armar_producto"
    ),
    path(
        "vender/<int:producto_id>/",
        views.accion_vender_producto,
        name="vender_producto",
    ),
    path("pedidos/", views.lista_pedidos, name="lista_pedidos"),
    path("pedidos/nuevo/", views.crear_pedido, name="crear_pedido"),
    # kanban
    path("kanban/", views.tablero_kanban, name="tablero_kanban"),
    path("api/mover-pedido/", views.actualizar_estado_pedido, name="api_mover_pedido"),
    path('api/crear-logo/', views.api_crear_logo, name='api_crear_logo'),
]
