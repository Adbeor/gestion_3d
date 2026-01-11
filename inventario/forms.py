from django import forms
from django.forms import inlineformset_factory
from .models import Pedido, Cliente, ItemPedido

# 1. Formulario del Pedido
class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ['cliente', 'fecha_entrega_estimada', 'es_urgente', 'requiere_factura']
        widgets = {
            'fecha_entrega_estimada': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'cliente': forms.Select(attrs={'class': 'form-control select-cliente'}),
        }

# 2. Formulario del Cliente
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

# 3. FormSet de Items (AQUÍ ESTABA EL FALTANTE)
ItemPedidoFormSet = inlineformset_factory(
    Pedido,
    ItemPedido,
    # 👇 ¡IMPORTANTE! Agregamos 'poner_nombre', 'nombre' y 'logo' a esta lista:
    fields=("producto", "cantidad", "precio_unitario", "cubierta", "poner_nombre", "nombre", "logo", "texto_dedicatoria"),
    extra=1,
    can_delete=True,
    widgets={
        "producto": forms.Select(attrs={"class": "form-control","onchange": "actualizarPrecio(this)"}),
        "cantidad": forms.NumberInput(attrs={"class": "form-control", "style": "width: 70px"}),
        "precio_unitario": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "style": "width: 90px"}),
        "cubierta": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        
        # --- NUEVOS WIDGETS ---
        "poner_nombre": forms.CheckboxInput(
            attrs={
                "class": "form-check-input check-nombre", 
                "onchange": "toggleNombre(this)" # Activa el JS
            }
        ),
        "nombre": forms.TextInput(
            attrs={
                "class": "form-control input-nombre", 
                "placeholder": "Nombre a grabar...",
                "style": "display:none;" # Oculto por defecto
            }
        ),
        "logo": forms.Select(attrs={"class": "form-control"}),
        # ---------------------

        "texto_dedicatoria": forms.TextInput(attrs={"class": "form-control", "placeholder": "Dedicatoria..."}),
    },
)
