from django.urls import path
from django.http import JsonResponse
from . import views

# 1. Vue de test pour l'API
def api_test_view(request):
    return JsonResponse({
        "status": "success",
        "message": "Bienvenue sur l'API Kitunga AI !"
    })

# 2. Configuration des routes
urlpatterns = [
    # Route de test -> http://127.0.0.1:8000/api/test/
    path('test/', api_test_view, name='api-test'),

    # Dashboard & Monitoring Live (Support des deux formats d'URL)
    path('dashboard-stats/', views.dashboard_stats, name='dashboard-stats'),
    path('dashboard/stats/', views.dashboard_stats, name='dashboard-stats-alt'),

    # Endpoints de Détection (Raspberry Pi / Caméra)
    path('add-detection/', views.add_detection, name='add-detection'),
    path('add-detection/<str:device_id>/', views.add_detection, name='add-detection-device'),
    path('baskets/<str:device_id>/add-detection/', views.add_detection, name='pi-add-detection'),
    path('baskets/ensure-active/', views.add_detection, name='ensure-active'),

    # Endpoints de Gestion du Panier (Consultation, Retrait, Nettoyage)
    path('basket/<str:device_id>/', views.get_basket, name='get-basket'),
    path('basket/<str:device_id>/remove/', views.remove_item, name='remove-item'),
    path('basket/<str:device_id>/clear/', views.clear_basket, name='clear-basket'),
]
