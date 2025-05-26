# inventory/urls.py
from django.urls import path
from .views import ProductCategoryCreateView, ProductCreateView, ProductListView, StockUpdateView, ProductBatchCreateView, ProductScanView

urlpatterns = [
    path('categories/', ProductCategoryCreateView.as_view(), name='category-create'),
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/create/', ProductCreateView.as_view(), name='product-create'),
    path('stock/update/', StockUpdateView.as_view(), name='stock-update'),
    path('batches/create/', ProductBatchCreateView.as_view(), name='batch-create'),
    path('products/scan/', ProductScanView.as_view(), name='product-scan'),
]