# inventory/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'inventory'

# Создаем роутер для ViewSets
router = DefaultRouter()
router.register(r'categories', views.ProductCategoryViewSet, basename='productcategory')
router.register(r'attribute-types', views.AttributeTypeViewSet, basename='attributetype')
router.register(r'attribute-values', views.AttributeValueViewSet, basename='attributevalue')
router.register(r'products', views.ProductViewSet, basename='product')
router.register(r'batches', views.ProductBatchViewSet, basename='productbatch')
router.register(r'stock', views.StockViewSet, basename='stock')
router.register(r'size-info', views.SizeInfoViewSet, basename='sizeinfo')

urlpatterns = [
    # ViewSets через роутер
    path('', include(router.urls)),

    # Дополнительные эндпоинты
    path('stats/', views.InventoryStatsView.as_view(), name='inventory-stats'),
    # в urls.py
    path('media/<path:path>', views.serve_media, name='serve_media'),
    path("products/<int:pk>/label/", views.product_label_proxy, name="product_label_proxy"),
]

"""
Полный список доступных эндпоинтов:

КАТЕГОРИИ:
- GET    categories/                    - Список всех категорий
- POST   categories/                    - Создать категорию
- GET    categories/{id}/               - Получить категорию
- PUT    categories/{id}/               - Обновить категорию
- PATCH  categories/{id}/               - Частично обновить
- DELETE categories/{id}/               - Удалить категорию

ТИПЫ АТРИБУТОВ:
- GET    attribute-types/               - Список типов атрибутов
- POST   attribute-types/               - Создать тип атрибута
- GET    attribute-types/{id}/          - Получить тип атрибута
- PUT    attribute-types/{id}/          - Обновить тип атрибута
- PATCH  attribute-types/{id}/          - Частично обновить
- DELETE attribute-types/{id}/          - Удалить тип атрибута
- GET    attribute-types/for_product_creation/ - Атрибуты для создания товара

ЗНАЧЕНИЯ АТРИБУТОВ:
- GET    attribute-values/              - Список значений атрибутов
- POST   attribute-values/              - Создать значение атрибута
- GET    attribute-values/{id}/         - Получить значение атрибута
- PUT    attribute-values/{id}/         - Обновить значение атрибута
- PATCH  attribute-values/{id}/         - Частично обновить
- DELETE attribute-values/{id}/         - Удалить значение атрибута

ТОВАРЫ:
- GET    products/                      - Список товаров
- POST   products/                      - Создать товар/добавить партию
- GET    products/{id}/                 - Получить товар
- PUT    products/{id}/                 - Обновить товар
- PATCH  products/{id}/                 - Частично обновить товар
- DELETE products/{id}/                 - Удалить товар
- GET    products/scan_barcode/?barcode=123 - Сканировать штрих-код
- POST   products/{id}/sell/            - Продать товар
- GET    products/low_stock/            - Товары с низким остатком

ПАРТИИ ТОВАРОВ:
- GET    batches/                       - Список партий
- POST   batches/                       - Создать партию
- GET    batches/{id}/                  - Получить партию
- PUT    batches/{id}/                  - Обновить партию
- PATCH  batches/{id}/                  - Частично обновить партию
- DELETE batches/{id}/                  - Удалить партию
- GET    batches/expiring_soon/         - Партии с истекающим сроком

ОСТАТКИ НА СКЛАДЕ:
- GET    stock/                         - Список остатков
- POST   stock/                         - Создать остаток
- GET    stock/{id}/                    - Получить остаток
- PUT    stock/{id}/                    - Обновить остаток
- PATCH  stock/{id}/                    - Частично обновить остаток
- DELETE stock/{id}/                    - Удалить остаток
- GET    stock/summary/                 - Сводка по остаткам
- POST   stock/{id}/adjust/             - Корректировка остатков

РАЗМЕРНАЯ ИНФОРМАЦИЯ:
- GET    size-info/                     - Список размерной информации
- POST   size-info/                     - Создать размерную информацию
- GET    size-info/{id}/                - Получить размерную информацию
- PUT    size-info/{id}/                - Обновить размерную информацию
- PATCH  size-info/{id}/                - Частично обновить
- DELETE size-info/{id}/                - Удалить размерную информацию

СТАТИСТИКА:
- GET    stats/                         - Общая статистика склада
"""