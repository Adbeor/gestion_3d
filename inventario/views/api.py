# inventario/views/api.py

import json
import logging
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

from inventario.models import (
    Producto, Filamento, Pieza, ItemPedido, 
    Pedido, Proyecto, Insumo, ComposicionInsumo
)
from inventario.forms import LogoForm

logger = logging.getLogger(__name__)

# =========================================================
# 3. APIs PARA MOVER TARJETAS (AJAX)
# =========================================================

@login_required
def actualizar_estado_pedido(request):
    """Mueve un Pedido entre columnas del Kanban"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            pedido_id = data.get("id")
            nuevo_estado = data.get("estado")

            pedido = Pedido.objects.get(pk=pedido_id)
            pedido.estado_entrega = nuevo_estado
            pedido.save()
            return JsonResponse({"status": "ok", "mensaje": f"Movido a {nuevo_estado}"})
        except Pedido.DoesNotExist:
            return JsonResponse({"status": "error", "mensaje": "Pedido no encontrado"}, status=404)
        except Exception as e:
            logger.error(f"Error actualizando pedido: {e}")
            return JsonResponse({"status": "error", "mensaje": str(e)}, status=500)

    return JsonResponse({"status": "error"}, status=400)

@csrf_exempt
def actualizar_estado_proyecto(request):
    """Mueve un Proyecto entre fases"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            proyecto_id = data.get('id')
            nuevo_estado = data.get('estado')
        
            proy = Proyecto.objects.get(id=proyecto_id)
            proy.estado = nuevo_estado
            proy.save()
            return JsonResponse({'status': 'success'})
        except Proyecto.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Proyecto no encontrado'})
        except Exception as e:
            logger.error(f"Error actualizando proyecto: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)})
            
    return JsonResponse({'status': 'error', 'message': 'Método no válido'})

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
                    if pieza.material and pieza.material.descontar_material(peso_total):
                        pieza.stock_fisico += int(cantidad)
                        mensaje = f"Impresa: +{int(cantidad)} (Stock: {pieza.stock_fisico})"
                    else:
                        status = "error"
                        mensaje = f"Sin filamento suficiente ({pieza.material.color if pieza.material else 'Sin Material'})"
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
            logger.error(f"Error API Stock Pieza: {e}")
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
            logger.error(f"Error creando filamento: {e}")
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
            logger.error(f"Error stock filamento: {e}")
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
            logger.error(f"Error actualizando costo filamento: {e}")
            return JsonResponse({"status": "error", "mensaje": str(e)}, status=400)

    return JsonResponse({"status": "error", "mensaje": "Método no permitido"}, status=405)


@login_required
def api_stock_insumo(request, insumo_id):
    """API para sumar/restar stock de insumos."""
    if request.method == "POST":
        try:
            insumo = get_object_or_404(Insumo, pk=insumo_id)
            data = json.loads(request.body)
            accion = data.get("accion")

            if accion == "sumar":
                insumo.stock += 1
            elif accion == "restar" and insumo.stock > 0:
                insumo.stock -= 1
            
            insumo.save()
            return JsonResponse({"status": "ok", "nuevo_stock": insumo.stock})
        except Exception as e:
            logger.error(f"Error stock insumo: {e}")
            return JsonResponse({"status": "error", "mensaje": str(e)})

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
            logger.error(f"Error creando insumo: {e}")
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
            logger.error(f"Error vinculando insumo: {e}")
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
