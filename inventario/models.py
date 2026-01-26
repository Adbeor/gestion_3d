import base64
import re
from django.core.files.base import ContentFile
from django.db import models

# ==============================================================================
# SECCIÓN 1: INVENTARIO Y PRODUCCIÓN
# ==============================================================================


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

        super().save(*args, **kwargs)

    def extraer_thumbnail_gcode(self):
        """Lee el archivo GCode y extrae la imagen previsualizada."""
        try:
            self.archivo_gcode.open("rb")
            lines = self.archivo_gcode.readlines()
            self.archivo_gcode.seek(0)  # Rebobinar

            capturando = False
            base64_string = ""

            for line in lines:
                try:
                    line_str = line.decode("utf-8", errors="ignore").strip()
                except:
                    continue

                if (
                    "; thumbnail begin" in line_str
                    or "; THUMBNAIL_BLOCK_START" in line_str
                ):
                    capturando = True
                    continue

                if "; thumbnail end" in line_str or "; THUMBNAIL_BLOCK_END" in line_str:
                    capturando = False
                    break

                if capturando:
                    data = line_str.replace(";", "").strip()
                    base64_string += data

            if base64_string:
                image_data = base64.b64decode(base64_string)
                return ContentFile(image_data)
            return None
        except Exception as e:
            print(f"Error extrayendo thumbnail: {e}")
            self.archivo_gcode.seek(0)
            return None

    def extraer_peso_gcode(self):
        """
        Busca en el GCode cuánto filamento consume.
        Versión mejorada para Orca, Creality, Prusa y Cura.
        """
        try:
            self.archivo_gcode.open("rb")
            # Leemos solo los primeros 50kb y los últimos 50kb para ser rápidos
            # (El peso suele estar al final o al principio)
            contenido = self.archivo_gcode.read().decode("utf-8", errors="ignore")
            self.archivo_gcode.seek(0)  # Rebobinar siempre

            # LISTA DE PATRONES MEJORADA
            # \s* significa "cualquier cantidad de espacios"
            # (?i) significa "ignora mayúsculas/minúsculas"
            patrones = [
                # Orca / Prusa / SuperSlicer (común al final)
                r"(?i); filament used \[g\] = ([0-9.]+)",
                r"(?i); total filament used \[g\] = ([0-9.]+)",
                # Creality Print / Otros
                r"(?i); weight = ([0-9.]+)",
                r"(?i); total weight = ([0-9.]+)",
                r"(?i); estimated weight = ([0-9.]+)",
                # Cura
                r"(?i);Filament used: .* \(([0-9.]+)g\)",
                # Formato simple a veces encontrado
                r"(?i); filament_weight_g = ([0-9.]+)",
            ]

            for patron in patrones:
                match = re.search(patron, contenido)
                if match:
                    return float(match.group(1))

            return None

        except Exception as e:
            print(f"Error extrayendo peso: {e}")
            self.archivo_gcode.seek(0)
            return None

    def __str__(self):
        # Esto le dice a Django: "No digas 'Objeto 12', di 'Engranaje (Gris)'"
        return f"{self.nombre} ({self.material.color})"


class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    stock_armado = models.PositiveIntegerField(default=0, verbose_name="Molinos Listos")
    ventas = models.PositiveIntegerField(default=0, verbose_name="Total Vendidos")

    piezas = models.ManyToManyField(Pieza, through="ComposicionProducto")
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


class Pedido(models.Model):
    ESTADOS_PAGO = [
        ("PENDIENTE", "🔴 Pendiente de Pago"),
        ("PARCIAL", "🟡 Pago Parcial (Seña)"),
        ("PAGADO", "🟢 Pagado Totalmente"),
    ]

    ESTADOS_ENTREGA = [
        ("COLA", "⏳ En Cola (Pendiente)"),
        ("TALLER", "🔨 En Taller (Fabricación)"),
        ("TRANSITO", "🚚 En Tránsito"),
        ("ENTREGADO", "✅ Entregado y Conforme"),
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
    estado_entrega = models.CharField(
        max_length=20, choices=ESTADOS_ENTREGA, default="COLA"
    )

    # Datos de Envío
    codigo_seguimiento = models.CharField(
        max_length=50, blank=True, help_text="Número de guía o tracking"
    )

    # --- CAMPOS NUEVOS (BOOLEANOS) ---
    requiere_factura = models.BooleanField(
        default=False, verbose_name="Solicitó Factura"
    )

    def __str__(self):
        return f"Pedido #{self.id} - {self.cliente.nombre}"

    @property
    def total_pedido(self):
        """Suma el precio de todos los items dentro de este pedido"""
        total = 0
        for item in self.items.all():
            total += item.subtotal
        return total

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
