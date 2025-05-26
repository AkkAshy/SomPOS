# inventory/urls.py
from django.urls import path
from .views import (
    ProductCategoryCreateView, ProductCategoryListView, ProductCreateView, ProductListView,
    ProductSearchView, ProductSearchByBarcodeView, StockUpdateView, ProductBatchCreateView,
    ProductScanCheckView, ProductScanCreateView, SaleCreateView
)

urlpatterns = [
    path('categories/', ProductCategoryCreateView.as_view(), name='category-create'),
    path('categories/list/', ProductCategoryListView.as_view(), name='category-list'),
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/create/', ProductCreateView.as_view(), name='product-create'),
    path('products/search/', ProductSearchView.as_view(), name='product-search'),
    path('products/search/by-barcode/', ProductSearchByBarcodeView.as_view(), name='product-search-by-barcode'),
    path('products/scan/check/', ProductScanCheckView.as_view(), name='product-scan-check'),
    path('products/scan/create/', ProductScanCreateView.as_view(), name='product-scan-create'),
    path('stock/update/', StockUpdateView.as_view(), name='stock-update'),
    path('batches/create/', ProductBatchCreateView.as_view(), name='batch-create'),
    path('sales/create/', SaleCreateView.as_view(), name='sale-create'),
]