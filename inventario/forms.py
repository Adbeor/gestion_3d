# inventario/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import Pedido, Cliente, ItemPedido

# 1. Formulario del Pedido (La Cabecera)
class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ['cliente', 'fecha_entrega_estimada', 'es_urgente', 'requiere_factura']
        widgets = {
            'fecha_entrega_estimada': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'cliente': forms.Select(attrs={'class': 'form-control select-cliente'}), # Clase para JS
        }

# 2. Formulario para Cliente Nuevo (El que aparece con el botón verde)
class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nombre', 'telefono', 'email', 'direccion']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre Completo'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'WhatsApp'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Correo (Opcional)'}),
            'direccion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Dirección'}),
        }

# 3. La "Magia" de los Productos (El Inline)
# Esto crea un set de formularios repetibles para los items
ItemPedidoFormSet = inlineformset_factory(
    Pedido, ItemPedido,
    fields=('producto', 'cantidad', 'precio_unitario', 'texto_dedicatoria'),
    extra=1,    # Cuántos renglones vacíos mostrar al inicio
    can_delete=True,
    widgets={
        'producto': forms.Select(attrs={'class': 'form-control'}),
        'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'style': 'width: 80px'}),
        'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        'texto_dedicatoria': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Dedicatoria...'}),
    }
)
