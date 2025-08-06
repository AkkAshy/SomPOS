from django.urls import path
from .views import CustomerViewSet, CustomerSearchView

urlpatterns = [
    path('', CustomerViewSet.as_view({'get': 'list', 'post': 'create'}), name='customer-list'),
    path('<int:pk>/', CustomerViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='customer-detail'),
    path('search/', CustomerSearchView.as_view(), name='customer-search'),
]