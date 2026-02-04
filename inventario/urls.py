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
    # Nuevo: Gestión de Composición
    path("producto/<int:producto_id>/agregar-pieza/", views.accion_agregar_pieza_composicion, name="agregar_pieza_composicion"),
    path("producto/<int:producto_id>/crear-pieza-rapida/", views.accion_crear_pieza_superrapida, name="crear_pieza_superrapida"),
    
    path("pedidos/", views.lista_pedidos, name="lista_pedidos"),
    path("pedidos/nuevo/", views.crear_pedido, name="crear_pedido"),
    # kanban
    path("kanban/ventas/", views.kanban_ventas, name="kanban_ventas"),
    path("kanban/taller/", views.kanban_taller, name="kanban_taller"),
    path("proyectos/", views.kanban_proyectos, name="kanban_proyectos"),
    path("filamentos/", views.gestion_filamentos, name="gestion_filamentos"),
    path("api/mover-pedido/", views.actualizar_estado_pedido, name="api_mover_pedido"),
    path("api/stock-pieza/<int:pieza_id>/", views.api_control_stock_pieza, name="api_control_stock_pieza"),
    path("api/stock-filamento/<int:filamento_id>/", views.api_stock_filamento, name="api_stock_filamento"),
    path("api/costo-filamento/<int:filamento_id>/", views.api_actualizar_costo_filamento, name="api_actualizar_costo_filamento"),
    path("api/crear-filamento/", views.api_crear_filamento, name="api_crear_filamento"),
    
    # Insumos
    path("insumos/", views.gestion_insumos, name="gestion_insumos"),
    path("api/stock-insumo/<int:insumo_id>/", views.api_stock_insumo, name="api_stock_insumo"),
    path("api/crear-insumo/", views.api_crear_insumo, name="api_crear_insumo"),
    path("api/vincular-insumo/<int:producto_id>/", views.api_vincular_insumo, name="api_vincular_insumo"),
    path('api/crear-logo/', views.api_crear_logo, name='api_crear_logo'),
    path('api/mover-proyecto/', views.actualizar_estado_proyecto, name='api_mover_proyecto'),
]
