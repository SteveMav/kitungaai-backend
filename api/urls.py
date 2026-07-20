from django.urls import path
from .views import add_detection, get_basket

urlpatterns = [
    # 🌟 LA LIGNE À RAJOUTER POUR LA PI :
    path('baskets/<str:device_id>/add-detection/', add_detection, name='pi-add-detection'),
    
    # Tes routes actuelles qui fonctionnent déjà
    path('baskets/ensure-active/', add_detection, name='ensure-active'), 
    path('add-detection/', add_detection, name='add-detection'),
    path('basket/<str:device_id>/', get_basket, name='get-basket'),
]