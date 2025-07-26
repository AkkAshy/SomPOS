# inventory/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductCategoryCreateView,
    ProductCategoryListView,
    ProductCreateView,
    ProductListView,
    ProductSearchView,
    ProductBarcodeLookupView,
    StockManagementView,
    ProductBatchCreateView,
    ProductScanView,
    StockkeeperProductAddView,
    MeasurementCategoryViewSet,
    UnitOfMeasureViewSet,

)


router = DefaultRouter()
router.register(r'measurement-categories', MeasurementCategoryViewSet, basename='measurement-category')
router.register(r'units', UnitOfMeasureViewSet, basename='unit')

urlpatterns = [
    path('', include(router.urls)),
    # Категории товаров
    path('categories/', ProductCategoryListView.as_view(), name='category-list'),
    path('categories/create/', ProductCategoryCreateView.as_view(), name='category-create'),
    path('products/create/', ProductCreateView.as_view(), name='product-create'),
    
    # Товары
    path('products/', ProductListView.as_view(), name='product-list'),
    
    path('products/search/', ProductSearchView.as_view(), name='product-search'),
    path('products/barcode/', ProductBarcodeLookupView.as_view(), name='product-barcode'),
    path('products/scan/', ProductScanView.as_view(), name='product-scan'),
    
    # Склад и партии
    path('stock/update/', StockManagementView.as_view(), name='stock-update'),
    path('batches/create/', ProductBatchCreateView.as_view(), name='batch-create'),

    # Управление остатками
    path('stockkeeper/add/<int:product_id>/', StockkeeperProductAddView.as_view(), name='stockkeeper-add'),

]