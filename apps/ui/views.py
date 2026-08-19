import uuid
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from api.models import Product
from apps.baskets.models import BasketLine, BasketSession, DetectionEvent, UncataloguedBasketLine
from apps.baskets.selectors import serialize_session, session_with_lines
from apps.catalog.models import VisionLabel
from apps.checkout.models import Sale, StockMovement
from apps.checkout.services import (
    DomainError,
    complete_sale,
    correct_line,
    release_basket,
    remove_uncatalogued_line,
)
from apps.devices.models import BasketDevice
from apps.wallets.models import RfidEnrollmentRequest
from apps.wallets.services import (
    RfidEnrollmentError,
    approve_rfid_enrollment as approve_rfid_enrollment_service,
    reject_rfid_enrollment as reject_rfid_enrollment_service,
)

from .context_processors import can_manage_rfid_enrollments
from .forms import (
    BasketLineCorrectionForm,
    CompleteSaleForm,
    ProductForm,
    ReleaseBasketForm,
    RfidEnrollmentApprovalForm,
    RfidEnrollmentRejectionForm,
    UncataloguedLineRemovalForm,
)


UI_ROLES = {"Administrateur", "Caissier", "Superviseur"}
DOMAIN_ERROR_MESSAGES = {
    "basket_locked": "Ce panier a changé d'état. Rechargez-le avant de continuer.",
    "version_conflict": "Le panier a été mis à jour ailleurs. Vérifiez les quantités actuelles.",
    "line_not_found": "Cette ligne n'existe plus dans le panier.",
    "uncatalogued_line_not_found": "Cet objet non répertorié n'existe plus dans le panier.",
    "empty_basket": "Le panier est vide et ne peut pas être confirmé.",
    "uncatalogued_objects_pending": "Retirez ou répertoriez les objets inconnus avant de confirmer la vente.",
    "insufficient_stock": "Le stock disponible ne suffit pas pour confirmer cette vente.",
    "session_not_found": "Cette session de panier n'existe plus.",
}


def ui_access_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not (
            request.user.is_superuser
            or request.user.groups.filter(name__in=UI_ROLES).exists()
        ):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return login_required(wrapped)


def _can_manage_stock(user):
    return user.is_superuser or user.has_perm("api.change_product")


def _can_correct_basket(user):
    return user.is_superuser or user.has_perm("baskets.correct_basket")


def _can_complete_sale(user):
    return user.is_superuser or user.has_perm("checkout.complete_sale")


def _can_release_basket(user):
    return user.is_superuser or user.has_perm("baskets.release_basket")


def _rfid_enrollment_access_required(request):
    if not can_manage_rfid_enrollments(request.user):
        raise PermissionDenied


RFID_ENROLLMENT_ERROR_MESSAGES = {
    "enrollment_not_found": "Cette demande RFID n'existe plus.",
    "enrollment_not_pending": "Cette demande RFID a déjà été traitée.",
    "rfid_uid_already_assigned": "Cette carte est déjà associée à un autre client.",
    "customer_not_available": "Le client sélectionné n'est plus disponible.",
    "customer_name_required": "Indiquez le nom du nouveau client.",
    "customer_code_taken": "Ce code client existe déjà.",
}


def _session_totals(session):
    lines = list(session.lines.all())
    uncatalogued_lines = list(session.uncatalogued_lines.all())
    return {
        "items": sum(line.quantity for line in lines) + sum(line.quantity for line in uncatalogued_lines),
        "total": sum((line.subtotal for line in lines), Decimal("0")),
        "uncatalogued_items": sum(line.quantity for line in uncatalogued_lines),
    }


def _is_online(last_seen_at):
    return bool(last_seen_at and last_seen_at >= timezone.now() - timezone.timedelta(minutes=2))


def _active_sessions():
    return (
        BasketSession.objects.filter(
            status__in=(BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING)
        )
        .select_related("device", "selected_terminal")
        .prefetch_related(
            Prefetch("lines", queryset=BasketLine.objects.select_related("product").order_by("created_at", "id")),
            Prefetch("uncatalogued_lines", queryset=UncataloguedBasketLine.objects.order_by("created_at", "id")),
        )
        .order_by("device__matrix_id")
    )


@ui_access_required
def dashboard(request):
    today = timezone.localdate()
    open_sessions = _active_sessions()
    pending_sessions = [
        session for session in open_sessions if session.status == BasketSession.Status.CHECKOUT_PENDING
    ]
    low_stock = list(Product.objects.filter(is_active=True, stock__lte=5).order_by("stock", "name")[:6])
    recent_sales = Sale.objects.select_related("cashier").filter(created_at__date=today)[:5]
    revenue_today = (
        Sale.objects.filter(created_at__date=today, payment_status=Sale.PaymentStatus.PAID).aggregate(
            total=Sum("total")
        )["total"]
        or Decimal("0")
    )
    return render(
        request,
        "ui/dashboard.html",
        {
            "section": "dashboard",
            "page_title": "Vue d'ensemble",
            "open_count": sum(1 for session in open_sessions if session.status == BasketSession.Status.OPEN),
            "pending_sessions": pending_sessions,
            "low_stock": low_stock,
            "unknown_labels_today": DetectionEvent.objects.filter(
                received_at__date=today, result=DetectionEvent.Result.UNCATALOGUED_OBJECT
            ).count(),
            "recent_sales": recent_sales,
            "revenue_today": revenue_today,
            "device_count": BasketDevice.objects.filter(enabled=True).count(),
        },
    )


@ui_access_required
def baskets(request, session_id=None):
    sessions = list(_active_sessions())
    session_by_device = {session.device_id: session for session in sessions}
    device_rows = []
    for device in BasketDevice.objects.filter(enabled=True).order_by("matrix_id"):
        session = session_by_device.get(device.id)
        totals = _session_totals(session) if session else {"items": 0, "total": Decimal("0")}
        device_rows.append(
            {
                "device": device,
                "session": session,
                "totals": totals,
                "is_online": _is_online(device.last_seen_at),
            }
        )

    selected = None
    if session_id:
        selected = next((session for session in sessions if session.id == session_id), None)
        if selected is None:
            messages.warning(request, "Ce panier n'est plus actif.")
    if selected is None and sessions:
        selected = sessions[0]

    return render(
        request,
        "ui/baskets.html",
        {
            "section": "baskets",
            "page_title": "Paniers",
            "device_rows": device_rows,
            "selected": selected,
            "selected_totals": _session_totals(selected) if selected else None,
        },
    )


@ui_access_required
def basket_data(request, session_id):
    session = session_with_lines(session_id)
    if session is None:
        return JsonResponse({"error": "session_not_found"}, status=404)
    payload = serialize_session(session)
    payload["status_label"] = session.get_status_display()
    payload["device_online"] = _is_online(session.device.last_seen_at)
    payload["last_seen_at"] = session.device.last_seen_at
    return JsonResponse(payload)


@ui_access_required
def checkout(request, session_id=None):
    pending = list(
        _active_sessions().filter(status=BasketSession.Status.CHECKOUT_PENDING).order_by("checkout_started_at")
    )
    selected = None
    if session_id:
        selected = next((session for session in pending if session.id == session_id), None)
        if selected is None:
            messages.warning(request, "Ce panier n'attend plus à la caisse.")
    if selected is None and pending:
        selected = pending[0]

    complete_form = None
    release_form = None
    if selected:
        complete_form = CompleteSaleForm(
            initial={
                "expected_version": selected.version,
                "idempotency_key": uuid.uuid4(),
                "payment_method": "CASH",
                "payment_status": Sale.PaymentStatus.PAID,
            }
        )
        release_form = ReleaseBasketForm(initial={"expected_version": selected.version})

    return render(
        request,
        "ui/checkout.html",
        {
            "section": "checkout",
            "page_title": "Caisse",
            "pending": pending,
            "selected": selected,
            "selected_totals": _session_totals(selected) if selected else None,
            "complete_form": complete_form,
            "release_form": release_form,
            "can_correct": _can_correct_basket(request.user),
            "can_complete": _can_complete_sale(request.user),
            "can_release": _can_release_basket(request.user),
        },
    )


@ui_access_required
def correct_checkout_line(request, session_id, line_id):
    if request.method != "POST" or not _can_correct_basket(request.user):
        raise PermissionDenied
    form = BasketLineCorrectionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Vérifiez la quantité saisie.")
        return redirect("ui:checkout-detail", session_id=session_id)
    payload = form.cleaned_data
    payload["reason"] = payload.get("reason") or "Correction après vérification en caisse"
    try:
        correct_line(session_id, line_id, request.user, payload)
        messages.success(request, "La quantité a été corrigée.")
    except DomainError as error:
        messages.error(request, DOMAIN_ERROR_MESSAGES.get(error.code, "La correction n'a pas pu être appliquée."))
    return redirect("ui:checkout-detail", session_id=session_id)


@ui_access_required
def remove_uncatalogued_checkout_line(request, session_id, line_id):
    if request.method != "POST" or not _can_correct_basket(request.user):
        raise PermissionDenied
    form = UncataloguedLineRemovalForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Vérifiez les informations de retrait.")
        return redirect("ui:checkout-detail", session_id=session_id)
    payload = form.cleaned_data
    payload["reason"] = payload.get("reason") or "Objet non répertorié retiré après vérification"
    try:
        remove_uncatalogued_line(session_id, line_id, request.user, payload)
        messages.success(request, "L'objet non répertorié a été retiré du panier.")
    except DomainError as error:
        messages.error(request, DOMAIN_ERROR_MESSAGES.get(error.code, "Le retrait n'a pas pu être appliqué."))
    return redirect("ui:checkout-detail", session_id=session_id)


@ui_access_required
def complete_checkout(request, session_id):
    if request.method != "POST" or not _can_complete_sale(request.user):
        raise PermissionDenied
    form = CompleteSaleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Vérifiez les informations de paiement.")
        return redirect("ui:checkout-detail", session_id=session_id)
    payload = {
        "expected_version": form.cleaned_data["expected_version"],
        "payment_method": form.cleaned_data["payment_method"],
        "payment_status": form.cleaned_data["payment_status"],
    }
    try:
        sale, _duplicate = complete_sale(
            session_id,
            request.user,
            form.cleaned_data["idempotency_key"],
            payload,
        )
        messages.success(request, f"Vente {sale.sale_number} enregistrée. Le stock a été mis à jour.")
        return redirect("ui:checkout")
    except DomainError as error:
        messages.error(request, DOMAIN_ERROR_MESSAGES.get(error.code, "La vente n'a pas pu être confirmée."))
        return redirect("ui:checkout-detail", session_id=session_id)


@ui_access_required
def release_checkout(request, session_id):
    if request.method != "POST" or not _can_release_basket(request.user):
        raise PermissionDenied
    form = ReleaseBasketForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Le panier n'a pas pu être libéré.")
        return redirect("ui:checkout-detail", session_id=session_id)
    payload = form.cleaned_data
    payload["reason"] = payload.get("reason") or "Panier renvoyé après vérification"
    try:
        release_basket(session_id, request.user, payload)
        messages.success(request, "Le panier est de nouveau ouvert aux détections.")
        return redirect("ui:checkout")
    except DomainError as error:
        messages.error(request, DOMAIN_ERROR_MESSAGES.get(error.code, "Le panier n'a pas pu être libéré."))
        return redirect("ui:checkout-detail", session_id=session_id)


@ui_access_required
def inventory(request):
    query = request.GET.get("q", "").strip()
    products = Product.objects.prefetch_related("vision_labels").order_by("name")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))
    return render(
        request,
        "ui/inventory.html",
        {
            "section": "inventory",
            "page_title": "Stock",
            "products": products,
            "query": query,
            "can_manage_stock": _can_manage_stock(request.user),
            "low_stock_count": Product.objects.filter(is_active=True, stock__lte=5).count(),
        },
    )


@ui_access_required
def rfid_enrollments(request, enrollment_id=None):
    _rfid_enrollment_access_required(request)
    pending = list(
        RfidEnrollmentRequest.objects.filter(status=RfidEnrollmentRequest.Status.PENDING)
        .select_related("device")
        .order_by("-last_seen_at", "-id")
    )
    selected = None
    if enrollment_id:
        selected = next((item for item in pending if item.id == enrollment_id), None)
        if selected is None:
            messages.warning(request, "Cette demande RFID n'est plus en attente.")
    if selected is None and pending:
        selected = pending[0]

    return render(
        request,
        "ui/rfid_enrollments.html",
        {
            "section": "rfid_enrollments",
            "page_title": "Cartes RFID",
            "pending": pending,
            "selected": selected,
            "approval_form": RfidEnrollmentApprovalForm(),
            "rejection_form": RfidEnrollmentRejectionForm(),
        },
    )


@ui_access_required
def approve_rfid_enrollment(request, enrollment_id):
    _rfid_enrollment_access_required(request)
    if request.method != "POST":
        raise PermissionDenied
    form = RfidEnrollmentApprovalForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Vérifiez les informations du client avant d'accepter la carte.")
        return redirect("ui:rfid-enrollment-detail", enrollment_id=enrollment_id)
    try:
        enrollment, customer = approve_rfid_enrollment_service(
            enrollment_id=enrollment_id,
            reviewer=request.user,
            existing_customer=form.cleaned_data["customer"],
            customer_code=form.cleaned_data["customer_code"],
            display_name=form.cleaned_data["display_name"],
        )
    except RfidEnrollmentError as error:
        messages.error(request, RFID_ENROLLMENT_ERROR_MESSAGES.get(error.code, "La carte n'a pas pu être acceptée."))
        return redirect("ui:rfid-enrollment-detail", enrollment_id=enrollment_id)
    messages.success(
        request,
        f"Carte RFID {enrollment.uid} associée à {customer.display_name}. Le portefeuille est prêt.",
    )
    return redirect("ui:rfid-enrollments")


@ui_access_required
def reject_rfid_enrollment(request, enrollment_id):
    _rfid_enrollment_access_required(request)
    if request.method != "POST":
        raise PermissionDenied
    form = RfidEnrollmentRejectionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Le motif du refus est invalide.")
        return redirect("ui:rfid-enrollment-detail", enrollment_id=enrollment_id)
    try:
        reject_rfid_enrollment_service(
            enrollment_id=enrollment_id,
            reviewer=request.user,
            reason=form.cleaned_data["reason"],
        )
    except RfidEnrollmentError as error:
        messages.error(request, RFID_ENROLLMENT_ERROR_MESSAGES.get(error.code, "La carte n'a pas pu être refusée."))
        return redirect("ui:rfid-enrollment-detail", enrollment_id=enrollment_id)
    messages.success(request, "Demande RFID refusée.")
    return redirect("ui:rfid-enrollments")


@ui_access_required
@transaction.atomic
def product_form(request, product_id=None):
    if not _can_manage_stock(request.user):
        raise PermissionDenied
    product = get_object_or_404(Product, pk=product_id) if product_id else None
    previous_stock = product.stock if product else 0
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        labels = form.cleaned_data["vision_labels"]
        current_labels = VisionLabel.objects.filter(product=product, model_version="")
        current_labels.exclude(label__in=labels).update(is_active=False)
        for label in labels:
            VisionLabel.objects.update_or_create(
                label=label,
                model_version="",
                defaults={"product": product, "is_active": True},
            )

        stock_delta = product.stock - previous_stock
        if stock_delta:
            StockMovement.objects.create(
                product=product,
                movement_type=StockMovement.Type.ADJUSTMENT,
                quantity=stock_delta,
                author=request.user,
                reason=form.cleaned_data.get("adjustment_reason")
                or ("Stock initial" if product_id is None else "Ajustement depuis l'interface"),
            )
        messages.success(request, f"{product.name} a été enregistré.")
        return redirect("ui:inventory")

    return render(
        request,
        "ui/product_form.html",
        {
            "section": "inventory",
            "page_title": "Modifier le produit" if product else "Nouveau produit",
            "form": form,
            "product": product,
        },
    )
