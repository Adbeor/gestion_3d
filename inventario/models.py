import re
import zipfile
import logging
import base64
from io import BytesIO
from django.db import models
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

# ==============================================================================
# SECCIÓN 1: INVENTARIO Y PRODUCCIÓN
# ==============================================================================


class Insumo(models.Model):
    nombre = models.CharField(max_length=100)
    stock = models.PositiveIntegerField(default=0, verbose_name="Stock Disponible")
    costo_unitario = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name="Costo Unitario (S/)"
    )
    unidad = models.CharField(max_length=20, default="unidad", verbose_name="Unidad de Medida")
    link_compra = models.URLField(blank=True, null=True, verbose_name="Link de Compra")

    def __str__(self):
        return f"{self.nombre} ({self.stock} {self.unidad})"


class Filamento(models.Model):
    TIPOS = [
        ("PLA_SILK", "PLA Silk"),
        ("PETG", "PETG"),
        ("PLA_MATE", "PLA Mate"),
        ("PLA", "PLA"),
    ]
    tipo = models.CharField(max_length=50, choices=TIPOS)
    color = models.CharField(max_length=50)  # Ej: Gris, Marmoleado

    # Stock
    cantidad_rollos = models.PositiveIntegerField(
        default=0, verbose_name="Rollos Cerrados (1kg)"
    )
    gramos_sueltos = models.FloatField(
        default=0, verbose_name="Gramos en carrete abierto"
    )

    # Costos
    costo_rollo = models.DecimalField(
        default=0.00, max_digits=10, decimal_places=2, verbose_name="Costo por Rollo (S/)"
    )

    @property
    def costo_por_gramo(self):
        """Asume rollos de 1kg (1000g)."""
        if self.costo_rollo > 0:
            return float(self.costo_rollo) / 1000.0
        return 0.0

    @property
    def stock_total(self):
        """Suma todo para saber cuánto tenemos realmente en total."""
        return (self.cantidad_rollos * 1000) + self.gramos_sueltos

    def descontar_material(self, cantidad_necesaria):
        """
        Resta material inteligentemente. Si falta en el suelto, abre una caja nueva.
        """
        if self.stock_total < cantidad_necesaria:
            return False  # No alcanza

        nuevo_total_gramos = self.stock_total - cantidad_necesaria
        self.cantidad_rollos = int(nuevo_total_gramos // 1000)
        self.gramos_sueltos = nuevo_total_gramos % 1000
        self.save()
        return True

    def __str__(self):
        return f"{self.tipo} - {self.color} ({self.stock_total}g)"


class Logo(models.Model):
    nombre = models.CharField(max_length=50)
    archivo_3mf = models.FileField(upload_to="logos/models/", blank=True, null=True)
    image = models.ImageField(upload_to="logos/images/", blank=True, null=True)

    def __str__(self):
        return f"{self.nombre}"


class Pieza(models.Model):
    nombre = models.CharField(max_length=100)
    peso_gramos = models.FloatField(blank=True, null=True, verbose_name="Peso (g)")
    material = models.ForeignKey(Filamento, on_delete=models.CASCADE)

    # Archivos
    archivo_stl = models.FileField(upload_to="stls/", null=True, blank=True)
    archivo_gcode = models.FileField(
        upload_to="gcodes/", null=True, blank=True, verbose_name="Archivo GCode"
    )
    imagen = models.ImageField(
        upload_to="piezas/", null=True, blank=True, verbose_name="Foto de la pieza"
    )

    # Stock
    stock_fisico = models.PositiveIntegerField(
        default=0, verbose_name="Stock impreso (Unidades)"
    )
    tiempo_impresion = models.CharField(
        max_length=50, null=True, blank=True, verbose_name="Tiempo de Impresión"
    )

    def save(self, *args, **kwargs):
        # 1. Lógica del Thumbnail (Extraer foto del GCode)
        if self.archivo_gcode and not self.imagen:
            try:
                imagen_extraida = self.extraer_thumbnail_gcode()
                if imagen_extraida:
                    nombre_archivo = f"{self.nombre}_thumbnail.png"
                    self.imagen.save(nombre_archivo, imagen_extraida, save=False)
            except Exception as e:
                print(f"Error thumbnail: {e}")

        # 2. Lógica del Peso (Extraer gramos del GCode si no está definido)
        if self.archivo_gcode and (not self.peso_gramos or self.peso_gramos == 0):
            peso_detectado = self.extraer_peso_gcode()
            if peso_detectado:
                self.peso_gramos = peso_detectado

        # 3. Lógica del Tiempo (Extraer del nombre o GCode)
        if self.archivo_gcode and not self.tiempo_impresion:
            self.tiempo_impresion = self.extraer_tiempo()

        super().save(*args, **kwargs)

    def _leer_contenido_gcode_raw(self, max_bytes=None):
        """
        Lee el contenido del archivo. Si es .3mf (zip), busca el archivo .gcode dentro.
        Retorna bytes.
        """
        try:
            self.archivo_gcode.open("rb")
            
            # Detectar 3MF / ZIP
            if self.archivo_gcode.name.lower().endswith(".3mf"):
                try:
                    with zipfile.ZipFile(self.archivo_gcode) as z:
                        # Buscar archivos .gcode dentro del zip
                        gcode_files = [f for f in z.namelist() if f.lower().endswith(".gcode")]
                        if not gcode_files:
                            return None
                        
                        # Usar el primero (Metadata/plate_1.gcode o similar)
                        with z.open(gcode_files[0]) as f:
                            if max_bytes:
                                return f.read(max_bytes)
                            return f.read()
                except zipfile.BadZipFile:
                    # Fallback si no es zip válido
                    pass

            # Archivo normal
            self.archivo_gcode.seek(0)
            if max_bytes:
                return self.archivo_gcode.read(max_bytes)
            return self.archivo_gcode.read()
            
        except Exception as e:
            logger.error(f"Error leyendo archivo: {e}")
            return None
        finally:
            # Asegurar que el archivo quede cerrado/reseteado si es necesario
            # Pero Django maneja apertura/cierre en models.FileField usualmente
            try: self.archivo_gcode.seek(0)
            except: pass

    def _leer_metadata_bambu(self):
        """
        Busca y lee Metadata/slice_info.config en 3MF para datos extra.
        Retorna diccionario con 'peso' y 'tiempo' si encuentra algo.
        """
        logger.debug(f"_leer_metadata_bambu: Procesando {self.archivo_gcode.name}")
        datos = {}
        if not self.archivo_gcode.name.lower().endswith(".3mf"):
            logger.debug("No es .3mf, saltando metadata bambu.")
            return datos
            
        try:
            self.archivo_gcode.open("rb")
            logger.debug("Abierto archivo 3mf para zip reading...")
            with zipfile.ZipFile(self.archivo_gcode) as z:
                # Buscar slice_info.config
                target = "Metadata/slice_info.config"
                file_list = z.namelist()
                logger.debug(f"Archivos en zip: {len(file_list)} encontrados.")
                
                candidates = [f for f in file_list if f.lower().endswith("slice_info.config")]
                
                if candidates:
                    logger.debug(f"Metadata encontrada: {candidates[0]}")
                    with z.open(candidates[0]) as f:
                        content = f.read().decode("utf-8", errors="ignore")
                        logger.debug(f"Contenido slice_info ({len(content)} chars)")
                        
                        # Buscar Peso
                        # 1. Formato Key=Value (Bambu antiguo/Orca)
                        m_peso = re.search(r"(?i)total_weight\s*=\s*([0-9.]+)", content)
                        if not m_peso:
                             m_peso = re.search(r"(?i)consumption_weight\s*=\s*([0-9.]+)", content)
                        # 2. Formato XML (Bambu nuevo?) <metadata key="weight" value="180.96"/>
                        if not m_peso:
                             m_peso = re.search(r'<metadata\s+key="weight"\s+value="([0-9.]+)"', content)
                        
                        if m_peso:
                            datos['peso'] = float(m_peso.group(1))
                            logger.debug(f"Peso metadata encontrado: {datos['peso']}")
                        else:
                            logger.debug("No se halló weight en metadata.")
                            
                        # Buscar Tiempo
                        m_time = re.search(r"(?i)estimated_time\s*=\s*([0-9]+)", content)
                        # XML format?
                        if not m_time:
                             m_time = re.search(r'<metadata\s+key="estimated_time"\s+value="([0-9]+)"', content)
                        # Bambu/Orca Prediction (Tiempo en segundos)
                        if not m_time:
                             m_time = re.search(r'<metadata\s+key="prediction"\s+value="([0-9]+)"', content)
                        
                        if m_time:
                            datos['tiempo_seg'] = int(m_time.group(1))
                            logger.debug(f"Tiempo (seg) metadata encontrado: {datos['tiempo_seg']}")
                        else:
                            logger.debug("No se halló estimated_time/prediction en metadata.")
                else:
                    logger.debug("No se encontró slice_info.config en el zip.")

        except Exception as e:
            logger.error(f"Error leyendo metadata Bambu: {e}")
            pass
        finally:
             try: self.archivo_gcode.seek(0)
             except: pass
             
        return datos

    def extraer_thumbnail_gcode(self):
        """Lee el archivo GCode y extrae la imagen previsualizada."""
        # Logica existente (omito prints aqui para no saturar si no es el foco)
        try:
            # 1. SI ES 3MF (ZIP), BUSCAR IMAGEN EN METADATA PRIMERO
            if self.archivo_gcode.name.lower().endswith(".3mf"):
                try:
                    self.archivo_gcode.open("rb")
                    with zipfile.ZipFile(self.archivo_gcode) as z:
                        file_list = z.namelist()
                        
                        # Buscar Imagenes en Metadata/plate_*.png
                        candidates = [f for f in file_list if f.startswith("Metadata/plate_") and f.endswith(".png")]
                        
                        # Si hay varias, tomar la primera
                        if candidates:
                            logger.debug(f"Imagen encontrada en 3MF: {candidates[0]}")
                            with z.open(candidates[0]) as f:
                                return ContentFile(f.read())
                                
                        # Fallback: Buscar Metadata/thumbnail.png (Estándar 3MF)
                        if "Metadata/thumbnail.png" in file_list:
                             with z.open("Metadata/thumbnail.png") as f:
                                return ContentFile(f.read())
                                
                except Exception as e:
                    logger.error(f"Error buscando imagen en ZIP 3MF: {e}")
                finally:
                    try: self.archivo_gcode.seek(0)
                    except: pass

            # 2. SI NO ENCONTRÓ EN ZIP O NO ES ZIP, BUSCAR EN GCODE PURO
            contenido_bytes = self._leer_contenido_gcode_raw(max_bytes=100000) 
            if not contenido_bytes: return None
            lines = contenido_bytes.split(b"\n")
            capturando = False
            base64_string = ""
            for line in lines:
                try: line_str = line.decode("utf-8", errors="ignore").strip()
                except: continue
                if "; thumbnail begin" in line_str or "; THUMBNAIL_BLOCK_START" in line_str:
                    capturando = True
                    continue
                if "; thumbnail end" in line_str or "; THUMBNAIL_BLOCK_END" in line_str:
                    capturando = False
                    break
                if capturando:
                    base64_string += line_str.replace(";", "").strip()
            if base64_string:
                return ContentFile(base64.b64decode(base64_string))
            return None
            if base64_string:
                return ContentFile(base64.b64decode(base64_string))
            return None
        except Exception as e:
            logger.error(f"Error extrayendo thumbnail: {e}")
            return None

    def extraer_peso_gcode(self):
        """
        Busca en el GCode cuánto filamento consume.
        Soporta GCode plano y 3MF (Bambu/Orca Metadata fallback).
        """
        logger.debug(f"Iniciando extraer_peso_gcode para {self.archivo_gcode.name}")
        
        # 1. Intentar Metadata Bambu
        meta = self._leer_metadata_bambu()
        if 'peso' in meta:
            logger.debug(f"Retornando peso desde Metadata: {meta['peso']}")
            return meta['peso']

        # 2. Intentar buscar en GCODE interno
        try:
            logger.debug("Buscando peso en contenido RAW (GCode plano)...")
            raw_data = self._leer_contenido_gcode_raw()
            if not raw_data: 
                logger.debug("No se pudo leer contenido raw.")
                return None
            
            contenido = raw_data.decode("utf-8", errors="ignore")
            logger.debug(f"Contenido decodificado ({len(contenido)} chars). Buscando regex...")

            # LISTA DE PATRONES
            patrones = [
                r"(?i); filament used \[g\] = ([0-9., ]+)",
                r"(?i); total filament used \[g\] = ([0-9., ]+)",
                r"(?i); weight = ([0-9., ]+)",
                r"(?i); total weight = ([0-9., ]+)",
                r"(?i); estimated weight = ([0-9., ]+)",
                r"(?i);Filament used: .* \(([0-9.]+)g\)",
                r"(?i); filament_weight_g = ([0-9., ]+)",
            ]

            for patron in patrones:
                match = re.search(patron, contenido)
                if match:
                    valores_str = match.group(1)
                    print(f"[DEBUG] Match encontrado con patron '{patron}': {valores_str}")
                    if "," in valores_str:
                        valores = [float(v.strip()) for v in valores_str.split(",") if v.strip()]
                        total = sum(valores)
                        print(f"[DEBUG] Suma de extrusores: {total}")
                        return total
                    return float(valores_str)
            
            print("[DEBUG] Ningun patron de peso hizo match.")
            return None

        except Exception as e:
            print(f"[DEBUG] Error extrayendo peso: {e}")
            return None

    def extraer_tiempo(self):
        """Intenta obtener el tiempo de impresión del nombre del archivo, metadata 3MF o contenido GCode."""
        
        # 1. Intentar Metadata Bambu (Preciso)
        meta = self._leer_metadata_bambu()
        if 'tiempo_seg' in meta:
            seg = meta['tiempo_seg']
            h = seg // 3600
            m = (seg % 3600) // 60
            return f"{h}h{m}m"

        tiempo_encontrado = None
        nombre_archivo = self.archivo_gcode.name
        
        # Limpiar extensión para no confundir "3mf" con "3m" (minutos)
        nombre_limpio = nombre_archivo.lower()
        for ext in [".gcode.3mf", ".3mf", ".gcode", ".gco"]:
            if nombre_limpio.endswith(ext):
                nombre_limpio = nombre_limpio[:-len(ext)]
                break

        # Estrategia 1: Buscar en el nombre LIMPIO
        match_complejo = re.search(r"(?i)(?:_|-)(\d{1,2}h)?(\d{1,2}m)?(?:_|-|\.|$)", nombre_limpio)
        if match_complejo:
            partes = []
            if match_complejo.group(1): partes.append(match_complejo.group(1))
            if match_complejo.group(2): partes.append(match_complejo.group(2))
            if partes:
                tiempo_encontrado = "".join(partes)

        if not tiempo_encontrado:
             # Busca "2h30m" o "45m" asegurando que tenga bordes (no parte de una palabra o extension)
             match_simple = re.search(r"(?i)(?:^|_)(\d+h\d+m|\d+h|\d+m)(?:_|$)", nombre_limpio)
             if match_simple:
                 tiempo_encontrado = match_simple.group(1)

        # Estrategia 2: Buscar en el Contenido (GCode o 3MF)
        if not tiempo_encontrado:
            try:
                raw_data = self._leer_contenido_gcode_raw(max_bytes=50000) # Leer inicio
                if raw_data:
                    contenido = raw_data.decode("utf-8", errors="ignore")
                    
                    # Patrones comunes
                    patrones_tiempo = [
                        r"(?i); estimated printing time = (.*)",
                        r"(?i); print_time = (.*)",
                        r"(?i);TIME:(.*)"
                    ]
                    
                    for p in patrones_tiempo:
                        m = re.search(p, contenido)
                        if m:
                            t_raw = m.group(1).strip()
                            # Cura (segundos) vs Prusa (2h 10m)
                            if t_raw.isdigit(): 
                                minutos = int(t_raw) // 60
                                horas = minutos // 60
                                minutos = minutos % 60
                                tiempo_encontrado = f"{horas}h{minutos}m"
                            else:
                                tiempo_encontrado = t_raw
                            break
            except Exception as e:
                print(f"Error extrayendo tiempo contenido: {e}")
                pass

        return tiempo_encontrado

    @property
    def costo_estimado(self):
        """Costo de material basado en el peso."""
        if self.peso_gramos and self.material:
            return round(self.peso_gramos * self.material.costo_por_gramo, 2)
        return 0.0

    def __str__(self):
        # Esto le dice a Django: "No digas 'Objeto 12', di 'Engranaje (Gris)'"
        return f"{self.nombre} ({self.material.color})"


class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    stock_armado = models.PositiveIntegerField(default=0, verbose_name="Molinos Listos")
    ventas = models.PositiveIntegerField(default=0, verbose_name="Total Vendidos")

    piezas = models.ManyToManyField(Pieza, through="ComposicionProducto")
    insumos = models.ManyToManyField(Insumo, through="ComposicionInsumo")
    imagen = models.ImageField(
        upload_to="productos/",
        null=True,
        blank=True,
        verbose_name="Foto del producto final",
    )

    def __str__(self):
        return f"{self.nombre} (Listos: {self.stock_armado})"

    def se_puede_armar(self):
        """Revisa si hay stock físico de piezas para armar."""
        faltantes = []
        viable = True
        for item in self.composicionproducto_set.all():
            if item.pieza.stock_fisico < item.cantidad:
                viable = False
                faltantes.append(
                    f"Faltan {item.cantidad - item.pieza.stock_fisico} un. de {item.pieza.nombre}"
                )
        return {"viable": viable, "errores": faltantes}

    def analizar_disponibilidad(self):
        """Revisa si hay FILAMENTO suficiente para imprimir todo desde cero."""
        piezas_necesarias = self.composicionproducto_set.all()
        lista_faltantes = []
        es_viable = True

        for item in piezas_necesarias:
            peso_total = (
                item.pieza.peso_gramos * item.cantidad if item.pieza.peso_gramos else 0
            )
            stock_filamento = item.pieza.material.stock_total

            if stock_filamento < peso_total:
                es_viable = False
                gramos_faltantes = peso_total - stock_filamento
                lista_faltantes.append(
                    f"Falta {gramos_faltantes}g de {item.pieza.material.color} para {item.pieza.nombre}"
                )

        return {"viable": es_viable, "mensajes": lista_faltantes}

    def analizar_disponibilidad_completa(self):
        """Revisa filamento + insumos NO opcionales."""
        # 1. Filamento (Lógica existente)
        resultado = self.analizar_disponibilidad()
        
        # 2. Insumos
        insumos_necesarios = self.composicioninsumo_set.filter(es_opcional=False)
        for item in insumos_necesarios:
            if item.insumo.stock < item.cantidad:
                resultado["viable"] = False
                resultado["mensajes"].append(
                    f"Falta {item.cantidad - item.insumo.stock} de {item.insumo.nombre}"
                )
        return resultado

    @property
    def costo_total(self):
        """Suma del costo de todas las piezas + insumos no opcionales."""
        total = 0
        
        # Costo Piezas
        for item in self.composicionproducto_set.all():
            total += item.pieza.costo_estimado * item.cantidad
            
        # Costo Insumos (Solo los obligatorios por defecto en el costo base)
        for item in self.composicioninsumo_set.filter(es_opcional=False):
            total += float(item.insumo.costo_unitario) * float(item.cantidad)
            
        return round(total, 2)

    @property
    def ganancia_estimada(self):
        return float(self.precio) - self.costo_total

    @property
    def margen(self):
        if self.precio > 0:
            return round((self.ganancia_estimada / float(self.precio)) * 100, 1)
        return 0.0

    def cantidad_armable_hoy(self):
        """Calcula cuántos productos completos podrías armar YA MISMO con las piezas impresas."""
        piezas_necesarias = self.composicionproducto_set.all()
        if not piezas_necesarias:
            return 0

        posibles = []
        for item in piezas_necesarias:
            if item.cantidad > 0:
                cantidad_posible = item.pieza.stock_fisico // item.cantidad
                posibles.append(cantidad_posible)
            else:
                posibles.append(0)

        return min(posibles) if posibles else 0


class ComposicionProducto(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    pieza = models.ForeignKey(Pieza, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)


# ==============================================================================
# SECCIÓN 2: VENTAS Y PEDIDOS
# ==============================================================================


class Cliente(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Cliente")
    telefono = models.CharField(
        max_length=20, blank=True, verbose_name="Teléfono / WhatsApp"
    )
    email = models.EmailField(blank=True)
    direccion = models.TextField(blank=True, verbose_name="Dirección de Envío")

    def __str__(self):
        return self.nombre


# PROYECTO
class Proyecto(models.Model):
    ESTADOS_PROYECTO = [
        ('DISENO', '🎨 Fase de Diseño'),
        ('PRUEBA', '🧪 Pruebas / Prototipo'),
        ('PRODUCCION', '🔨 En Producción'),
        ('TERMINADO', '✅ Terminado (Evaluar Producto)'),
    ]
    
    nombre = models.CharField(max_length=200)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, blank = True, null = True)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS_PROYECTO, default='DISENO')
    fecha_inicio = models.DateField(auto_now_add=True)
    
    # Archivos adjuntos (Planos, bocetos)
    archivo_adjunto = models.FileField(upload_to='proyectos/', blank=True, null=True)

    def __str__(self):
        return f"PROYECTO: {self.nombre}"


class Pedido(models.Model):
    ESTADOS_PAGO = [
        ("PENDIENTE", "🔴 Pendiente de Pago"),
        ("PARCIAL", "🟡 Pago Parcial (Seña)"),
        ("PAGADO", "🟢 Pagado Totalmente"),
    ]

    ESTADOS_ENTREGA = [
        ('VENTA', '💰 Venta/Cotización (No pasar a Taller aún)'),
        ('COLA', '⏳ En Cola de Taller (Listo para fabricar)'),
        ('PROCESO', '🔨 En Proceso (Taller trabajando)'),
        ('LISTO', '📦 Listo para Retiro (Taller terminó)'),
        ('ENTREGADO', '✅ Entregado al Cliente'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_entrega_estimada = models.DateField(null=True, blank=True)

    es_urgente = models.BooleanField(default=False, verbose_name="¿Es Urgente?")

    # Estados y Montos
    estado_pago = models.CharField(
        max_length=20, choices=ESTADOS_PAGO, default="PENDIENTE"
    )
    monto_pagado = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Monto Abonado (S/)"
    )
    estado_entrega = models.CharField(max_length=20, choices=ESTADOS_ENTREGA, default='VENTA')

    # Datos de Envío
    costo_envio = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Costo Envío (S/)"
    )
    metodo_envio = models.CharField(
        max_length=50, blank=True, verbose_name="Método de Envío",
        choices=[
            ('RECOJO', '🏠 Recojo en Taller'),
            ('MOTORIZADO', '🏍️ Motorizado (Lima)'),
            ('SHALOM', '🚛 Shalom'),
            ('OLVA', '📦 Olva Courier'),
            ('OTRO', '✨ Otro'),
        ],
        default='RECOJO'
    )
    codigo_seguimiento = models.CharField(
        max_length=50, blank=True, help_text="Número de guía o tracking"
    )

    # Descuentos
    descuento = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Descuento (S/)"
    )

    # --- CAMPOS NUEVOS (BOOLEANOS) ---
    requiere_factura = models.BooleanField(
        default=False, verbose_name="Solicitó Factura"
    )
    paga_al_recibir = models.BooleanField(
        default=False, verbose_name="Paga Envío al Recibir"
    )

    def __str__(self):
        return f"Pedido #{self.id} - {self.cliente.nombre}"

    @property
    def total_pedido(self):
        """Suma productos, piezas sueltas y envío, menos descuentos"""
        total = 0
        # 1. Sumar Productos
        for item in self.items.all():
            total += item.subtotal
        
        # 2. Sumar Piezas Sueltas
        for item_p in self.items_pieza.all():
            total += item_p.subtotal

        # 3. Sumar Envío
        total += self.costo_envio * (0 if self.paga_al_recibir else 1)

        # 4. Restar Descuento Global
        total -= self.descuento
            
        return max(total, 0)

    @property
    def saldo_pendiente(self):
        return self.total_pedido - self.monto_pagado


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, related_name="items", on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Precio al momento de la venta"
    )

    # Campos personalizados
    cubierta = models.BooleanField(default=True, verbose_name="¿Lleva cubierta?")

    # nombre
    nombre = models.TextField(blank=True, verbose_name="Dirección de Envío")
    poner_nombre = models.BooleanField(default=True, verbose_name="¿Lleva nombre?")

    logo = models.ForeignKey(Logo, on_delete=models.SET_NULL, blank=True, null=True)

    texto_dedicatoria = models.TextField(
        null=True,
        blank=True,
        help_text="Ej: 'Recuerdo de la Gerencia de Mantenimiento 2025'",
    )
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Descuento (S/)")

    @property
    def subtotal(self):
        total_bruto = self.cantidad * self.precio_unitario
        return total_bruto - self.descuento

    def save(self, *args, **kwargs):
        # Si no ponemos precio, jalamos el precio actual del producto automáticamente
        if not self.precio_unitario:
            self.precio_unitario = self.producto.precio
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre}"


class ItemPiezaPedido(models.Model):
    """Clase para piezas sueltas o repuestos dentro de un pedido"""
    pedido = models.ForeignKey(Pedido, related_name="items_pieza", on_delete=models.CASCADE)
    pieza = models.ForeignKey(Pieza, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Precio (S/)",
        help_text="Pon 0 si es garantía o regalo"
    )

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def __str__(self):
        return f"{self.cantidad}x Pieza: {self.pieza.nombre}"


class ComposicionInsumo(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    insumo = models.ForeignKey(Insumo, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    es_opcional = models.BooleanField(default=False, verbose_name="Es Opcional")

    def __str__(self):
        return f"{self.producto.nombre} - {self.insumo.nombre} (x{self.cantidad})"
