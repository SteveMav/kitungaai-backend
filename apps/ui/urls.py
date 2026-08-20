from django.urls import path

from . import views


app_name = "ui"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("paniers/", views.baskets, name="baskets"),
    path("paniers/<uuid:session_id>/", views.baskets, name="basket-detail"),
    path("paniers/<uuid:session_id>/donnees/", views.basket_data, name="basket-data"),
    path(
        "paniers/<uuid:session_id>/verifier/",
        views.begin_manual_checkout_from_basket,
        name="begin-manual-checkout",
    ),
    path("caisse/", views.checkout, name="checkout"),
    path("caisse/<uuid:session_id>/", views.checkout, name="checkout-detail"),
    path(
        "caisse/<uuid:session_id>/lignes/<int:line_id>/corriger/",
        views.correct_checkout_line,
        name="correct-line",
    ),
    path(
        "caisse/<uuid:session_id>/objets-non-repertories/<int:line_id>/retirer/",
        views.remove_uncatalogued_checkout_line,
        name="remove-uncatalogued-line",
    ),
    path("caisse/<uuid:session_id>/confirmer/", views.complete_checkout, name="complete-checkout"),
    path("caisse/<uuid:session_id>/liberer/", views.release_checkout, name="release-checkout"),
    path("factures/", views.invoices, name="invoices"),
    path("factures/<uuid:sale_id>/", views.invoices, name="invoice-detail"),
    path("stock/", views.inventory, name="inventory"),
    path("stock/nouveau/", views.product_form, name="product-create"),
    path("stock/<int:product_id>/modifier/", views.product_form, name="product-edit"),
    path("cartes-rfid/", views.rfid_enrollments, name="rfid-enrollments"),
    path("cartes-rfid/ajouter/", views.register_rfid_card, name="rfid-card-register"),
    path(
        "cartes-rfid/cartes/<int:card_id>/associer/",
        views.reassign_rfid_card,
        name="rfid-card-reassign",
    ),
    path(
        "cartes-rfid/cartes/<int:card_id>/statut/",
        views.toggle_rfid_card,
        name="rfid-card-toggle",
    ),
    path(
        "cartes-rfid/cartes/<int:card_id>/supprimer/",
        views.remove_rfid_card,
        name="rfid-card-remove",
    ),
    path(
        "cartes-rfid/cartes/<int:card_id>/recharger/",
        views.top_up_rfid_card,
        name="rfid-card-top-up",
    ),
    path(
        "paiements-rfid/<uuid:request_id>/confirmer/",
        views.confirm_rfid_payment,
        name="rfid-payment-confirm",
    ),
    path(
        "paiements-rfid/<uuid:request_id>/refuser/",
        views.reject_rfid_payment,
        name="rfid-payment-reject",
    ),
    path("cartes-rfid/<int:enrollment_id>/", views.rfid_enrollments, name="rfid-enrollment-detail"),
    path(
        "cartes-rfid/<int:enrollment_id>/accepter/",
        views.approve_rfid_enrollment,
        name="rfid-enrollment-approve",
    ),
    path(
        "cartes-rfid/<int:enrollment_id>/refuser/",
        views.reject_rfid_enrollment,
        name="rfid-enrollment-reject",
    ),
]
