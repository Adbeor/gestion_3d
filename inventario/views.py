# en inventario/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Producto, Filamento, Pieza, ItemPedido, Pedido
from django.db.models import Sum  # <--- AGREGA ESTO AL PRINCIPIO CON LOS OTROS IMPORTS


def lista_pedidos(request):
    # Traemos los pedidos ordenados: Primero los pendientes, luego los recientes
    pedidos = Pedido.objects.all().order_by("estado_entrega", "-fecha_creacion")
    return render(request, "inventario/lista_pedidos.html", {"pedidos": pedidos})


def dashboard_produccion(request):
    # 1. Alertas de Filamento (Materia Prima)
    filamentos = Filamento.objects.all()
    filamentos_criticos = [f for f in filamentos if f.stock_total < 1000]

    # 2. Análisis de Productos (Ensamblaje y Venta)
    productos = Producto.objects.all()
    lista_productos = []

    for p in productos:
        analisis_armado = p.se_puede_armar()
        lista_productos.append(
            {
                "producto": p,
                "se_puede_armar": analisis_armado["viable"],
                "faltantes_armado": analisis_armado["errores"],
            }
        )

    # 3. Lista de Piezas (Para imprimir individualmente)
    piezas = Pieza.objects.all()

    contexto = {
        "alertas_compra": filamentos_criticos,
        "lista_productos": lista_productos,
        "lista_piezas": piezas,
    }
    return render(request, "inventario/dashboard.html", contexto)


# ACCIÓN 1: IMPRIMIR UNA PIEZA SUELTA
def accion_imprimir_pieza(request, pieza_id):
    if request.method == "POST":
        pieza = get_object_or_404(Pieza, pk=pieza_id)
        cantidad_a_imprimir = int(request.POST.get("cantidad", 1))

        # --- CORRECCIÓN DE SEGURIDAD ---
        # Si el peso es None, asumimos 0.0 para evitar el error
        peso_unitario = pieza.peso_gramos if pieza.peso_gramos is not None else 0.0

        peso_total = peso_unitario * cantidad_a_imprimir

        # Validación extra: Si el peso es 0, advertimos pero dejamos imprimir (para ajustar stock físico)
        if peso_total == 0:
            messages.warning(
                request,
                f"⚠️ La pieza '{pieza.nombre}' no tiene peso registrado. No se descontó filamento.",
            )
            pieza.stock_fisico += cantidad_a_imprimir
            pieza.save()
            # Redirección inteligente
            return redirect(request.POST.get("next") or "dashboard")

        # Intentamos descontar del filamento
        if pieza.material.descontar_material(peso_total):
            pieza.stock_fisico += cantidad_a_imprimir
            pieza.save()
            messages.success(
                request,
                f"🖨️ Se imprimieron {cantidad_a_imprimir} unidades de {pieza.nombre}.",
            )

        else:
            messages.error(
                request,
                f"❌ No hay suficiente filamento {pieza.material.color} para imprimir.",
            )

    # Redirección inteligente (la que ya tenías)
    direccion_retorno = request.POST.get("next")
    if direccion_retorno:
        return redirect(direccion_retorno)
    else:
        return redirect("dashboard")


# ACCIÓN 2: ARMAR UN MOLINO (Usando piezas impresas)
def accion_armar_producto(request, producto_id):
    if request.method == "POST":
        producto = get_object_or_404(Producto, pk=producto_id)
        analisis = producto.se_puede_armar()

        if analisis["viable"]:
            # Descontamos las piezas del stock físico
            for item in producto.composicionproducto_set.all():
                item.pieza.stock_fisico -= item.cantidad
                item.pieza.save()

            # Aumentamos el stock del producto terminado
            producto.stock_armado += 1
            producto.save()
            messages.success(
                request, f"🔧 ¡{producto.nombre} ARMADO! Stock listo actualizado."
            )
        else:
            messages.error(
                request, "❌ Faltan piezas impresas para armar este producto."
            )

    # --- CAMBIO IMPORTANTE AQUÍ ---
    # Buscamos si el formulario nos mandó una dirección "next"
    direccion_retorno = request.POST.get("next")

    if direccion_retorno:
        return redirect(direccion_retorno)  # Si existe, volvemos ahí (al detalle)
    else:
        return redirect("dashboard")  # Si no existe, vamos al dashboard por defecto


# ACCIÓN 3: VENDER UN MOLINO
def accion_vender_producto(request, producto_id):
    if request.method == "POST":
        producto = get_object_or_404(Producto, pk=producto_id)

        if producto.stock_armado > 0:
            producto.stock_armado -= 1
            producto.ventas += 1
            producto.save()
            messages.success(
                request,
                f"💰 ¡Venta registrada! Quedan {producto.stock_armado} en stock.",
            )
        else:
            messages.error(request, "❌ No tienes stock armado para vender.")

    # --- CAMBIO IMPORTANTE AQUÍ ---
    # Buscamos si el formulario nos mandó una dirección "next"
    direccion_retorno = request.POST.get("next")

    if direccion_retorno:
        return redirect(direccion_retorno)  # Si existe, volvemos ahí (al detalle)
    else:
        return redirect("dashboard")  # Si no existe, vamos al dashboard por defecto


from django.shortcuts import render
from .models import Producto, Filamento


def dashboard_simple(request):
    # 1. FILAMENTOS: Los ordenamos para que los que tienen poco salgan primero
    # Usamos una función lambda para ordenar por la propiedad stock_total
    todos_filamentos = Filamento.objects.all()
    filamentos_ordenados = sorted(todos_filamentos, key=lambda f: f.stock_total)

    # 2. PRODUCTOS: Solo info resumen
    productos = Producto.objects.all()
    resumen_productos = []

    for p in productos:
        resumen_productos.append(
            {
                "obj": p,
                "listos_venta": p.stock_armado,
                "listos_armar": p.cantidad_armable_hoy(),  # Usamos el método nuevo
            }
        )

    return render(
        request,
        "inventario/dashboard_simple.html",
        {"filamentos": filamentos_ordenados, "productos": resumen_productos},
    )


def detalle_producto(request, producto_id):
    # 1. Obtener el producto básico
    producto = get_object_or_404(Producto, pk=producto_id)

    # ---------------------------------------------------------
    # PARTE 1: Lógica de Piezas (Barritas de progreso)
    # ---------------------------------------------------------
    piezas_info = []
    composicion = producto.composicionproducto_set.all()

    for item in composicion:
        # Matemática: Tengo 1, necesito 2 = 0.5 Molinos
        # Agregamos una validación simple por si item.cantidad fuera 0 (seguridad)
        if item.cantidad > 0:
            equivalencia = item.pieza.stock_fisico / item.cantidad
        else:
            equivalencia = 0

        piezas_info.append(
            {
                "pieza": item.pieza,
                "requerido": item.cantidad,
                "tengo": item.pieza.stock_fisico,
                "equivalencia": round(equivalencia, 1),
                "porcentaje": min((equivalencia * 100), 100),
            }
        )

    # ---------------------------------------------------------
    # PARTE 2: Lógica de Pedidos (Demanda Pendiente)
    # ---------------------------------------------------------
    resultado_suma = ItemPedido.objects.filter(
        producto=producto, pedido__estado_entrega="PREPARACION"
    ).aggregate(total=Sum("cantidad"))

    cantidad_pendiente = resultado_suma["total"]
    if cantidad_pendiente is None:
        cantidad_pendiente = 0

    # Calculamos cuánto falta. Si el resultado es negativo (sobra stock), ponemos 0.
    faltante = max(0, cantidad_pendiente - producto.stock_armado)
    # ---------------------------------------------------------
    # PARTE 3: Enviar TODO junto al HTML
    # ---------------------------------------------------------
    return render(
        request,
        "inventario/detalle_producto.html",
        {
            "producto": producto,
            "piezas": piezas_info,  # Viene de la Parte 1
            "demanda_pendiente": cantidad_pendiente,  # Viene de la Parte 2
            "cantidad_faltante": faltante,
            "puede_armar": producto.cantidad_armable_hoy() > 0,
        },
    )
