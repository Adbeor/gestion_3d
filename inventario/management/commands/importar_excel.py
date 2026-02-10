import pandas as pd
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from inventario.models import (
    Cliente, Pedido, Producto, ItemPedido, 
    Proyecto, Pieza, ItemPiezaPedido, Filamento,
    Insumo, ItemInsumoPedido
)

class Command(BaseCommand):
    help = 'Importar Excel preguntando al usuario (Modo Interactivo)'

    def handle(self, *args, **kwargs):
        archivo_excel = 'Control_Empresarial_Automatizado_V3.xlsx'
        nombre_hoja = 'Pedidos'
        
        self.stdout.write(f"📂 Cargando Excel: {archivo_excel}...")

        try:
            # Change header to 0 because the new Excel has headers on the first row
            df = pd.read_excel(archivo_excel, sheet_name=nombre_hoja, header=0, engine='openpyxl')
            df = df.fillna('')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error al leer Excel: {e}"))
            return

        # --- MEMORIA DE DECISIONES ---
        # Guardaremos tus respuestas aquí para no preguntarte lo mismo 2 veces
        memoria = {}

        # Material por defecto para piezas nuevas
        # CORREGIDO: Usamos solo los campos que existen en tu modelo Filamento
        material_default, _ = Filamento.objects.get_or_create(
            color="Generico Importacion", 
            defaults={
                'tipo': 'PLA', 
                'cantidad_rollos': 10,  # Iniciamos con 10 rollos para tener stock
                'gramos_sueltos': 0
            }
        )

        contadores = {'proyectos': 0, 'productos': 0, 'piezas': 0, 'insumos': 0, 'saltados': 0}

        for index, row in df.iterrows():
            try:
                # 1. DATOS BÁSICOS
                nombre_cliente = str(row['Cliente']).strip()
                # 'Producto' column is the Description/Name now
                desc_bruta = str(row['Producto']).strip()
                
                if not nombre_cliente or not desc_bruta: 
                    continue

                clave_memoria = desc_bruta.lower() # Usamos minúsculas para comparar

                # --- INTERACCIÓN CON EL USUARIO ---
                tipo_elegido = None

                # A) ¿Ya tomamos una decisión sobre esto antes?
                if clave_memoria in memoria:
                    tipo_elegido = memoria[clave_memoria]
                    self.stdout.write(f"   🤖 Recordando: '{desc_bruta}' es {tipo_elegido}")
                
                # B) Si es nuevo, PREGUNTAMOS
                else:
                    self.stdout.write("\n" + "="*60)
                    self.stdout.write(f"📝 Fila {index+2} | Cliente: {nombre_cliente}")
                    self.stdout.write(f"🔍 Descripción: {self.style.WARNING(desc_bruta)}")
                    self.stdout.write("="*60)
                    
                    while True:
                        opcion = input("Es: [1] Producto  [2] Pieza/Repuesto  [3] Proyecto  [4] Insumo  [s] Saltar: ").lower().strip()
                        
                        if opcion == '1':
                            tipo_elegido = 'PRODUCTO'
                            break
                        elif opcion == '2':
                            tipo_elegido = 'PIEZA'
                            break
                        elif opcion == '3':
                            tipo_elegido = 'PROYECTO'
                            break
                        elif opcion == '4':
                            tipo_elegido = 'INSUMO'
                            break
                        elif opcion == 's':
                            tipo_elegido = 'SALTAR'
                            break
                    
                    # Guardamos en memoria para la próxima
                    memoria[clave_memoria] = tipo_elegido

                if tipo_elegido == 'SALTAR':
                    contadores['saltados'] += 1
                    continue

                # --- PROCESAR SEGÚN LA ELECCIÓN ---
                
                # Crear Cliente Común
                cliente, _ = Cliente.objects.get_or_create(
                    nombre=nombre_cliente, defaults={'telefono': '', 'direccion': ''}
                )
                
                # Fecha
                val_crea = row['Fecha Pedido']
                fecha_creacion = None
                if val_crea and val_crea != '':
                    try:
                        ts = pd.to_datetime(val_crea)
                        fecha_creacion = make_aware(ts.to_pydatetime())
                    except: pass
                
                estado_excel = str(row['Estado']).strip()

                # === OPCIÓN 1: PRODUCTO ===
                if tipo_elegido == 'PRODUCTO':
                    # Precio
                    try: precio = float(row['Precio Unitario'])
                    except: precio = 0
                    
                    # Normalizamos nombre
                    nombre_limpio = desc_bruta.strip().capitalize()
                    
                    producto, _ = Producto.objects.update_or_create(
                        nombre=nombre_limpio, defaults={'precio': precio}
                    )

                    pedido = self.crear_pedido_base(row, cliente, fecha_creacion, estado_excel)

                    # Items
                    try: cant = int(row['Cantidad'])
                    except: cant = 1
                    try: descuento = float(row['Descuento']) if row['Descuento'] != '' else 0
                    except: descuento = 0
                    
                    # 'Cubierta' column doesn't exist in new Excel, default to False or remove logic
                    # val_cubierta = str(row['Cubierta']).lower()
                    # cubierta = val_cubierta in ['si', 's', 'yes', 'true', 'ok']
                    cubierta = False 
                    
                    ItemPedido.objects.create(
                        pedido=pedido, producto=producto, cantidad=cant, 
                        precio_unitario=precio, descuento=descuento, cubierta=cubierta,
                        poner_nombre=False, nombre=""
                    )
                    contadores['productos'] += 1

                # === OPCIÓN 2: PIEZA ===
                elif tipo_elegido == 'PIEZA':
                    try: precio = float(row['Precio Unitario'])
                    except: precio = 0
                    
                    # Al crear pieza, usamos los campos que sí existen
                    pieza_obj, _ = Pieza.objects.get_or_create(
                        nombre=desc_bruta,
                        defaults={
                            'material': material_default, 
                            'peso_gramos': 0, 
                            # 'tiempo_minutos' no lo ponemos porque no es obligatorio en tu modelo, o si lo es, ponlo en 0
                        }
                    )
                    
                    pedido = self.crear_pedido_base(row, cliente, fecha_creacion, estado_excel)
                    
                    try: cant = int(row['Cantidad'])
                    except: cant = 1

                    ItemPiezaPedido.objects.create(
                        pedido=pedido, pieza=pieza_obj, cantidad=cant, precio_unitario=precio
                    )
                    contadores['piezas'] += 1

                # === OPCIÓN 3: PROYECTO ===
                elif tipo_elegido == 'PROYECTO':
                    estado_proy = 'DISENO'
                    if estado_excel in ['Entregado', 'Terminado']: estado_proy = 'TERMINADO'
                    elif estado_excel in ['Fabricación', 'En proceso']: estado_proy = 'PRODUCCION'
                    
                    Proyecto.objects.create(
                        nombre=desc_bruta[:200],
                        cliente=cliente,
                        descripcion=f"Importado. Estado orig: {estado_excel}",
                        estado=estado_proy
                    )
                    contadores['proyectos'] += 1

                # === OPCIÓN 4: INSUMO ===
                elif tipo_elegido == 'INSUMO':
                    try: precio = float(row['Precio Unitario'])
                    except: precio = 0
                    
                    # 1. Crear/Buscar Insumo en Catálogo
                    # Asumimos que el precio del Excel es Precio Venta, no Costo. 
                    # El costo lo dejamos en 0 o lo que sea por defecto.
                    insumo_obj, _ = Insumo.objects.get_or_create(
                        nombre=desc_bruta,
                        defaults={'costo_unitario': 0, 'stock': 0} 
                    )

                    # 2. Crear Pedido
                    pedido = self.crear_pedido_base(row, cliente, fecha_creacion, estado_excel)

                    try: cant = int(row['Cantidad'])
                    except: cant = 1

                    # 3. Vincular Insumo al Pedido
                    ItemInsumoPedido.objects.create(
                        pedido=pedido, insumo=insumo_obj, cantidad=cant, precio_unitario=precio
                    )
                    contadores['insumos'] += 1

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Error fila {index}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\n✅ ¡Listo! Resumen:"))
        self.stdout.write(f"   📦 Productos: {contadores['productos']}")
        self.stdout.write(f"   🔧 Piezas:    {contadores['piezas']}")
        self.stdout.write(f"   🧪 Proyectos: {contadores['proyectos']}")
        self.stdout.write(f"   🔩 Insumos:   {contadores['insumos']}")

    def crear_pedido_base(self, row, cliente, fecha_creacion, estado_excel):
        MAPA_ESTADOS = {'Fabricación': 'PROCESO', 'Terminado': 'LISTO', 'Entregado': 'ENTREGADO', 'Pendiente': 'COLA', '': 'COLA'}
        
        try: cant = int(row['Cantidad'])
        except: cant = 1
        try: monto_igv = float(row['IGV']) if row['IGV'] != '' else 0
        except: monto_igv = 0
        requiere_factura = (monto_igv > 0) or (cant >= 10)

        try:
            total = float(row['Total']) if row['Total'] != '' else 0
            adelanto = float(row['Adelanto']) if row['Adelanto'] != '' else 0
        except: total, adelanto = 0, 0
        
        estado_pago = 'PENDIENTE'
        if total > 0:
            if adelanto >= total: estado_pago = 'PAGADO'
            elif adelanto > 0: estado_pago = 'PARCIAL'

        fecha_entrega = None
        if row['Fecha Entrega']:
            try: fecha_entrega = pd.to_datetime(row['Fecha Entrega']).date()
            except: pass

        pedido = Pedido.objects.create(
            cliente=cliente, fecha_entrega_estimada=fecha_entrega,
            estado_pago=estado_pago, monto_pagado=adelanto,
            estado_entrega=MAPA_ESTADOS.get(estado_excel, 'COLA'),
            requiere_factura=requiere_factura
        )
        if fecha_creacion: Pedido.objects.filter(id=pedido.id).update(fecha_creacion=fecha_creacion)
        return pedido
