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
