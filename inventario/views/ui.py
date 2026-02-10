# inventario/views/ui.py

import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction  # Para guardar todo o nada si hay error
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout

# Importamos Modelos
from inventario.models import (
    Producto, Filamento, Pieza, ItemPedido, 
    Pedido, Proyecto, ItemPiezaPedido, ComposicionProducto, Insumo,
    TareaProyecto
)

# Importamos Formularios
from inventario.forms import (
    PedidoForm, ClienteForm, ItemPedidoFormSet, 
    LogoForm, ProyectoForm, ItemPiezaFormSet
)

logger = logging.getLogger(__name__)

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
    if request.user.groups.filter(name="Taller").exists() and not request.user.is_superuser:
        return redirect("kanban_taller")

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
                             from inventario.models import Cliente
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
            logger.error(f"Error creando pedido/proyecto: {e}")
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
    # DEBUG LOGS
    logger.info(f"🔍 DEBUG KANBAN VENTAS: User={request.user.username}, Superuser={request.user.is_superuser}")
    logger.info(f"Groups: {[g.name for g in request.user.groups.all()]}")
    
    if request.user.groups.filter(name="Taller").exists() and not request.user.is_superuser:
        logger.warning(f"⛔ ACCESO DENEGADO: Usuario {request.user.username} redirigido a Taller")
        return redirect("kanban_taller")

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

    return render(request, 'inventario/tablero_kanban.html', context)

@login_required
def kanban_proyectos(request):
    """Vista para el Laboratorio de Proyectos"""
    if request.user.groups.filter(name="Taller").exists() and not request.user.is_superuser:
        return redirect("kanban_taller")

    proyectos = Proyecto.objects.all()
    return render(request, 'inventario/kanban_proyectos.html', {'proyectos': proyectos})

@login_required
def tablero_kanban(request):
    """(Redirección por compatibilidad)"""
    return redirect('kanban_ventas')


@login_required
def detalle_proyecto(request, proyecto_id):
    """
    Vista de detalle para un proyecto específico.
    Incluye diagrama de Gantt.
    """
    proyecto = get_object_or_404(Proyecto, pk=proyecto_id)
    tareas = proyecto.tareas.all().order_by('fecha_inicio')
    
    # Serializar tareas para el Gantt (JSON)
    tareas_data = []
    for t in tareas:
        deps = [d.id for d in t.dependencias.all()]
        
        # Clase dinámica basada en ID de categoría
        # En el template generaremos el CSS correspondiente
        css_class = "bar-default"
        if t.categoria:
             css_class = f"bar-cat-{t.categoria.id}"

        tareas_data.append({
            "id": str(t.id),
            "name": t.nombre,
            "start": t.fecha_inicio.strftime("%Y-%m-%d"),
            "end": t.fecha_fin.strftime("%Y-%m-%d"),
            "progress": t.progreso,
            "dependencies": ",".join(map(str, deps)),
            "custom_class": css_class,
            "categoria_id": t.categoria.id if t.categoria else ""
        })

    # Obtener todas las categorías para el template
    from inventario.models import CategoriaTarea
    categorias = CategoriaTarea.objects.all()

    return render(request, "inventario/detalle_proyecto.html", {
        "proyecto": proyecto,
        "tareas_json": json.dumps(tareas_data),
        "categorias": categorias,
    })


# =========================================================
# 4. LISTAS Y DASHBOARDS
# =========================================================

@login_required
def lista_pedidos(request):
    if request.user.groups.filter(name="Taller").exists() and not request.user.is_superuser:
        return redirect("kanban_taller")
        
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

    # Validar permisos para gráfico
    is_taller = request.user.groups.filter(name="Taller").exists() and not request.user.is_superuser
    show_sales_plot = not is_taller

    # DEBUG LOGS
    logger.info(f"🔍 DEBUG DASHBOARD: User={request.user.username}, IsTaller={is_taller}, ShowPlot={show_sales_plot}")
    logger.info(f"Groups: {[g.name for g in request.user.groups.all()]}")

    context = {
        'filamentos': filamentos_ordenados,
        'productos': resumen_productos,
        'grafico_labels': json.dumps(labels_meses),
        'grafico_creados': json.dumps(data_creados),
        'grafico_entregados': json.dumps(data_entregados),
        'show_sales_plot': show_sales_plot,
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
        if pieza.material and pieza.material.descontar_material(peso_total):
            pieza.stock_fisico += cantidad
            pieza.save()
            messages.success(request, f"🖨️ Se imprimieron {cantidad} unidades de {pieza.nombre}.")
        else:
            messages.error(request, f"❌ No hay suficiente filamento {pieza.material.color if pieza.material else 'Sin Material'}.")

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
                
                # Forzar extracción inmediata
                if archivo_gcode:
                    try:
                        logger.info(f"Procesando archivo: {archivo_gcode.name}")
                        # Peso
                        peso = nueva_pieza.extraer_peso_gcode()
                        if peso:
                            nueva_pieza.peso_gramos = peso
                            logger.info(f"Peso detectado: {peso}")
                        
                        # Tiempo
                        tiempo = nueva_pieza.extraer_tiempo()
                        if tiempo:
                            nueva_pieza.tiempo_impresion = tiempo
                            logger.info(f"Tiempo detectado: {tiempo}")
                            
                        nueva_pieza.save()
                    except Exception as e:
                        logger.error(f"Error procesando GCode en vista: {e}")
                
                # Crear la relación automáticamente
                ComposicionProducto.objects.create(
                    producto=producto,
                    pieza=nueva_pieza,
                    cantidad=cantidad_requerida
                )
                
                messages.success(request, f"✨ Pieza '{nombre}' creada y vinculada correctamente.")
                
            except Exception as e:
                logger.error(f"Error creando pieza: {e}")
                messages.error(request, f"Error creando pieza: {e}")
        else:
            messages.error(request, "Faltan datos obligatorios (Nombre o Material).")

    return redirect("detalle_producto", producto_id=producto_id)

@login_required
def gestion_insumos(request):
    """Vista para gestionar stock de insumos (imanes, motores, etc)."""
    if request.user.groups.filter(name="Taller").exists() and not request.user.is_superuser:
        return redirect("dashboard")

    insumos = Insumo.objects.all().order_by('nombre')
    return render(request, "inventario/gestion_insumos.html", {
        "insumos": insumos
    })

@login_required
def gestion_filamentos(request):
    """Vista dedicada para gestión de rollos de filamento."""
    filamentos = Filamento.objects.all().order_by('tipo', 'color')
    return render(request, "inventario/gestion_filamentos.html", {
        "filamentos": filamentos
    })

def salir(request):
    logout(request)
    return redirect('/admin/login/')
