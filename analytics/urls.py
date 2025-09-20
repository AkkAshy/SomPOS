# analytics/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (SalesAnalyticsViewSet, ProductAnalyticsViewSet, CustomerAnalyticsViewSet, 
                    TransactionsHistoryByDayView, SupplierAnalyticsViewSet)

router = DefaultRouter()
router.register(r'sales', SalesAnalyticsViewSet, basename='sales-analytics')
router.register(r'products', ProductAnalyticsViewSet, basename='product-analytics')
router.register(r'customers', CustomerAnalyticsViewSet, basename='customer-analytics')
router.register(r'suppliers', SupplierAnalyticsViewSet, basename='supplier-analytics')

urlpatterns = [
    path('', include(router.urls)),
    path('transactions-by-day/', TransactionsHistoryByDayView.as_view(), name='transactions-by-day'),
]