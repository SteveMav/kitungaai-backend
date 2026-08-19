from django import forms

from api.models import Product
from apps.wallets.models import Customer


class ProductForm(forms.ModelForm):
    vision_labels = forms.CharField(
        required=False,
        label="Labels reconnus par la caméra",
        help_text="Séparez plusieurs labels par une virgule, par exemple : arduino_mega, mega_2560.",
        widget=forms.TextInput(attrs={"placeholder": "arduino_mega_2560"}),
    )
    adjustment_reason = forms.CharField(
        required=False,
        label="Motif de l'ajustement",
        widget=forms.TextInput(attrs={"placeholder": "Inventaire, réception, correction…"}),
    )

    class Meta:
        model = Product
        fields = ("sku", "name", "price", "stock", "is_active")
        labels = {
            "sku": "Référence (SKU)",
            "name": "Nom du produit",
            "price": "Prix unitaire (FC)",
            "stock": "Quantité en stock",
            "is_active": "Produit disponible",
        }
        widgets = {
            "sku": forms.TextInput(attrs={"placeholder": "ARD-MEGA-2560"}),
            "name": forms.TextInput(attrs={"placeholder": "Arduino Mega 2560"}),
            "price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "stock": forms.NumberInput(attrs={"min": "0", "step": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["vision_labels"].initial = ", ".join(
                self.instance.vision_labels.filter(is_active=True, model_version="").values_list(
                    "label", flat=True
                )
            )

    def clean_sku(self):
        return self.cleaned_data["sku"].strip().upper()

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price < 0:
            raise forms.ValidationError("Le prix ne peut pas être négatif.")
        return price

    def clean_vision_labels(self):
        raw_labels = self.cleaned_data.get("vision_labels", "")
        labels = []
        for raw_label in raw_labels.split(","):
            label = raw_label.strip().lower()
            if label and label not in labels:
                labels.append(label)
        return labels


class BasketLineCorrectionForm(forms.Form):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=0, max_value=999, label="Quantité correcte")
    reason = forms.CharField(
        max_length=255,
        required=False,
        label="Motif",
        widget=forms.TextInput(attrs={"placeholder": "Correction après vérification"}),
    )


class UncataloguedLineRemovalForm(forms.Form):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(
        max_length=255,
        required=False,
        label="Motif",
        widget=forms.TextInput(attrs={"placeholder": "Objet non répertorié retiré après vérification"}),
    )


class BeginManualCheckoutForm(forms.Form):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)


class CompleteSaleForm(forms.Form):
    PAYMENT_METHODS = (
        ("CASH", "Espèces"),
        ("MOBILE_MONEY", "Mobile money"),
        ("OTHER", "Autre"),
    )

    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)
    payment_method = forms.ChoiceField(choices=PAYMENT_METHODS, label="Mode de paiement")


class ReleaseBasketForm(forms.Form):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(
        max_length=255,
        required=False,
        label="Motif",
        widget=forms.TextInput(attrs={"placeholder": "Retour au panier"}),
    )


class RfidEnrollmentApprovalForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        required=False,
        label="Client existant",
        empty_label="Créer un nouveau client",
    )
    customer_code = forms.CharField(
        max_length=32,
        required=False,
        label="Code client",
        widget=forms.TextInput(attrs={"placeholder": "CUST-0042"}),
    )
    display_name = forms.CharField(
        max_length=160,
        required=False,
        label="Nom affiché",
        widget=forms.TextInput(attrs={"placeholder": "Nom du client"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True).order_by(
            "display_name", "customer_code"
        )

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get("customer")
        customer_code = (cleaned_data.get("customer_code") or "").strip()
        display_name = (cleaned_data.get("display_name") or "").strip()
        if customer and (customer_code or display_name):
            raise forms.ValidationError(
                "Choisissez un client existant ou renseignez un nouveau client, pas les deux."
            )
        if not customer and not display_name:
            self.add_error("display_name", "Indiquez le nom du nouveau client.")
        cleaned_data["customer_code"] = customer_code
        cleaned_data["display_name"] = display_name
        return cleaned_data


class RfidEnrollmentRejectionForm(forms.Form):
    reason = forms.CharField(
        max_length=255,
        required=False,
        label="Motif du refus",
        widget=forms.TextInput(attrs={"placeholder": "Optionnel"}),
    )
