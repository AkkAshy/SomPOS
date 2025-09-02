# sales/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TransactionViewSet, TransactionHistoryListView, CashierSalesSummaryView


router = DefaultRouter()
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'transaction-history', TransactionHistoryListView, basename='transaction-history')



urlpatterns = [
    path('', include(router.urls)),
    path('cashier-summary/', CashierSalesSummaryView.as_view(), name='cashier-summary'),
]