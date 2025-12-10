import base64
from django.core.files.base import ContentFile
from django.db import models

# Create your models here.


# 1. El Filamento (Tu materia prima)
class Filamento(models.Model):
    TIPOS = [
        ("PLA_SILK", "PLA Silk"),
        ("PETG", "PETG"),
        ("PLA_MATE", "PLA Mate"),
        ("PLA", "pla"),
    ]
    tipo = models.CharField(max_length=50, choices=TIPOS)

    color = models.CharField(max_length=50)  # Ej: Gris, Marmoleado

    # IntegerField = Números enteros (0, 1, 2, 10...)
    cantidad_rollos = models.PositiveIntegerField(
        default=0, verbose_name="Rollos Cerrados (1kg)"
    )
    gramos_sueltos = models.FloatField(
        default=0, verbose_name="Gramos en carrete abierto"
    )  # Cuánto tienes en el carrete

    def __str__(self):
        return f"{self.tipo} - {self.color} ({self.stock_total}g)"

    @property
    def stock_total(self):
        """Suma todo para saber cuánto tenemos realmente en total."""
        return (self.cantidad_rollos * 1000) + self.gramos_sueltos

    # --- MÉTODO MÁGICO PARA DESCONTAR ---
    def descontar_material(self, cantidad_necesaria):
        """
        Resta material inteligentemente. Si falta en el suelto, abre una caja nueva.
        """
        if self.stock_total < cantidad_necesaria:
            return False  # No alcanza

        # 1. Convertimos todo a gramos, restamos y volvemos a empaquetar
        nuevo_total_gramos = self.stock_total - cantidad_necesaria

        # División entera (//): Cuántos rollos de 1000 caben
        self.cantidad_rollos = int(nuevo_total_gramos // 1000)

        # Módulo (%): Cuántos gramos sobran
        self.gramos_sueltos = nuevo_total_gramos % 1000

        self.save()
        return True


# 2. La Pieza Individual (Ej: Un engranaje del molino)
class Pieza(models.Model):
    nombre = models.CharField(max_length=100)  # Ej: "Engranaje Principal"
    peso_gramos = models.FloatField()
    # Aquí relacionamos la pieza con el filamento que usa
    material = models.ForeignKey(Filamento, on_delete=models.CASCADE)
    archivo_stl = models.FileField(upload_to="stls/", null=True, blank=True)

    stock_fisico = models.PositiveIntegerField(
        default=0, verbose_name="Stock impreso (Unidades)"
    )
    imagen = models.ImageField(
        upload_to="piezas/", null=True, blank=True, verbose_name="Foto de la pieza"
    )

# Campo para el archivo GCODE real
    archivo_gcode = models.FileField(upload_to='gcodes/', null=True, blank=True, verbose_name="Archivo GCode")
    

    def save(self, *args, **kwargs):
        # DETECTAR SI HAY UN GCODE NUEVO Y NO HAY IMAGEN
        # Si estamos subiendo un GCode y la imagen está vacía...
        if self.archivo_gcode and not self.imagen:
            imagen_extraida = self.extraer_thumbnail_gcode()
            if imagen_extraida:
                # Guardamos la imagen con el mismo nombre que la pieza + .png
                nombre_archivo = f"{self.nombre}_thumbnail.png"
                self.imagen.save(nombre_archivo, imagen_extraida, save=False)
        
        super().save(*args, **kwargs)

    def extraer_thumbnail_gcode(self):
        """
        Lee el archivo GCode sin cerrarlo para no romper el guardado de Django.
        """
        try:
            # 1. Abrimos el archivo en modo lectura binaria ('rb')
            self.archivo_gcode.open('rb')
            
            # 2. Leemos todas las líneas
            lines = self.archivo_gcode.readlines()
            
            # 3. ¡IMPORTANTE! Rebobinamos el archivo al inicio (byte 0)
            # Si no hacemos esto, Django guardará un archivo vacío.
            self.archivo_gcode.seek(0)
            
            # NOTA: NO HACEMOS .close() AQUÍ. Django lo cerrará después de guardar.
            
            capturando = False
            base64_string = ""
            
            for line in lines:
                # Como leemos en binario (rb), decodificamos a texto
                try:
                    line_str = line.decode('utf-8', errors='ignore').strip()
                except:
                    continue
                
                # INICIO DEL THUMBNAIL
                if "; thumbnail begin" in line_str or "; THUMBNAIL_BLOCK_START" in line_str:
                    capturando = True
                    continue
                
                # FIN DEL THUMBNAIL
                if "; thumbnail end" in line_str or "; THUMBNAIL_BLOCK_END" in line_str:
                    capturando = False
                    break 
                
                # CAPTURANDO DATOS
                if capturando:
                    data = line_str.replace(';', '').strip()
                    base64_string += data

            if base64_string:
                image_data = base64.b64decode(base64_string)
                return ContentFile(image_data)
            
            return None
                
        except Exception as e:
            print(f"Error interno extrayendo thumbnail: {e}")
            # En caso de error, aseguramos rebobinar por si acaso
            self.archivo_gcode.seek(0)
            return None

    def __str__(self):
        return f"{self.nombre} ({self.material.color})"


# 3. El Producto Final (Ej: Molino SAG 1:115)
class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    # Un producto tiene muchas piezas a través de una tabla intermedia

    # --- NUEVOS CAMPOS ---
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

    # --- LÓGICA DE ENSAMBLAJE ---
    def se_puede_armar(self):
        """Revisa si tienes las piezas FÍSICAS ya impresas para armar un molino."""
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
        """
        Retorna un diccionario con el estado del stock para este producto.
        """
        piezas_necesarias = self.composicionproducto_set.all()
        lista_faltantes = []
        es_viable = True

        for item in piezas_necesarias:
            peso_total = item.pieza.peso_gramos * item.cantidad
            stock_filamento = item.pieza.material.stock_total

            # Verificamos si hay stock suficiente
            if stock_filamento < peso_total:
                es_viable = False
                gramos_faltantes = peso_total - stock_filamento
                lista_faltantes.append(
                    f"Falta {gramos_faltantes}g de {item.pieza.material.color} para {item.pieza.nombre}"
                )

        return {"viable": es_viable, "mensajes": lista_faltantes}

    def cantidad_armable_hoy(self):
        """
        Calcula cuántos productos completos podrías armar YA MISMO
        basado en la pieza que menos tengas (El cuello de botella).
        """
        piezas_necesarias = self.composicionproducto_set.all()
        if not piezas_necesarias:
            return 0

        posibles = []
        for item in piezas_necesarias:
            # División entera: Si necesito 4 y tengo 9, alcanzan para 2 (sobra 1)
            cantidad_posible = item.pieza.stock_fisico // item.cantidad
            posibles.append(cantidad_posible)

        # El número máximo de molinos es dictado por la pieza que menos alcance
        return min(posibles)


# 4. Tabla Intermedia (Para decir: El Molino lleva 4 patas y 1 carcasa)
class ComposicionProducto(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    pieza = models.ForeignKey(Pieza, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)


# --- SECCIÓN DE VENTAS Y PEDIDOS ---


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
    # Opciones de Estado (Tuplas: 'VALOR_BD', 'Nombre Visible')
    ESTADOS_PAGO = [
        ("PENDIENTE", "🔴 Pendiente de Pago"),
        ("PARCIAL", "🟡 Pago Parcial (Seña)"),
        ("PAGADO", "🟢 Pagado Totalmente"),
    ]

    ESTADOS_ENTREGA = [
        ("PREPARACION", "📦 En Preparación"),
        ("TRANSITO", "🚚 En Tránsito / Enviado"),
        ("ENTREGADO", "✅ Entregado al Cliente"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_entrega_estimada = models.DateField(null=True, blank=True)

    estado_pago = models.CharField(
        max_length=20, choices=ESTADOS_PAGO, default="PENDIENTE"
    )
    monto_pagado = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Monto Abonado (S/)"
    )

    estado_entrega = models.CharField(
        max_length=20, choices=ESTADOS_ENTREGA, default="PREPARACION"
    )
    codigo_seguimiento = models.CharField(
        max_length=50, blank=True, help_text="Número de guía o tracking"
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

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def save(self, *args, **kwargs):
        # Si no ponemos precio, jalamos el precio actual del producto automáticamente
        if not self.precio_unitario:
            self.precio_unitario = self.producto.precio
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre}"
