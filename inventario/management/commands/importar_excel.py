import pandas as pd
from django.core.management.base import BaseCommand
from datetime import datetime
from django.utils.timezone import make_aware # <--- IMPORTANTE: Para arreglar el warning
from inventario.models import Cliente, Pedido, Producto, ItemPedido

class Command(BaseCommand):
    help = 'Importar pedidos arreglando las Zonas Horarias (Timezones)'

    def handle(self, *args, **kwargs):
        archivo_excel = 'Ventas TEC.xlsx'
        nombre_hoja = 'Pedidos'
        
        self.stdout.write(f"Leyendo archivo Excel: {archivo_excel}...")

        try:
            df = pd.read_excel(archivo_excel, sheet_name=nombre_hoja, header=1, engine='openpyxl')
            df = df.fillna('')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error al leer Excel: {e}"))
            return

        cont_creados = 0
        MAPA_ESTADOS = {
            'Fabricación': 'TALLER', 'Terminado': 'COLA', 
            'Entregado': 'ENTREGADO', 'Pendiente': 'COLA', '': 'COLA'
        }

        for index, row in df.iterrows():
            try:
                # 1. CLIENTE
                nombre_cliente = str(row['Nombre']).strip()
                if not nombre_cliente: continue

                cliente, _ = Cliente.objects.get_or_create(
                    nombre=nombre_cliente, defaults={'telefono': '', 'direccion': ''}
                )

                # 2. PRODUCTO
                nombre_sucio = str(row['Descripción']).strip()
                if not nombre_sucio: nombre_producto = "Generico"
                nombre_limpio = self.normalizar_producto(nombre_sucio)

                try: precio = float(row['Precio de venta'])
                except: precio = 0

                producto, _ = Producto.objects.update_or_create(
                    nombre=nombre_limpio, defaults={'precio': precio}
                )

                # 3. CANTIDAD Y DESCUENTO
                try: cant = int(row['Cantidad'])
                except: cant = 1
                
                try: descuento = float(row['Dscuento']) if row['Dscuento'] != '' else 0
                except: descuento = 0

                # 4. REGLAS DE FACTURA
                try: monto_igv = float(row['IGV']) if row['IGV'] != '' else 0
                except: monto_igv = 0
                
                es_mayorista = (cant >= 10)
                requiere_factura = (monto_igv > 0) or es_mayorista

                # 5. FECHAS (CORREGIDO PARA TIMEZONES)
                fecha_entrega = None
                val_ent = row['Fecha de entrega']
                if val_ent and val_ent != '':
                    try: fecha_entrega = pd.to_datetime(val_ent).date()
                    except: pass
                
                # --- AQUÍ ESTÁ LA CORRECCIÓN DE LA ZONA HORARIA ---
                fecha_creacion_real = None
                val_crea = row['Fecha de pedido']
                if val_crea and val_crea != '':
                    try: 
                        # 1. Convertimos a Timestamp de Pandas
                        ts = pd.to_datetime(val_crea)
                        # 2. Lo pasamos a datetime de Python puro
                        dt_naive = ts.to_pydatetime()
                        # 3. Le ponemos la zona horaria del sistema (make_aware)
                        fecha_creacion_real = make_aware(dt_naive)
                    except: 
                        pass
                # --------------------------------------------------

                # 6. PAGOS
                try:
                    total = float(row['Total']) if row['Total'] != '' else 0
                    adelanto = float(row['Adelanto']) if row['Adelanto'] != '' else 0
                except:
                    total, adelanto = 0, 0
                
                estado_pago = 'PENDIENTE'
                if total > 0:
                    if adelanto >= total: estado_pago = 'PAGADO'
                    elif adelanto > 0: estado_pago = 'PARCIAL'

                estado_entrega = MAPA_ESTADOS.get(str(row['Estado']).strip(), 'COLA')

                # 7. CREAR PEDIDO
                pedido = Pedido.objects.create(
                    cliente=cliente,
                    fecha_entrega_estimada=fecha_entrega,
                    estado_pago=estado_pago,
                    monto_pagado=adelanto,
                    estado_entrega=estado_entrega,
                    es_urgente=False,
                    requiere_factura=requiere_factura
                )

                if fecha_creacion_real:
                    # Usamos update para forzar la fecha antigua
                    Pedido.objects.filter(id=pedido.id).update(fecha_creacion=fecha_creacion_real)

                # 8. ITEMS
                val_cubierta = str(row['Cubierta']).lower()
                cubierta = val_cubierta in ['si', 's', 'yes', 'true', 'ok']
                
                texto = str(row['Mensaje/ Nombre']).strip()
                poner_nombre = len(texto) > 0 and len(texto) < 30
                nombre_grab = texto if poner_nombre else ""
                dedic = texto if not poner_nombre else ""
                
                ItemPedido.objects.create(
                    pedido=pedido, producto=producto, 
                    cantidad=cant, precio_unitario=precio, 
                    descuento=descuento,
                    cubierta=cubierta,
                    poner_nombre=poner_nombre, nombre=nombre_grab, texto_dedicatoria=dedic
                )
                cont_creados += 1

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Error fila {index}: {e}"))

        self.stdout.write(self.style.SUCCESS(f'✅ ¡Importación limpia! {cont_creados} pedidos sin errores de fecha.'))

    def normalizar_producto(self, nombre_sucio):
        nombre = nombre_sucio.lower().strip() 
        if 'motor' in nombre and 'tracc' in nombre: return "Motor de Tracción"
        if 'sag' in nombre:
            if 'cubierta' in nombre: return "Cubierta Molino SAG"
            if '65' in nombre or 'grande' in nombre: return "Molino SAG (Escala 1:65)"
            return "Molino SAG (Escala 1:115)"
        if 'bola' in nombre:
            if 'seccion' in nombre or 'sección' in nombre: return "Sección de Molino de Bolas"
            if 'mecanico' in nombre or 'mecánico' in nombre: return "Molino de Bolas (Mecánico)"
            if '65' in nombre or 'grande' in nombre: return "Molino de Bolas (Escala 1:65)"
            if '100' in nombre and '1:100' in nombre: return "Molino de Bolas (Escala 1:100)"
            return "Molino de Bolas (Escala 1:115)"
        if 'chancadora' in nombre:
            if '50' in nombre: return "Chancadora Primaria (Escala 1:50)"
            return "Chancadora Primaria"
        if 'cubierta' in nombre:
            if 'dos' in nombre or '2' in nombre: return "Set de Cubiertas (2 unid.)"
            return "Cubierta de Repuesto"
        if 'celda' in nombre: return "Celda de Flotación"
        if 'obsequio' in nombre: return "Obsequio / Promoción"
        return nombre_sucio.strip().capitalize()
