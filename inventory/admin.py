# inventory/admin.py
from django.contrib import admin
from .models import ProductCategory, Product, Stock, ProductBatch
import logging

logger = logging.getLogger('inventory')

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'barcode', 'category', 'sale_price', 'stock_quantity']
    list_filter = ['category']
    search_fields = ['name', 'barcode']
    def stock_quantity(self, obj):
        return obj.stock.quantity
    def save_model(self, request, obj, form, change):
        logger.info(f"[SomPOS] Admin {request.user} {'updated' if change else 'created'} product {obj.name}")
        super().save_model(request, obj, form, change)
    def delete_model(self, request, obj):
        logger.info(f"[SomPOS] Admin {request.user} deleted product {obj.name}")
        super().delete_model(request, obj)

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ['product', 'quantity', 'updated_at']

@admin.register(ProductBatch)
class ProductBatchAdmin(admin.ModelAdmin):
    list_display = ['product', 'quantity', 'expiration_date', 'created_at']
    list_filter = ['expiration_date']