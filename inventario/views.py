# inventario/views.py

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils.html import conditional_escape
from django.db import transaction  # Para guardar todo o nada si hay error
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

# Importamos Modelos
from .models import (
    Producto, Filamento, Pieza, ItemPedido, 
    Pedido, Proyecto, ItemPiezaPedido, ComposicionProducto, Insumo, ComposicionInsumo
)

# Importamos Formularios
from .forms import (
    PedidoForm, ClienteForm, ItemPedidoFormSet, 
    LogoForm, ProyectoForm, ItemPiezaFormSet
)


# =========================================================
# 1. CREACIÓN CENTRALIZADA (PEDIDOS Y PROYECTOS)
# =========================================================
@login_required
def crear_pedido(request):
    """
    Vista maestra para crear:
    1. Pedidos de Venta (Con Productos y/o Piezas sueltas)
    2. Proyectos (De Clientes o Internos)
    """
    # Inicializamos Formularios
    pedido_form = PedidoForm(request.POST or None)
    cliente_form = ClienteForm(request.POST or None)
    proyecto_form = ProyectoForm(request.POST or None, request.FILES or None)
    
    # Formsets (Listas de items) con prefijos únicos para no mezclarse
    prod_formset = ItemPedidoFormSet(request.POST or None, prefix='productos')
    pieza_formset = ItemPiezaFormSet(request.POST or None, prefix='piezas')

    # Datos para Javascript de precios
    productos = Producto.objects.all()
    precios = {p.id: float(p.precio) for p in productos}

    if request.method == "POST":
        # ¿Qué estamos creando?
        tipo_creacion = request.POST.get('tipo_creacion', 'pedido') # 'pedido' o 'proyecto'
        es_interno = request.POST.get('proyecto_interno') == 'on'   # Checkbox de proyecto interno

        try:
            with transaction.atomic():
                # --- A. GESTIÓN DEL CLIENTE ---
                cliente = None
                
                # Solo buscamos/validamos cliente si NO es un proyecto interno
                # (Los proyectos internos pueden no tener cliente)
                necesita_cliente = not (tipo_creacion == 'proyecto' and es_interno)

                if necesita_cliente:
                    usar_nuevo_cliente = request.POST.get("usar_nuevo_cliente") == "on"
                    
                    if usar_nuevo_cliente:
                        if cliente_form.is_valid():
                            cliente = cliente_form.save()
                        else:
                            errores = cliente_form.errors.as_text()
                            raise Exception(f"Error en datos del nuevo cliente: {errores}")
                    else:
                        # Intentamos sacar el cliente del select
                        if pedido_form.is_valid():
                            cliente = pedido_form.cleaned_data["cliente"]
                        
                        # Respaldo manual por si la validación estricta falló
                        if not cliente and request.POST.get('cliente'):
                             from .models import Cliente
                             cliente = Cliente.objects.get(id=request.POST.get('cliente'))

                    if not cliente:
                        raise Exception("Debes seleccionar un cliente válido (o marcar como Proyecto Interno).")

                # --- B. GUARDADO SEGÚN TIPO ---
                
                # === CASO 1: PROYECTO ===
                if tipo_creacion == 'proyecto':
                    if proyecto_form.is_valid():
                        proyecto = proyecto_form.save(commit=False)
                        
                        if es_interno:
                            proyecto.cliente = None  # Sin cliente
                        else:
                            proyecto.cliente = cliente # Asignamos al cliente seleccionado
                            
                        proyecto.save()
                        messages.success(request, f"🚀 Proyecto '{proyecto.nombre}' iniciado correctamente.")
                        return redirect("kanban_proyectos")
                    else:
                        raise Exception(f"Error en formulario de proyecto: {proyecto_form.errors.as_text()}")

                # === CASO 2: PEDIDO DE VENTA ===
                else:
                    if pedido_form.is_valid():
                        pedido = pedido_form.save(commit=False)
                        pedido.cliente = cliente # El cliente es obligatorio aquí
                        pedido.save()

                        # Guardamos las listas de items vinculadas al pedido
                        prod_formset = ItemPedidoFormSet(request.POST, instance=pedido, prefix='productos')
                        pieza_formset = ItemPiezaFormSet(request.POST, instance=pedido, prefix='piezas')

                        if prod_formset.is_valid() and pieza_formset.is_valid():
                            prod_formset.save()   # Guardar Productos
                            pieza_formset.save()  # Guardar Piezas Sueltas
                            
                            messages.success(request, f"💰 Pedido #{pedido.id} creado exitosamente.")
                            return redirect("lista_pedidos")
                        else:
                            # Recopilar errores de las listas
                            err_txt = ""
                            if prod_formset.errors: err_txt += f"Productos: {prod_formset.errors} "
                            if pieza_formset.errors: err_txt += f"Piezas: {pieza_formset.errors}"
                            raise Exception(f"Error en los items: {err_txt}")
                    else:
                        raise Exception(f"Error en el encabezado del pedido: {pedido_form.errors.as_text()}")

        except Exception as e:
            messages.error(request, f"⚠️ No se pudo guardar: {str(e)}")

    # Renderizar plantilla
    return render(
        request,
        "inventario/crear_pedido.html",
        {
            "pedido_form": pedido_form,
            "cliente_form": cliente_form,
            "proyecto_form": proyecto_form,
            "formset": prod_formset,       # Productos
            "pieza_formset": pieza_formset, # Piezas
            "precios_json": json.dumps(precios),
        },
    )


# =========================================================
# 2. VISTAS KANBAN (TABLEROS)
# =========================================================

@login_required
def kanban_ventas(request):
    """Vista completa para Ventas/Administración"""
    context = {
        'venta': Pedido.objects.filter(estado_entrega='VENTA'),
        'cola': Pedido.objects.filter(estado_entrega='COLA'),
        'proceso': Pedido.objects.filter(estado_entrega='PROCESO'),
        'listo': Pedido.objects.filter(estado_entrega='LISTO'),
        'entregados': Pedido.objects.filter(estado_entrega='ENTREGADO').order_by('-fecha_creacion')[:10],
        'modo_taller': False
    }
    return render(request, 'inventario/tablero_kanban.html', context)

@login_required
def kanban_taller(request):
    """Vista filtrada para Producción (Sin precios, solo trabajo)"""
    # Calculamos carga sumando items de productos + items de piezas
    pedidos_activos = Pedido.objects.filter(estado_entrega__in=['COLA', 'PROCESO'])
    carga = sum(p.items.count() + p.items_pieza.count() for p in pedidos_activos)

    context = {
        'cola': Pedido.objects.filter(estado_entrega='COLA'),
        'proceso': Pedido.objects.filter(estado_entrega='PROCESO'),
        'listo': Pedido.objects.filter(estado_entrega='LISTO'),
        'carga_trabajo': carga,
        'modo_taller': True
    }
    return render(request, 'inventario/tablero_kanban.html', context)

@login_required
def kanban_proyectos(request):
    """Vista para el Laboratorio de Proyectos"""
    proyectos = Proyecto.objects.all()
    return render(request, 'inventario/kanban_proyectos.html', {'proyectos': proyectos})

@login_required
def tablero_kanban(request):
    """(Redirección por compatibilidad)"""
    return redirect('kanban_ventas')


# =========================================================
# 3. APIs PARA MOVER TARJETAS (AJAX)
# =========================================================

@login_required
def actualizar_estado_pedido(request):
    """Mueve un Pedido entre columnas del Kanban"""
    if request.method == "POST":
        data = json.loads(request.body)
        pedido_id = data.get("id")
        nuevo_estado = data.get("estado")

        try:
            pedido = Pedido.objects.get(pk=pedido_id)
            pedido.estado_entrega = nuevo_estado
            pedido.save()
            return JsonResponse({"status": "ok", "mensaje": f"Movido a {nuevo_estado}"})
        except Pedido.DoesNotExist:
            return JsonResponse({"status": "error", "mensaje": "Pedido no encontrado"}, status=404)

    return JsonResponse({"status": "error"}, status=400)

@csrf_exempt
def actualizar_estado_proyecto(request):
    """Mueve un Proyecto entre fases"""
    if request.method == 'POST':
        data = json.loads(request.body)
        proyecto_id = data.get('id')
        nuevo_estado = data.get('estado')
        
        try:
            proy = Proyecto.objects.get(id=proyecto_id)
            proy.estado = nuevo_estado
            proy.save()
            return JsonResponse({'status': 'success'})
        except Proyecto.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Proyecto no encontrado'})
            
    return JsonResponse({'status': 'error', 'message': 'Método no válido'})


# =========================================================
# 4. LISTAS Y DASHBOARDS
# =========================================================

@login_required
def lista_pedidos(request):
    # Ordenamos: Primero los no entregados, luego los más nuevos
    pedidos = Pedido.objects.all().order_by("estado_entrega", "-fecha_creacion")
    return render(request, "inventario/lista_pedidos.html", {"pedidos": pedidos})

@login_required
def dashboard_simple(request):
    """Dashboard Gráfico Principal"""
    # 1. Filamentos (Ordenados por stock bajo)
    filamentos_ordenados = sorted(Filamento.objects.all(), key=lambda f: f.stock_total)

    # 2. Resumen de Productos
    productos = Producto.objects.all()
    resumen_productos = []
    for p in productos:
        resumen_productos.append({
            "obj": p,
            "listos_venta": p.stock_armado,
            "listos_armar": p.cantidad_armable_hoy(),
        })
        
    # 3. Gráfico Histórico (Agrupado por Mes)
    historico = Pedido.objects.annotate(
        mes=TruncMonth('fecha_creacion')
    ).values('mes').annotate(
        total_creados=Count('id'),
        total_entregados=Count('id', filter=Q(estado_entrega='ENTREGADO'))
    ).order_by('mes')
    
    labels_meses = []
    data_creados = []
    data_entregados = []
    
    for h in historico:
        if h['mes']:
            nombre_mes = h['mes'].strftime("%b %Y") 
            labels_meses.append(nombre_mes)
            data_creados.append(h['total_creados'])
            data_entregados.append(h['total_entregados'])

    context = {
        'filamentos': filamentos_ordenados,
        'productos': resumen_productos,
        'grafico_labels': labels_meses,
        'grafico_creados': data_creados,
        'grafico_entregados': data_entregados,
    }

    return render(request, "inventario/dashboard_simple.html", context)

@login_required
def dashboard_produccion(request):
    """Dashboard Técnico detallado"""
    filamentos = Filamento.objects.all()
    filamentos_criticos = [f for f in filamentos if f.stock_total < 1000]

    productos = Producto.objects.all()
    lista_productos = []

    for p in productos:
        analisis_armado = p.se_puede_armar()
        lista_productos.append({
            "producto": p,
            "se_puede_armar": analisis_armado["viable"],
            "faltantes_armado": analisis_armado["errores"],
        })

    piezas = Pieza.objects.all()

    contexto = {
        "alertas_compra": filamentos_criticos,
        "lista_productos": lista_productos,
        "lista_piezas": piezas,
    }
    return render(request, "inventario/dashboard.html", contexto)

@login_required
def detalle_producto(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)

    # Info de Piezas (Barritas de progreso)
    piezas_info = []
    composicion = producto.composicionproducto_set.all()

    for item in composicion:
        equivalencia = item.pieza.stock_fisico / item.cantidad if item.cantidad > 0 else 0
        piezas_info.append({
            "pieza": item.pieza,
            "requerido": item.cantidad,
            "tengo": item.pieza.stock_fisico,
            "equivalencia": round(equivalencia, 1),
            "porcentaje": min((equivalencia * 100), 100),
        })

    # Demanda Pendiente (Pedidos en Proceso)
    resultado_suma = ItemPedido.objects.filter(
        producto=producto, pedido__estado_entrega="PROCESO"
    ).aggregate(total=Sum("cantidad"))

    cantidad_pendiente = resultado_suma["total"] or 0
    faltante = max(0, cantidad_pendiente - producto.stock_armado)
    
    tipos_filamento = Filamento.TIPOS # <--- NUEVO: Pasamos las opciones del modelo
    
    return render(request, "inventario/detalle_producto.html", {
        "producto": producto,
        "piezas": piezas_info,
        "demanda_pendiente": cantidad_pendiente,
        "cantidad_faltante": faltante,
        "puede_armar": producto.cantidad_armable_hoy() > 0,
        # Nuevos datos para formularios de agregado
        "todas_piezas": Pieza.objects.all().order_by('nombre'),
        "filamentos": Filamento.objects.all(),
        "tipos_filamento": tipos_filamento,
        "insumos_disponibles": Insumo.objects.all().order_by('nombre'), 
    })


# =========================================================
# 5. ACCIONES DE STOCK (IMPRIMIR, ARMAR, VENDER)
# =========================================================

@login_required
def accion_imprimir_pieza(request, pieza_id):
    if request.method == "POST":
        pieza = get_object_or_404(Pieza, pk=pieza_id)
        cantidad = int(request.POST.get("cantidad", 1))
        
        peso_unitario = pieza.peso_gramos if pieza.peso_gramos is not None else 0.0
        peso_total = peso_unitario * cantidad

        # Si no hay peso registrado, solo advertimos
        if peso_total == 0:
            messages.warning(request, f"⚠️ La pieza '{pieza.nombre}' no tiene peso. No se descontó filamento.")
            pieza.stock_fisico += cantidad
            pieza.save()
            return redirect(request.POST.get("next") or "dashboard")

        # Intentamos descontar material
        if pieza.material.descontar_material(peso_total):
            pieza.stock_fisico += cantidad
            pieza.save()
            messages.success(request, f"🖨️ Se imprimieron {cantidad} unidades de {pieza.nombre}.")
        else:
            messages.error(request, f"❌ No hay suficiente filamento {pieza.material.color}.")

    return redirect(request.POST.get("next") or "dashboard")

@login_required
def accion_armar_producto(request, producto_id):
    if request.method == "POST":
        producto = get_object_or_404(Producto, pk=producto_id)
        analisis = producto.se_puede_armar()

        if analisis["viable"]:
            # Descontar piezas
            for item in producto.composicionproducto_set.all():
                item.pieza.stock_fisico -= item.cantidad
                item.pieza.save()

            producto.stock_armado += 1
            producto.save()
            messages.success(request, f"🔧 ¡{producto.nombre} ARMADO! Stock actualizado.")
        else:
            messages.error(request, "❌ Faltan piezas impresas para armar este producto.")

    return redirect(request.POST.get("next") or "dashboard")

@login_required
def accion_vender_producto(request, producto_id):
    if request.method == "POST":
        producto = get_object_or_404(Producto, pk=producto_id)

        if producto.stock_armado > 0:
            producto.stock_armado -= 1
            producto.ventas += 1
            producto.save()
            messages.success(request, f"💰 ¡Venta registrada! Quedan {producto.stock_armado} en stock.")
        else:
            messages.error(request, "❌ No tienes stock armado para vender.")

    return redirect(request.POST.get("next") or "dashboard")


@login_required
def accion_agregar_pieza_composicion(request, producto_id):
    """Agrega una pieza existente a la receta del producto."""
    if request.method == "POST":
        producto = get_object_or_404(Producto, pk=producto_id)
        pieza_id = request.POST.get("pieza_id")
        cantidad = int(request.POST.get("cantidad", 1))

        if pieza_id:
            pieza = get_object_or_404(Pieza, pk=pieza_id)
            
            # Buscar si ya existe la relación, si sí, sumamos. Si no, creamos.
            item, created = ComposicionProducto.objects.get_or_create(
                producto=producto,
                pieza=pieza,
                defaults={'cantidad': cantidad}
            )
            
            if not created:
                # Si ya existía, actualizamos la cantidad (opcional: sumar o reemplazar. Aquí reemplazamos/sumamos)
                # Lógica: Si el usuario pone "2", ¿quiere que sean 2 en total o sumar 2?
                # UX Estándar: "Agregar" suele ser sumar, pero en configuración de producto suele ser "Definir cantidad".
                # Aquí haremos algo inteligente: Si viene de un form "Agregar", sumamos.
                item.cantidad += cantidad
                item.save()
                messages.success(request, f"Actualizado: Ahora requiere {item.cantidad}x {pieza.nombre}")
            else:
                messages.success(request, f"Agregada: {cantidad}x {pieza.nombre}")
        
    return redirect("detalle_producto", producto_id=producto_id)


@login_required
def accion_crear_pieza_superrapida(request, producto_id):
    """Crea una pieza nueva y la agrega al producto en un solo paso."""
    if request.method == "POST":
        producto = get_object_or_404(Producto, pk=producto_id)
        
        nombre = request.POST.get("nombre")
        material_id = request.POST.get("material_id")
        cantidad_requerida = int(request.POST.get("cantidad_requerida", 1))
        
        # Archivos opcionales
        archivo_gcode = request.FILES.get("archivo_gcode")
        archivo_stl = request.FILES.get("archivo_stl")

        if nombre and material_id:
            try:
                filamento = Filamento.objects.get(pk=material_id)
                
                nueva_pieza = Pieza.objects.create(
                    nombre=nombre,
                    material=filamento,
                    archivo_gcode=archivo_gcode,
                    archivo_stl=archivo_stl
                )
                
                # Forzar extracción inmediata (a veces el save del create no lo coge bien si el archivo aun no esta en disco)
                if archivo_gcode:
                    try:
                        print(f"Procesando archivo: {archivo_gcode.name}")
                        # Peso
                        peso = nueva_pieza.extraer_peso_gcode()
                        if peso:
                            nueva_pieza.peso_gramos = peso
                            print(f"Peso detectado: {peso}")
                        
                        # Tiempo
                        tiempo = nueva_pieza.extraer_tiempo()
                        if tiempo:
                            nueva_pieza.tiempo_impresion = tiempo
                            print(f"Tiempo detectado: {tiempo}")
                            
                        nueva_pieza.save()
                    except Exception as e:
                        print(f"Error procesando GCode en vista: {e}")
                
                # Crear la relación automáticamente
                ComposicionProducto.objects.create(
                    producto=producto,
                    pieza=nueva_pieza,
                    cantidad=cantidad_requerida
                )
                
                messages.success(request, f"✨ Pieza '{nombre}' creada y vinculada correctamente.")
                
            except Exception as e:
                messages.error(request, f"Error creando pieza: {e}")
        else:
            messages.error(request, "Faltan datos obligatorios (Nombre o Material).")

    return redirect("detalle_producto", producto_id=producto_id)


# =========================================================
# 6. API STOCK (CONTROL INTERACTIVO)
# =========================================================

@login_required
def api_control_stock_pieza(request, pieza_id):
    """
    API para controlar stock:
    - accion: 'imprimir' (+1 y resta material), 'ajustar' (delta simple), 'fijar' (set manual)
    - cantidad: int
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            accion = data.get("accion") # imprimir, ajustar, fijar
            cantidad = float(data.get("cantidad", 0)) # Puede ser negativo
            
            pieza = get_object_or_404(Pieza, pk=pieza_id)
            mensaje = ""
            status = "ok"

            if accion == "imprimir":
                # Lógica completa de impresión (Consumo de material)
                peso_total = (pieza.peso_gramos or 0) * cantidad
                if peso_total > 0:
                    if pieza.material.descontar_material(peso_total):
                        pieza.stock_fisico += int(cantidad)
                        mensaje = f"Impresa: +{int(cantidad)} (Stock: {pieza.stock_fisico})"
                    else:
                        status = "error"
                        mensaje = f"Sin filamento suficiente ({pieza.material.color})"
                else:
                    # Sin peso, solo sumamos
                    pieza.stock_fisico += int(cantidad)
                    mensaje = f"Impresa (Sin peso): +{int(cantidad)}"

            elif accion == "ajustar":
                # Solo suma/resta el número (Corrige stock)
                pieza.stock_fisico += int(cantidad)
                # Evitar negativos
                if pieza.stock_fisico < 0: pieza.stock_fisico = 0
                mensaje = f"Ajustado: Stock actual {pieza.stock_fisico}"

            elif accion == "fijar":
                # Auditoría: Poner el número exacto
                pieza.stock_fisico = int(cantidad)
                if pieza.stock_fisico < 0: pieza.stock_fisico = 0
                mensaje = f"Fijado: Stock actual {pieza.stock_fisico}"

            pieza.save()
            return JsonResponse({"status": status, "nuevo_stock": pieza.stock_fisico, "mensaje": mensaje})

        except Exception as e:
            return JsonResponse({"status": "error", "mensaje": str(e)}, status=400)

    return JsonResponse({"status": "error", "mensaje": "Método no permitido"}, status=405)


@login_required
def api_crear_filamento(request):
    """API para crear filamento al vuelo desde modales."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            tipo = data.get("tipo")
            color = data.get("color")
            
            if not tipo or not color:
                return JsonResponse({"status": "error", "mensaje": "Faltan datos"}, status=400)
                
            filamento = Filamento.objects.create(
                tipo=tipo,
                color=color,
                cantidad_rollos=1 # Default 1 rollo al crear
            )
            
            return JsonResponse({
                "status": "ok", 
                "id": filamento.id, 
                "text": f"{filamento.tipo} - {filamento.color}"
            })
            
        except Exception as e:
            return JsonResponse({"status": "error", "mensaje": str(e)}, status=400)
            
    return JsonResponse({"status": "error", "mensaje": "Método no permitido"}, status=405)


@login_required
def api_stock_filamento(request, filamento_id):
    """API para sumar/restar rollos de filamento."""
    if request.method == "POST":
        try:
            filamento = get_object_or_404(Filamento, pk=filamento_id)
            data = json.loads(request.body)
            accion = data.get("accion") # 'sumar' o 'restar'
            
            if accion == "sumar":
                filamento.cantidad_rollos += 1
                msg = f"Rollo agregado a {filamento.tipo} {filamento.color}"
            elif accion == "restar":
                if filamento.cantidad_rollos > 0:
                    filamento.cantidad_rollos -= 1
                    msg = f"Rollo quitado de {filamento.tipo} {filamento.color}"
                else:
                    return JsonResponse({"status": "error", "mensaje": "No hay rollos para quitar"}, status=400)
            else:
                 return JsonResponse({"status": "error", "mensaje": "Acción desconocida"}, status=400)
            
            filamento.save()
            return JsonResponse({
                "status": "ok",
                "nuevo_stock": filamento.cantidad_rollos,
                "mensaje": msg
            })
            
        except Exception as e:
            return JsonResponse({"status": "error", "mensaje": str(e)}, status=400)

    return JsonResponse({"status": "error", "mensaje": "Método no permitido"}, status=405)


@login_required
def api_actualizar_costo_filamento(request, filamento_id):
    """API para actualizar el costo de un rollo."""
    if request.method == "POST":
        try:
            filamento = get_object_or_404(Filamento, pk=filamento_id)
            data = json.loads(request.body)
            nuevo_costo = data.get("costo")
            
            if nuevo_costo is not None:
                filamento.costo_rollo = float(nuevo_costo)
                filamento.save()
                return JsonResponse({"status": "ok", "mensaje": "Costo actualizado"})
            
            return JsonResponse({"status": "error", "mensaje": "Falta el costo"}, status=400)
            
        except Exception as e:
            return JsonResponse({"status": "error", "mensaje": str(e)}, status=400)

    return JsonResponse({"status": "error", "mensaje": "Método no permitido"}, status=405)


    return JsonResponse({"status": "error", "mensaje": "Método no permitido"}, status=405)


# =========================================================
# 8. GESTIÓN DE INSUMOS
# =========================================================

@login_required
def gestion_insumos(request):
    """Vista para gestionar stock de insumos (imanes, motores, etc)."""
    insumos = Insumo.objects.all().order_by('nombre')
    return render(request, "inventario/gestion_insumos.html", {
        "insumos": insumos
    })

@login_required
def api_stock_insumo(request, insumo_id):
    """API para sumar/restar stock de insumos."""
    if request.method == "POST":
        insumo = get_object_or_404(Insumo, pk=insumo_id)
        data = json.loads(request.body)
        accion = data.get("accion")

        if accion == "sumar":
            insumo.stock += 1
        elif accion == "restar" and insumo.stock > 0:
            insumo.stock -= 1
        
        insumo.save()
        return JsonResponse({"status": "ok", "nuevo_stock": insumo.stock})

    return JsonResponse({"status": "error", "mensaje": "Método no permitido"}, status=405)

@login_required
def api_crear_insumo(request):
    """API para crear un insumo rápido."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            nombre = data.get("nombre")
            unidad = data.get("unidad", "unidad")
            costo = data.get("costo", 0)

            if not nombre:
                return JsonResponse({"status": "error", "mensaje": "Falta nombre"})

            Insumo.objects.create(
                nombre=nombre,
                unidad=unidad,
                costo_unitario=costo
            )
            return JsonResponse({"status": "ok", "mensaje": "Insumo creado"})
        except Exception as e:
            return JsonResponse({"status": "error", "mensaje": str(e)})
            
    return JsonResponse({"status": "error", "mensaje": "Método no permitido"}, status=405)


@login_required
def api_vincular_insumo(request, producto_id):
    """Vincular un insumo existente a un producto."""
    if request.method == "POST":
        try:
            producto = get_object_or_404(Producto, pk=producto_id)
            data = json.loads(request.body)
            insumo_id = data.get("insumo_id")
            cantidad = float(data.get("cantidad", 1))
            es_opcional = data.get("es_opcional", False)

            insumo = get_object_or_404(Insumo, pk=insumo_id)
            
            # Crear o actualizar vinculo
            comp, created = ComposicionInsumo.objects.update_or_create(
                producto=producto,
                insumo=insumo,
                defaults={'cantidad': cantidad, 'es_opcional': es_opcional}
            )
            
            return JsonResponse({"status": "ok"})
        except Exception as e:
            return JsonResponse({"status": "error", "mensaje": str(e)})

    return JsonResponse({"status": "error", "mensaje": "Método no permitido"}, status=405)

def api_crear_logo(request):
    if request.method == 'POST':
        form = LogoForm(request.POST, request.FILES)
        if form.is_valid():
            logo = form.save()
            return JsonResponse({'status': 'ok', 'id': logo.id, 'nombre': logo.nombre})
        else:
            return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
    
    return JsonResponse({'status': 'error', 'mensaje': 'Método no permitido'}, status=405)


@login_required
def gestion_filamentos(request):
    """Vista dedicada para gestión de rollos de filamento."""
    filamentos = Filamento.objects.all().order_by('tipo', 'color')
    return render(request, "inventario/gestion_filamentos.html", {
        "filamentos": filamentos
    })
