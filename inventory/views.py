
# inventory/views.py
from rest_framework import status, generics, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from django.db import transaction, models
from django.db.models import Q, Sum, Prefetch, F
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, NumberFilter, CharFilter
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.pagination import LimitOffsetPagination
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import logging
from django.core.exceptions import ValidationError
from rest_framework import pagination
from .pagination import OptionalPagination
from stores.mixins import StoreViewSetMixin, StoreSerializerMixin, StorePermissionMixin
from decimal import Decimal



from customers.views import FlexiblePagination

from .models import (
    Product, ProductCategory, Stock, ProductBatch,
    AttributeType, AttributeValue, ProductAttribute,
    SizeChart, SizeInfo, CustomUnit
)
from .serializers import (
    ProductSerializer, ProductCategorySerializer, StockSerializer,
    ProductBatchSerializer, AttributeTypeSerializer, AttributeValueSerializer,
    ProductAttributeSerializer, SizeChartSerializer, SizeInfoSerializer,
    ProductMultiSizeCreateSerializer, CustomUnitSerializer
)

from .filters import ProductFilter, ProductBatchFilter, StockFilter, SizeInfoFilter
from .pagination import CustomLimitOffsetPagination
# в одном из ваших приложений views.py
from django.http import HttpResponse, Http404
from django.conf import settings
import os

def serve_media(request, path):
    try:
        media_path = os.path.join(settings.MEDIA_ROOT, path)
        with open(media_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='image/png')
            response['Access-Control-Allow-Origin'] = 'http://localhost:5173'
            return response
    except:
        raise Http404




logger = logging.getLogger('inventory')

class CustomUnitViewSet(StoreViewSetMixin, ModelViewSet):
    """
    ViewSet для управления пользовательскими единицами измерения
    """
    serializer_class = CustomUnitSerializer
    pagination_class = CustomLimitOffsetPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'short_name']
    ordering_fields = ['name', 'short_name']
    ordering = ['name']

    def get_queryset(self):
        """Возвращает единицы только для текущего магазина"""
        current_store = self.get_current_store()
        if current_store:
            return CustomUnit.objects.filter(store=current_store)
        return CustomUnit.objects.none()

    @swagger_auto_schema(
        operation_description="Создать новую пользовательскую единицу измерения",
        request_body=CustomUnitSerializer,
        responses={201: CustomUnitSerializer}
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def presets(self, request):
        """
        Получить предустановленные шаблоны единиц измерения
        """
        presets = [
            {
                'name': 'Метр погонный',
                'short_name': 'м.п.',
                'allow_decimal': True,
                'min_quantity': 0.1,
                'step': 0.01,
                'description': 'Для кабелей, труб, профилей'
            },
            {
                'name': 'Квадратный метр',
                'short_name': 'кв.м',
                'allow_decimal': True,
                'min_quantity': 0.01,
                'step': 0.01,
                'description': 'Для плитки, обоев, листовых материалов'
            },
            {
                'name': 'Кубический метр',
                'short_name': 'куб.м',
                'allow_decimal': True,
                'min_quantity': 0.001,
                'step': 0.001,
                'description': 'Для сыпучих материалов, бетона'
            },
            {
                'name': 'Тонна',
                'short_name': 'тн',
                'allow_decimal': True,
                'min_quantity': 0.001,
                'step': 0.001,
                'description': 'Для тяжелых материалов'
            },
            {
                'name': 'Рулон',
                'short_name': 'рул',
                'allow_decimal': False,
                'min_quantity': 1,
                'step': 1,
                'description': 'Для рулонных материалов'
            },
            {
                'name': 'Лист',
                'short_name': 'лист',
                'allow_decimal': False,
                'min_quantity': 1,
                'step': 1,
                'description': 'Для листовых материалов'
            }
        ]

        return Response({
            'presets': presets,
            'message': 'Рекомендуемые единицы измерения для стройматериалов'
        })


class SizeInfoPagination(LimitOffsetPagination):
    """
    Кастомная пагинация для SizeInfo с информацией о магазине
    """
    default_limit = 20
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = 100

    def get_current_store_from_request(self, request):
        """
        Безопасное получение текущего магазина из запроса
        """
        try:
            # Пытаемся получить магазин из атрибута пользователя
            if hasattr(request.user, 'current_store') and request.user.current_store:
                return request.user.current_store

            # Альтернативный способ - через view, если доступен
            if hasattr(request, '_request') and hasattr(request._request, 'resolver_match'):
                view = getattr(request._request.resolver_match, 'func', None)
                if hasattr(view, 'cls') and hasattr(view.cls, 'get_current_store'):
                    # Создаем временный экземпляр view для получения магазина
                    view_instance = view.cls()
                    view_instance.request = request
                    return view_instance.get_current_store()

            # Если есть контекст с view
            if hasattr(self, 'request') and hasattr(self.request, 'parser_context'):
                view = self.request.parser_context.get('view')
                if view and hasattr(view, 'get_current_store'):
                    return view.get_current_store()

        except Exception as e:
            logger.warning(f"Не удалось получить текущий магазин в пагинации: {e}")

        return None

    def get_store_info(self, request):
        """
        Получение информации о магазине для добавления в ответ
        """
        current_store = self.get_current_store_from_request(request)
        if current_store:
            return {
                'id': str(current_store.id),
                'name': current_store.name
            }
        return None

    def get_paginated_response(self, data):
        """
        Формирование ответа с пагинацией и информацией о магазине
        """
        response_data = {
            'count': self.count,
            'limit': self.limit,
            'offset': self.offset,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        }

        # Добавляем информацию о магазине, если доступна
        try:
            # Получаем request из контекста
            request = None
            if hasattr(self, 'request'):
                request = self.request
            elif hasattr(self, 'context') and 'request' in self.context:
                request = self.context['request']

            if request:
                store_info = self.get_store_info(request)
                if store_info:
                    response_data['store_info'] = store_info
                    logger.debug(f"Добавлена информация о магазине в пагинацию: {store_info['name']}")
                else:
                    logger.debug("Информация о магазине недоступна для пагинации")
        except Exception as e:
            logger.error(f"Ошибка при добавлении информации о магазине в пагинацию: {e}")

        return Response(response_data)

class CustomPagination(LimitOffsetPagination):
    """
    Кастомная пагинация с настраиваемыми параметрами
    """
    default_limit = 20
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.count,
            'limit': self.limit,
            'offset': self.offset,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })

# class ProductCategoryViewSet(StoreViewSetMixin, ModelViewSet):
#     """
#     ViewSet для управления категориями товаров
#     """
#     pagination_class = CustomPagination
#     serializer_class = ProductCategorySerializer
#     filter_backends = [SearchFilter, OrderingFilter]
#     search_fields = ['name']
#     ordering_fields = ['name', 'created_at']
#     ordering = ['name']

#     def get_current_store_safely(self):
#         """Безопасное получение текущего магазина с комплексной обработкой ошибок"""
#         try:
#             current_store = self.get_current_store()
#             if not current_store:
#                 logger.warning(f"Не найден текущий магазин для пользователя {self.request.user.username}")
#             return current_store
#         except Exception as e:
#             logger.error(f"Ошибка получения текущего магазина для пользователя {self.request.user.username}: {e}")
#             return None

#     def get_queryset(self):
#         """Получение категорий с фильтрацией по текущему магазину"""
#         current_store = self.get_current_store_safely()
#         if current_store:
#             return ProductCategory.objects.filter(store=current_store).select_related('store')
#         return ProductCategory.objects.none()

#     def list(self, request, *args, **kwargs):
#         """Улучшенный метод list с комплексным логированием"""
#         logger.info(f"📋 ЗАПРОС СПИСКА КАТЕГОРИЙ - Пользователь: {request.user.username}")

#         current_store = self.get_current_store_safely()
#         if not current_store:
#             return Response({
#                 'error': 'Текущий магазин недоступен',
#                 'detail': 'Пользователь должен быть связан с активным магазином',
#                 'results': [],
#                 'count': 0
#             }, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             # Используем стандартную реализацию DRF list с нашим queryset
#             response = super().list(request, *args, **kwargs)

#             # Добавляем информацию о магазине в ответ
#             if isinstance(response.data, dict):
#                 response.data['store_info'] = {
#                     'id': str(current_store.id),
#                     'name': current_store.name
#                 }

#             logger.info(f"✅ Успешно возвращены категории для магазина: {current_store.name}")
#             return response

#         except Exception as e:
#             logger.error(f"❌ Ошибка в списке категорий: {e}")
#             return Response({
#                 'error': 'Не удалось получить категории',
#                 'detail': str(e)
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#     @action(detail=False, methods=['get'])
#     def debug_info(self, request):
#         """
#         Упрощенный endpoint отладки с учетом безопасности
#         Доступен только в режиме разработки
#         """
#         if not settings.DEBUG:
#             return Response({
#                 'error': 'Endpoint отладки доступен только в режиме разработки'
#             }, status=status.HTTP_404_NOT_FOUND)

#         # Проверка прав доступа
#         if not request.user.is_staff:
#             return Response({
#                 'error': 'Недостаточно прав доступа'
#             }, status=status.HTTP_403_FORBIDDEN)

#         current_store = self.get_current_store_safely()

#         debug_info = {
#             'user_info': {
#                 'username': request.user.username,
#                 'user_id': request.user.id,
#                 'is_authenticated': request.user.is_authenticated,
#                 'is_staff': request.user.is_staff,
#             },
#             'store_info': {
#                 'has_current_store': current_store is not None,
#                 'store_id': str(current_store.id) if current_store else None,
#                 'store_name': current_store.name if current_store else None,
#             },
#             'categories_info': {
#                 'queryset_count': self.get_queryset().count(),
#             }
#         }

#         # Добавляем детальную информацию о категориях, если магазин существует
#         if current_store:
#             try:
#                 categories = ProductCategory.objects.filter(store=current_store)
#                 debug_info['categories_info'].update({
#                     'categories_count': categories.count(),
#                     'categories_list': [
#                         {
#                             'id': cat.id,
#                             'name': cat.name,
#                             'created_at': cat.created_at.isoformat() if cat.created_at else None
#                         }
#                         for cat in categories[:10]  # Ограничиваем первыми 10 для производительности
#                     ]
#                 })
#             except Exception as e:
#                 debug_info['categories_info']['error'] = str(e)

#         return Response(debug_info)

#     def handle_exception(self, exc):
#         """Кастомная обработка исключений с логированием"""
#         logger.error(f"Исключение в ProductCategoryViewSet: {exc}")
#         return super().handle_exception(exc)

#     def perform_create(self, serializer):
#         """Обеспечиваем создание категории для текущего магазина"""
#         current_store = self.get_current_store_safely()
#         if not current_store:
#             raise ValidationError("Невозможно создать категорию без текущего магазина")

#         serializer.save(store=current_store)
#         logger.info(f"Создана категория '{serializer.instance.name}' для магазина '{current_store.name}'")

#     def perform_update(self, serializer):
#         """Логирование обновлений категорий"""
#         old_name = serializer.instance.name
#         serializer.save()
#         new_name = serializer.instance.name

#         if old_name != new_name:
#             logger.info(f"Обновлена категория '{old_name}' на '{new_name}'")

#     def perform_destroy(self, instance):
#         """Логирование удаления категорий"""
#         category_name = instance.name
#         store_name = instance.store.name
#         super().perform_destroy(instance)
#         logger.info(f"Удалена категория '{category_name}' из магазина '{store_name}'")



class ProductCategoryViewSet(StoreViewSetMixin, ModelViewSet):
    """
    ViewSet для управления категориями товаров с поддержкой soft delete
    """
    pagination_class = CustomPagination
    serializer_class = ProductCategorySerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_current_store_safely(self):
        """Безопасное получение текущего магазина с комплексной обработкой ошибок"""
        try:
            current_store = self.get_current_store()
            if not current_store:
                logger.warning(f"Не найден текущий магазин для пользователя {self.request.user.username}")
            return current_store
        except Exception as e:
            logger.error(f"Ошибка получения текущего магазина для пользователя {self.request.user.username}: {e}")
            return None

    def get_queryset(self):
        """Получение АКТИВНЫХ категорий с фильтрацией по текущему магазину"""
        current_store = self.get_current_store_safely()
        if current_store:
            # objects manager уже фильтрует по deleted_at__isnull=True
            return ProductCategory.objects.filter(store=current_store).select_related('store')
        return ProductCategory.objects.none()

    def list(self, request, *args, **kwargs):
        """Улучшенный метод list с комплексным логированием"""
        logger.info(f"📋 ЗАПРОС СПИСКА КАТЕГОРИЙ - Пользователь: {request.user.username}")

        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин недоступен',
                'detail': 'Пользователь должен быть связан с активным магазином',
                'results': [],
                'count': 0
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            response = super().list(request, *args, **kwargs)

            if isinstance(response.data, dict):
                response.data['store_info'] = {
                    'id': str(current_store.id),
                    'name': current_store.name
                }

            logger.info(f"✅ Успешно возвращены активные категории для магазина: {current_store.name}")
            return response

        except Exception as e:
            logger.error(f"❌ Ошибка в списке категорий: {e}")
            return Response({
                'error': 'Не удалось получить категории',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def deleted(self, request):
        """Получить список удаленных категорий"""
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин недоступен'
            }, status=status.HTTP_400_BAD_REQUEST)

        deleted_categories = ProductCategory.all_objects.filter(
            store=current_store,
            deleted_at__isnull=False
        ).order_by('-deleted_at')

        serializer = self.get_serializer(deleted_categories, many=True)
        return Response({
            'results': serializer.data,
            'count': deleted_categories.count()
        })

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Восстановить удаленную категорию"""
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин недоступен'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Ищем среди всех объектов (включая удаленные)
            category = ProductCategory.all_objects.get(
                pk=pk,
                store=current_store,
                deleted_at__isnull=False
            )
        except ProductCategory.DoesNotExist:
            return Response({
                'error': 'Удаленная категория не найдена'
            }, status=status.HTTP_404_NOT_FOUND)

        # Проверяем, нет ли уже активной категории с таким именем
        if ProductCategory.objects.filter(
            store=current_store,
            name__iexact=category.name
        ).exists():
            return Response({
                'error': f'Категория с названием "{category.name}" уже существует. Удалите её сначала или переименуйте.'
            }, status=status.HTTP_400_BAD_REQUEST)

        category.restore()
        logger.info(f"Восстановлена категория '{category.name}' в магазине '{current_store.name}'")

        serializer = self.get_serializer(category)
        return Response({
            'message': f'Категория "{category.name}" успешно восстановлена',
            'category': serializer.data
        })

    @action(detail=True, methods=['delete'])
    def hard_delete(self, request, pk=None):
        """Окончательное удаление категории из БД (только для админов)"""
        if not request.user.is_staff:
            return Response({
                'error': 'Недостаточно прав для окончательного удаления'
            }, status=status.HTTP_403_FORBIDDEN)

        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин недоступен'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            category = ProductCategory.all_objects.get(pk=pk, store=current_store)
        except ProductCategory.DoesNotExist:
            return Response({
                'error': 'Категория не найдена'
            }, status=status.HTTP_404_NOT_FOUND)

        category_name = category.name
        category.hard_delete()
        logger.warning(f"ОКОНЧАТЕЛЬНО удалена категория '{category_name}' из магазина '{current_store.name}' пользователем {request.user.username}")

        return Response({
            'message': f'Категория "{category_name}" окончательно удалена'
        })

    def perform_create(self, serializer):
        """Обеспечиваем создание категории для текущего магазина"""
        current_store = self.get_current_store_safely()
        if not current_store:
            raise ValidationError("Невозможно создать категорию без текущего магазина")

        serializer.save(store=current_store)
        logger.info(f"Создана категория '{serializer.instance.name}' для магазина '{current_store.name}'")

    def perform_update(self, serializer):
        """Логирование обновлений категорий"""
        old_name = serializer.instance.name
        serializer.save()
        new_name = serializer.instance.name

        if old_name != new_name:
            logger.info(f"Обновлена категория '{old_name}' на '{new_name}'")

    def perform_destroy(self, instance):
        """Soft delete вместо реального удаления"""
        category_name = instance.name
        store_name = instance.store.name

        # Используем soft delete
        instance.delete()  # Это наш кастомный метод delete()

        logger.info(f"Мягко удалена категория '{category_name}' из магазина '{store_name}'")

    @action(detail=False, methods=['get'])
    def debug_info(self, request):
        """Упрощенный endpoint отладки с информацией о удаленных категориях"""
        if not settings.DEBUG:
            return Response({
                'error': 'Endpoint отладки доступен только в режиме разработки'
            }, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff:
            return Response({
                'error': 'Недостаточно прав доступа'
            }, status=status.HTTP_403_FORBIDDEN)

        current_store = self.get_current_store_safely()

        debug_info = {
            'user_info': {
                'username': request.user.username,
                'user_id': request.user.id,
                'is_authenticated': request.user.is_authenticated,
                'is_staff': request.user.is_staff,
            },
            'store_info': {
                'has_current_store': current_store is not None,
                'store_id': str(current_store.id) if current_store else None,
                'store_name': current_store.name if current_store else None,
            },
            'categories_info': {
                'active_count': self.get_queryset().count(),
                'deleted_count': 0,
                'total_count': 0,
            }
        }

        if current_store:
            try:
                active_categories = ProductCategory.objects.filter(store=current_store)
                deleted_categories = ProductCategory.all_objects.filter(store=current_store, deleted_at__isnull=False)
                total_categories = ProductCategory.all_objects.filter(store=current_store)

                debug_info['categories_info'].update({
                    'active_count': active_categories.count(),
                    'deleted_count': deleted_categories.count(),
                    'total_count': total_categories.count(),
                    'active_categories': [
                        {
                            'id': cat.id,
                            'name': cat.name,
                            'created_at': cat.created_at.isoformat() if cat.created_at else None
                        }
                        for cat in active_categories[:5]
                    ],
                    'deleted_categories': [
                        {
                            'id': cat.id,
                            'name': cat.name,
                            'deleted_at': cat.deleted_at.isoformat() if cat.deleted_at else None
                        }
                        for cat in deleted_categories[:5]
                    ]
                })
            except Exception as e:
                debug_info['categories_info']['error'] = str(e)

        return Response(debug_info)


class AttributeTypeViewSet(ModelViewSet):
    """
    ViewSet для управления типами атрибутов (динамические атрибуты)
    """
    queryset = AttributeType.objects.prefetch_related('values').all()
    serializer_class = AttributeTypeSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'slug']
    ordering_fields = ['name']
    ordering = ['name']

    @swagger_auto_schema(
        operation_description="Получить все типы атрибутов с их значениями",
        responses={200: AttributeTypeSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def for_product_creation(self, request):
        """
        Получить все активные атрибуты для создания товара
        """
        attributes = self.get_queryset().filter(values__isnull=False).distinct()
        serializer = self.get_serializer(attributes, many=True)
        return Response({
            'attributes': serializer.data,
            'message': _('Доступные атрибуты для создания товара')
        })


class AttributeValueViewSet(ModelViewSet):
    """
    ViewSet для управления значениями атрибутов
    """
    queryset = AttributeValue.objects.select_related('attribute_type').all()
    serializer_class = AttributeValueSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['attribute_type']
    search_fields = ['value']




class ProductViewSet(
    StoreViewSetMixin,
    StorePermissionMixin,   # ✅ этот можно оставить
    viewsets.ModelViewSet
):
    pagination_class = FlexiblePagination
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'barcode', 'category__name', 'created_by__username']
    filterset_fields = ['category', 'created_by']
    ordering_fields = ['name', 'sale_price', 'created_at']
    ordering = ['-created_at']

    queryset = Product.objects.select_related("category", "stock").prefetch_related("size", "batches")
    # def get_queryset(self):
    #     # ✅ получаем текущий магазин
    #     current_store = self.get_current_store()

    #     # если магазин не найден — возвращаем пустой queryset
    #     if not current_store:
    #         return Product.objects.none()

    #     return Product.objects.filter(
    #         store=current_store  # 🔥 фильтрация по магазину
    #     ).select_related(
    #         'category', 'stock'
    #     ).prefetch_related(
    #         'size',
    #         'batches'
    #     )


    @swagger_auto_schema(
        operation_description="Создать товары для множественных размеров",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'name': openapi.Schema(type=openapi.TYPE_STRING, description='Базовое название товара'),
                'category': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID категории'),
                'sale_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Цена продажи'),
                'unit': openapi.Schema(type=openapi.TYPE_STRING, description='Единица измерения'),
                'size_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                    description='Массив ID размеров'
                ),
                'batch_info': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'purchase_price': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'supplier': openapi.Schema(type=openapi.TYPE_STRING),
                        'expiration_date': openapi.Schema(type=openapi.TYPE_STRING, format='date', nullable=True)
                    },
                    required=[]
                )
            },
            required=['name', 'category', 'sale_price', 'size_ids']
        ),
        responses={
            201: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'products': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT)
                    ),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER)
                }
            ),
            400: 'Ошибка валидации'
        }
    )

# {
#     "name": "Футболка Армани",
#     "category": 1,
#     "sale_price": 150000.00,
#     "unit": "piece",
#     "size_ids": [1, 2, 3, 4],  // ID размеров S, M, L, XL
#     "batch_info": {
#         "quantity": 10,
#         "purchase_price": 100000.00,
#         "supplier": "Армани Official",
#         "expiration_date": null
#     }
# }


    @action(detail=False, methods=['post'])
    def create_multi_size(self, request):
        """
        Создание товаров с множественными размерами.
        Каждый размер создается как отдельный Product с уникальным штрих-кодом.
        """
        # Проверяем аутентификацию
        if not request.user.is_authenticated:
            return Response({
                'error': _('Необходима аутентификация')
            }, status=status.HTTP_401_UNAUTHORIZED)

        # ✅ ВАЖНО: Получаем текущий магазин
        current_store = self.get_current_store()
        if not current_store:
            return Response({
                'error': 'Магазин не определен. Переавторизуйтесь или выберите магазин.',
                'debug_info': {
                    'user': request.user.username,
                    'has_current_store': hasattr(request.user, 'current_store'),
                    'current_store_value': getattr(request.user, 'current_store', None)
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = ProductMultiSizeCreateSerializer(data=request.data)

        if serializer.is_valid():
            try:
                with transaction.atomic():
                    # ✅ Передаем created_by И store
                    created_products = serializer.save(
                        created_by=request.user,
                        store=current_store  # ← ДОБАВЛЕНО
                    )

                # Сериализуем созданные товары для ответа
                products_data = ProductSerializer(created_products, many=True, context={'request': request}).data

                logger.info(f"Создано {len(created_products)} товаров с размерами пользователем {request.user.username}")

                return Response({
                    'products': products_data,
                    'message': _('Товары успешно созданы для всех размеров'),
                    'count': len(created_products),
                    'action': 'multi_size_products_created'
                }, status=status.HTTP_201_CREATED)

            except Exception as e:
                logger.error(f"Ошибка при создании товаров с размерами: {str(e)}")
                return Response({
                    'error': _('Ошибка при создании товаров'),
                    'details': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Также добавь этот вспомогательный endpoint для получения размеров
    @action(detail=False, methods=['get'])
    def available_sizes(self, request):
        """
        Получить все доступные размеры для создания товаров
        """
        sizes = SizeInfo.objects.all().order_by('size')
        serializer = SizeInfoSerializer(sizes, many=True)

        return Response({
            'sizes': serializer.data,
            'count': sizes.count(),
            'message': _('Доступные размеры для товаров')
        })

    @action(detail=False, methods=['get'])
    def units_info(self, request):
        """
        Получить информацию о доступных единицах измерения
        """
        current_store = self.get_current_store()
        if not current_store:
            return Response({'error': 'Магазин не определен'}, status=400)

        # Системные единицы
        system_units = [
            {
                'value': choice[0],
                'label': choice[1],
                'settings': Product.UNIT_SETTINGS.get(choice[0], {})
            }
            for choice in Product.SYSTEM_UNITS
        ]

        # Пользовательские единицы
        custom_units = CustomUnit.objects.filter(store=current_store)
        custom_units_data = [
            {
                'id': unit.id,
                'name': unit.name,
                'short_name': unit.short_name,
                'allow_decimal': unit.allow_decimal,
                'min_quantity': float(unit.min_quantity),
                'step': float(unit.step)
            }
            for unit in custom_units
        ]

        return Response({
            'system_units': system_units,
            'custom_units': custom_units_data,
            'store': {
                'id': str(current_store.id),
                'name': current_store.name
            }
        })

    @action(detail=False, methods=['get'])
    def pricing_analysis(self, request):
        """
        Анализ ценообразования товаров
        """
        current_store = self.get_current_store()
        if not current_store:
            return Response({'error': 'Магазин не определен'}, status=400)

        from django.db.models import Avg, Min, Max, Count

        # Анализ по всем товарам
        products = Product.objects.filter(store=current_store)
        
        pricing_stats = []
        
        for product in products:
            avg_purchase = product.average_purchase_price
            last_purchase = product.last_purchase_price
            min_purchase = product.min_purchase_price
            
            if avg_purchase and avg_purchase > 0:
                margin = ((product.sale_price - avg_purchase) / avg_purchase) * 100
                
                pricing_stats.append({
                    'product_id': product.id,
                    'product_name': product.name,
                    'sale_price': float(product.sale_price),
                    'purchase_prices': {
                        'average': float(avg_purchase) if avg_purchase else None,
                        'last': float(last_purchase) if last_purchase else None,
                        'minimum': float(min_purchase) if min_purchase else None,
                    },
                    'margin_percent': round(margin, 2),
                    'below_min_markup': margin < float(current_store.min_markup_percent),
                    'batches_count': product.batches.filter(quantity__gt=0).count(),
                    'unit_display': product.unit_display
                })

        # Сортируем по марже
        pricing_stats.sort(key=lambda x: x['margin_percent'])

        # Статистика
        margins = [p['margin_percent'] for p in pricing_stats if p['margin_percent'] is not None]
        
        summary = {
            'total_products': len(pricing_stats),
            'products_below_min_markup': len([p for p in pricing_stats if p['below_min_markup']]),
            'average_margin': round(sum(margins) / len(margins), 2) if margins else 0,
            'min_margin': min(margins) if margins else 0,
            'max_margin': max(margins) if margins else 0,
            'store_min_markup': float(current_store.min_markup_percent)
        }

        return Response({
            'summary': summary,
            'products': pricing_stats[:50],  # Первые 50 для производительности
            'store': {
                'id': str(current_store.id),
                'name': current_store.name,
                'min_markup_percent': float(current_store.min_markup_percent)
            }
        })

    @action(detail=True, methods=['post'])
    def update_pricing(self, request, pk=None):
        """
        Обновить цену товара с учетом минимальной наценки
        """
        product = self.get_object()
        new_price = request.data.get('sale_price')
        
        if not new_price:
            return Response(
                {'error': 'Укажите новую цену в поле sale_price'},
                status=400
            )

        try:
            new_price = Decimal(str(new_price))
        except (ValueError, TypeError):
            return Response(
                {'error': 'Некорректный формат цены'},
                status=400
            )

        # Проверяем минимальную наценку
        min_sale_price = product.min_sale_price
        current_store = self.get_current_store()
        
        if new_price < min_sale_price and not current_store.allow_sale_below_markup:
            # Проверяем права пользователя
            if not hasattr(request.user, 'store_role') or request.user.store_role not in ['owner', 'admin']:
                return Response({
                    'error': f'Цена ниже минимальной наценки. Минимальная цена: {min_sale_price}',
                    'min_price': float(min_sale_price),
                    'requested_price': float(new_price),
                    'min_markup_percent': float(current_store.min_markup_percent)
                }, status=400)

        # Обновляем цену
        old_price = product.sale_price
        product.sale_price = new_price
        product.save()

        logger.info(f"Price updated for {product.name}: {old_price} -> {new_price}")

        return Response({
            'message': 'Цена успешно обновлена',
            'product': {
                'id': product.id,
                'name': product.name,
                'old_price': float(old_price),
                'new_price': float(new_price),
                'unit_display': product.unit_display
            },
            'price_analysis': product.price_info
        })

    @action(detail=False, methods=['post'])
    def bulk_update_pricing(self, request):
        """
        Массовое обновление цен товаров
        """
        current_store = self.get_current_store()
        if not current_store:
            return Response({'error': 'Магазин не определен'}, status=400)

        # Проверяем права
        if not hasattr(request.user, 'store_role') or request.user.store_role not in ['owner', 'admin']:
            return Response({
                'error': 'Недостаточно прав для массового обновления цен'
            }, status=403)

        updates = request.data.get('updates', [])
        if not updates:
            return Response({
                'error': 'Укажите массив updates с product_id и sale_price'
            }, status=400)

        results = []
        errors = []

        with transaction.atomic():
            for update_data in updates:
                product_id = update_data.get('product_id')
                new_price = update_data.get('sale_price')

                try:
                    product = Product.objects.get(id=product_id, store=current_store)
                    new_price = Decimal(str(new_price))

                    # Проверяем минимальную наценку
                    min_sale_price = product.min_sale_price
                    if new_price < min_sale_price and not current_store.allow_sale_below_markup:
                        errors.append({
                            'product_id': product_id,
                            'product_name': product.name,
                            'error': f'Цена ниже минимальной наценки: {min_sale_price}',
                            'requested_price': float(new_price),
                            'min_price': float(min_sale_price)
                        })
                        continue

                    old_price = product.sale_price
                    product.sale_price = new_price
                    product.save()

                    results.append({
                        'product_id': product_id,
                        'product_name': product.name,
                        'old_price': float(old_price),
                        'new_price': float(new_price),
                        'success': True
                    })

                except Product.DoesNotExist:
                    errors.append({
                        'product_id': product_id,
                        'error': 'Товар не найден'
                    })
                except (ValueError, TypeError):
                    errors.append({
                        'product_id': product_id,
                        'error': 'Некорректный формат цены'
                    })
                except Exception as e:
                    errors.append({
                        'product_id': product_id,
                        'error': str(e)
                    })

        return Response({
            'message': f'Обновлено {len(results)} цен, ошибок: {len(errors)}',
            'successful_updates': results,
            'errors': errors,
            'summary': {
                'total_requested': len(updates),
                'successful': len(results),
                'failed': len(errors)
            }
        })


    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """✅ ИСПРАВЛЕННОЕ создание товара с правильной последовательностью"""
        barcode = request.data.get('barcode')
        batch_info = request.data.pop('batch_info', {})
        size_id = request.data.pop('size_id', None)

        # Получаем текущий магазин
        current_store = self.get_current_store() if hasattr(self, 'get_current_store') else getattr(request.user, 'current_store', None)

        if not current_store:
            return Response({
                'error': 'Магазин не определен. Переавторизуйтесь.',
                'debug_info': {
                    'user': request.user.username,
                    'has_current_store': hasattr(request.user, 'current_store')
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        # Проверяем существование товара по штрих-коду В ТЕКУЩЕМ МАГАЗИНЕ
        if barcode:
            existing_product = Product.objects.filter(
                store=current_store,
                barcode=barcode
            ).first()

            if existing_product:
                # Товар существует - добавляем партию
                if batch_info:
                    batch_data = {
                        'product': existing_product.id,
                        **batch_info
                    }
                    batch_serializer = ProductBatchSerializer(
                        data=batch_data,
                        context={'request': request}
                    )
                    if batch_serializer.is_valid():
                        # perform_create в StoreViewSetMixin автоматически добавит store
                        self.perform_create(batch_serializer)
                        logger.info(f"✅ Batch added to existing product {existing_product.name}")
                    else:
                        return Response(
                            {'batch_errors': batch_serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                serializer = self.get_serializer(existing_product)
                return Response({
                    'product': serializer.data,
                    'message': _('Партия добавлена к существующему товару'),
                    'action': 'batch_added'
                }, status=status.HTTP_200_OK)

        # ✅ СОЗДАЕМ НОВЫЙ ТОВАР - ПРАВИЛЬНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ

        # 1. Валидируем данные
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 2. Создаем товар через perform_create (установит store автоматически)
        self.perform_create(serializer)
        product = serializer.instance

        # 3. Теперь у product есть store, можем создать Stock вручную если нужно
        if not hasattr(product, 'stock'):
            try:
                Stock.objects.create(
                    product=product,
                    store=product.store,  # ← Теперь у product точно есть store
                    quantity=0
                )
                logger.info(f"✅ Stock manually created for {product.name}")
            except Exception as e:
                logger.error(f"❌ Error creating stock: {str(e)}")

        # 4. Обрабатываем размер
        if size_id:
            try:
                size_instance = SizeInfo.objects.get(id=size_id)
                product.size = size_instance
                product.save()
                logger.info(f"✅ Size {size_instance.size} set for {product.name}")
            except SizeInfo.DoesNotExist:
                return Response(
                    {'size_error': _('Размерная информация не найдена')},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 5. Создаем партию если указана
        if batch_info:
            batch_data = {
                'product': product.id,
                **batch_info
            }
            batch_serializer = ProductBatchSerializer(
                data=batch_data,
                context={'request': request}
            )
            if batch_serializer.is_valid():
                # perform_create добавит store к batch автоматически
                batch_viewset = ProductBatchViewSet()
                batch_viewset.request = request
                batch_viewset.perform_create(batch_serializer)
                logger.info(f"✅ Batch created for new product {product.name}")
            else:
                return Response(
                    {'batch_errors': batch_serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 6. Генерируем этикетку
        try:
            product.generate_label()
            logger.info(f"✅ Label generated for {product.name}")
        except Exception as e:
            logger.error(f"⚠️ Label generation failed: {str(e)}")

        # 7. Возвращаем результат
        updated_serializer = self.get_serializer(product)
        return Response({
            'product': updated_serializer.data,
            'message': _('Товар успешно создан'),
            'action': 'product_created'
        }, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        Обновление товара с атрибутами
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            product = serializer.save()

            # Обновляем атрибуты если переданы
            if 'attributes' in request.data:
                self._handle_product_attributes(product, request.data['attributes'])

            updated_serializer = self.get_serializer(product)
            return Response(updated_serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _handle_product_attributes(self, product, attributes_data):
        """
        Обработка атрибутов товара
        """
        if not attributes_data:
            return

        # Удаляем старые атрибуты
        ProductAttribute.objects.filter(product=product).delete()

        # Добавляем новые атрибуты
        for attr_data in attributes_data:
            attribute_value_id = attr_data.get('attribute_id')
            if attribute_value_id:
                try:
                    attribute_value = AttributeValue.objects.get(id=attribute_value_id)
                    ProductAttribute.objects.create(
                        product=product,
                        attribute_value=attribute_value
                    )
                except AttributeValue.DoesNotExist:
                    logger.warning(f"Атрибут с ID {attribute_value_id} не найден")

    @swagger_auto_schema(
        operation_description="Сканировать штрих-код и получить информацию о товаре",
        manual_parameters=[
            openapi.Parameter(
                'barcode',
                openapi.IN_QUERY,
                description="Штрих-код для сканирования",
                type=openapi.TYPE_STRING,
                required=True
            )
        ]
    )
    @action(detail=False, methods=['get'])
    def scan_barcode(self, request):
        """Сканирование штрих-кода - ищет только в текущем магазине"""
        barcode = request.query_params.get('barcode')
        if not barcode:
            return Response(
                {'error': _('Штрих-код не указан')},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ✅ ИСПРАВЛЕНИЕ: Используем get_current_store() как в других методах
        current_store = self.get_current_store()

        if not current_store:
            return Response({
                'error': 'Магазин не определен. Переавторизуйтесь или выберите магазин.',
                'debug_info': {
                    'user': request.user.username,
                    'has_current_store': hasattr(request.user, 'current_store'),
                    'current_store_value': getattr(request.user, 'current_store', None)
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ ИСПРАВЛЕНИЕ: Добавляем логирование для отладки
        logger.info(f"🔍 Scanning barcode: '{barcode}' in store: {current_store.name} (ID: {current_store.id})")

        # Ищем товар в текущем магазине
        product = Product.objects.filter(
            store=current_store,
            barcode=barcode
        ).select_related('category', 'stock').first()

        # ✅ ИСПРАВЛЕНИЕ: Дополнительная отладочная информация
        if not product:
            # Проверяем, есть ли товар с таким штрих-кодом в других магазинах
            other_stores_count = Product.objects.filter(barcode=barcode).exclude(store=current_store).count()
            all_products_count = Product.objects.filter(barcode=barcode).count()

            logger.warning(f"❌ Product not found. Barcode: '{barcode}', Current store: {current_store.id}, "
                          f"Products with this barcode in other stores: {other_stores_count}, "
                          f"Total products with this barcode: {all_products_count}")

        if product:
            logger.info(f"✅ Product found: {product.name} (ID: {product.id})")
            serializer = self.get_serializer(product)
            return Response({
                'found': True,
                'product': serializer.data,
                'message': _('Товар найден')
            })
        else:
            # Товар не найден, возвращаем категории текущего магазина
            categories = ProductCategory.objects.filter(store=current_store)

            return Response({
                'found': False,
                'barcode': barcode,
                'categories': ProductCategorySerializer(categories, many=True).data,
                'message': _('Товар не найден. Создайте новый товар.'),
                'debug_info': {
                    'current_store_id': current_store.id,
                    'current_store_name': current_store.name,
                    'barcode_searched': barcode
                }
            })

    @action(detail=True, methods=['post'])
    def sell(self, request, pk=None):
        """
        Продажа товара (списание со склада)
        """
        product = self.get_object()
        quantity = request.data.get('quantity', 0)

        if quantity <= 0:
            return Response(
                {'error': _('Количество должно быть больше нуля')},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                product.stock.sell(quantity)

            return Response({
                'message': _('Товар успешно продан'),
                'sold_quantity': quantity,
                'remaining_stock': product.stock.quantity
            })
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """
        Получить товары с низким остатком
        """
        min_quantity = int(request.query_params.get('min_quantity', 10))
        products = self.get_queryset().filter(stock__quantity__lte=min_quantity)

        serializer = self.get_serializer(products, many=True)
        return Response({
            'products': serializer.data,
            'count': products.count(),
            'min_quantity': min_quantity
        })

    @action(detail=False, methods=['get'])
    def product_sizes_info(self, request):
        """
        Получить информацию о размерах и количестве товаров по имени

        Query Parameters:
            - name: название товара (или его часть)

        Returns:
            - Если name передан: информация о товарах с этим именем, их размерах и количестве
            - Если name не передан: пустой JSON {}

        Example:
            GET /api/inventory/products/product_sizes_info/?name=Футболка

        Response:
            {
                "product_name": "Футболка",
                "total_products": 5,
                "total_stock": 150,
                "sizes": [
                    {
                        "size": "S",
                        "size_id": 1,
                        "count": 1,
                        "stock_quantity": 20,
                        "products": [
                            {
                                "id": 1,
                                "name": "Футболка - S",
                                "barcode": "123456789",
                                "stock": 20,
                                "price": 150000.00
                            }
                        ]
                    },
                    {
                        "size": "M",
                        "size_id": 2,
                        "count": 2,
                        "stock_quantity": 50,
                        "products": [...]
                    }
                ],
                "products_without_size": {
                    "count": 1,
                    "stock_quantity": 30,
                    "products": [...]
                }
            }
        """
        # Получаем параметр name из запроса
        product_name = request.query_params.get('name', '').strip()

        # Если name не передан или пустой - возвращаем пустой JSON
        if not product_name:
            return Response({})

        # Получаем текущий магазин
        current_store = self.get_current_store()
        if not current_store:
            return Response({
                'error': 'Магазин не определен'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Ищем товары по имени (частичное совпадение, регистронезависимо)
        products = Product.objects.filter(
            store=current_store,
            name__icontains=product_name
        ).select_related('size', 'stock', 'category').order_by('name', 'size__size')

        # Если товары не найдены
        if not products.exists():
            return Response({
                'product_name': product_name,
                'total_products': 0,
                'total_stock': 0,
                'sizes': [],
                'message': f'Товары с названием "{product_name}" не найдены'
            })

        # Группируем товары по размерам
        sizes_data = {}
        products_without_size = []
        total_stock = 0

        for product in products:
            stock_quantity = product.stock.quantity if hasattr(product, 'stock') else 0
            total_stock += stock_quantity

            product_info = {
                'id': product.id,
                'name': product.name,
                'barcode': product.barcode,
                'stock': stock_quantity,
                'price': float(product.sale_price),
                'category': product.category.name if product.category else None
            }

            if product.size:
                size_key = product.size.size
                if size_key not in sizes_data:
                    sizes_data[size_key] = {
                        'size': product.size.size,
                        'size_id': product.size.id,
                        'chest': product.size.chest,
                        'waist': product.size.waist,
                        'length': product.size.length,
                        'count': 0,
                        'stock_quantity': 0,
                        'products': []
                    }

                sizes_data[size_key]['count'] += 1
                sizes_data[size_key]['stock_quantity'] += stock_quantity
                sizes_data[size_key]['products'].append(product_info)
            else:
                products_without_size.append(product_info)

        # Преобразуем словарь размеров в список и сортируем
        size_order = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
        sizes_list = list(sizes_data.values())

        # Сортируем размеры в правильном порядке
        def size_sort_key(item):
            try:
                return size_order.index(item['size'])
            except ValueError:
                return 999  # Неизвестные размеры в конец

        sizes_list.sort(key=size_sort_key)

        # Формируем результат
        response_data = {
            'product_name': product_name,
            'total_products': products.count(),
            'total_stock': total_stock,
            'sizes': sizes_list
        }

        # Добавляем информацию о товарах без размера, если они есть
        if products_without_size:
            response_data['products_without_size'] = {
                'count': len(products_without_size),
                'stock_quantity': sum(p['stock'] for p in products_without_size),
                'products': products_without_size
            }

        return Response(response_data)


    @action(detail=False, methods=['get'])
    def sizes_summary(self, request):
        """
        Получить сводку по всем размерам в магазине
        Более простой вариант - только общая статистика

        Query Parameters:
            - name: (опционально) фильтр по имени товара

        Example:
            GET /api/inventory/products/sizes_summary/
            GET /api/inventory/products/sizes_summary/?name=Футболка
        """
        product_name = request.query_params.get('name', '').strip()

        # Если имя не указано - возвращаем пустой JSON
        if not product_name:
            return Response({})

        # Получаем текущий магазин
        current_store = self.get_current_store()
        if not current_store:
            return Response({
                'error': 'Магазин не определен'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Базовый queryset
        queryset = Product.objects.filter(store=current_store)

        # Фильтруем по имени если указано
        if product_name:
            queryset = queryset.filter(name__icontains=product_name)

        # Агрегируем данные по размерам
        from django.db.models import Count, Sum, Avg

        sizes_stats = queryset.filter(
            size__isnull=False
        ).values(
            'size__size'
        ).annotate(
            product_count=Count('id'),
            total_stock=Sum('stock__quantity'),
            avg_price=Avg('sale_price'),
            min_price=models.Min('sale_price'),
            max_price=models.Max('sale_price')
        ).order_by('size__size')

        # Преобразуем в список и сортируем
        size_order = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
        sizes_list = list(sizes_stats)

        def size_sort_key(item):
            try:
                return size_order.index(item['size__size'])
            except (ValueError, KeyError):
                return 999

        sizes_list.sort(key=size_sort_key)

        # Общая статистика
        total_stats = queryset.aggregate(
            total_products=Count('id'),
            total_with_size=Count('id', filter=models.Q(size__isnull=False)),
            total_without_size=Count('id', filter=models.Q(size__isnull=True)),
            total_stock=Sum('stock__quantity')
        )

        return Response({
            'filter': {'name': product_name} if product_name else None,
            'summary': total_stats,
            'by_size': sizes_list
        })

    def destroy(self, request, *args, **kwargs):
        """
        Мягкое удаление товара вместо физического удаления
        """
        instance = self.get_object()

        # Проверяем, используется ли товар в активных транзакциях
        from sales.models import TransactionItem, Transaction

        active_transactions = TransactionItem.objects.filter(
            product=instance,
            transaction__status__in=['pending', 'completed']
        ).exists()

        if active_transactions:
            # Делаем мягкое удаление
            instance.soft_delete()
            logger.info(f"Product {instance.name} soft deleted due to transaction history")

            return Response({
                'message': 'Товар помечен как удаленный (есть история продаж)',
                'action': 'soft_deleted',
                'product_id': instance.id,
                'can_restore': True
            }, status=status.HTTP_200_OK)
        else:
            # Если нет транзакций, можно удалить физически
            product_name = instance.name
            instance.delete()
            logger.info(f"Product {product_name} physically deleted (no transaction history)")

            return Response({
                'message': 'Товар полностью удален',
                'action': 'hard_deleted',
                'can_restore': False
            }, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """
        Восстановление мягко удаленного товара
        """
        # Получаем товар включая удаленные
        try:
            product = Product.all_objects.get(pk=pk, is_deleted=True)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Удаленный товар не найден'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Проверяем принадлежность к магазину
        current_store = self.get_current_store()
        if product.store != current_store:
            return Response(
                {'error': 'Товар не принадлежит вашему магазину'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Восстанавливаем
        product.restore()

        serializer = self.get_serializer(product)
        return Response({
            'message': 'Товар успешно восстановлен',
            'product': serializer.data
        })

    @action(detail=False, methods=['get'])
    def deleted(self, request):
        """
        Список удаленных товаров
        """
        current_store = self.get_current_store()
        if not current_store:
            return Response({'error': 'Магазин не определен'}, status=400)

        deleted_products = Product.all_objects.filter(
            store=current_store,
            is_deleted=True
        ).select_related('category')

        serializer = self.get_serializer(deleted_products, many=True)
        return Response({
            'deleted_products': serializer.data,
            'count': deleted_products.count()
        })

    @action(detail=True, methods=['delete'])
    def force_delete(self, request, pk=None):
        """
        Принудительное физическое удаление (только для админов)
        """
        # Проверяем права (только owner/admin)
        current_store = self.get_current_store()
        if not hasattr(request.user, 'store_role') or request.user.store_role not in ['owner', 'admin']:
            return Response(
                {'error': 'Недостаточно прав для принудительного удаления'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            product = Product.all_objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Товар не найден'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Проверяем принадлежность к магазину
        if product.store != current_store:
            return Response(
                {'error': 'Товар не принадлежит вашему магазину'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Получаем информацию о связанных объектах
        from sales.models import TransactionItem
        transaction_items = TransactionItem.objects.filter(product=product)

        if transaction_items.exists():
            return Response({
                'error': 'Нельзя удалить товар с историей продаж',
                'transaction_count': transaction_items.count(),
                'suggestion': 'Используйте мягкое удаление'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Удаляем физически
        product_name = product.name
        product.delete()

        logger.warning(f"Product {product_name} force deleted by {request.user.username}")

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'])
    def check_sizes(self, request):
        """
        Проверить наличие размеров для списка товаров

        Body:
            {
                "product_names": ["Футболка", "Джинсы", "Платье"]
            }

        Returns:
            Информация о размерах для каждого товара
        """
        product_names = request.data.get('product_names', [])

        if not product_names:
            return Response({})

        # Получаем текущий магазин
        current_store = self.get_current_store()
        if not current_store:
            return Response({
                'error': 'Магазин не определен'
            }, status=status.HTTP_400_BAD_REQUEST)

        result = {}

        for name in product_names:
            if not name or not name.strip():
                continue

            name = name.strip()

            # Находим товары с этим именем
            products = Product.objects.filter(
                store=current_store,
                name__icontains=name
            ).select_related('size', 'stock')

            if not products.exists():
                result[name] = {
                    'found': False,
                    'total_products': 0,
                    'sizes': []
                }
                continue

            # Собираем уникальные размеры
            sizes = set()
            total_stock = 0

            for product in products:
                if product.size:
                    sizes.add(product.size.size)
                if hasattr(product, 'stock'):
                    total_stock += product.stock.quantity

            # Сортируем размеры
            size_order = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
            sorted_sizes = sorted(
                list(sizes),
                key=lambda x: size_order.index(x) if x in size_order else 999
            )

            result[name] = {
                'found': True,
                'total_products': products.count(),
                'total_stock': total_stock,
                'available_sizes': sorted_sizes,
                'has_products_without_size': products.filter(size__isnull=True).exists()
            }

        return Response(result)


class ProductBatchViewSet(StoreViewSetMixin, ModelViewSet):
    """
    ViewSet для управления партиями товаров
    """
    serializer_class = ProductBatchSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductBatchFilter
    filterset_fields = ['product', 'supplier']
    search_fields = ['product__name', 'supplier']
    ordering_fields = ['created_at', 'expiration_date', 'quantity']
    ordering = ['expiration_date', 'created_at']

    def get_queryset(self):
        return ProductBatch.objects.select_related('product').all()

    @swagger_auto_schema(
        operation_description="Создать новую партию товара",
        request_body=ProductBatchSerializer,
        responses={201: ProductBatchSerializer}
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            batch = serializer.save()
            logger.info(f"Создана партия: {batch}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        """
        Партии с истекающим сроком годности
        """
        from datetime import date, timedelta

        days = int(request.query_params.get('days', 7))
        expiry_date = date.today() + timedelta(days=days)

        batches = self.get_queryset().filter(
            expiration_date__lte=expiry_date,
            expiration_date__isnull=False
        )

        serializer = self.get_serializer(batches, many=True)
        return Response({
            'batches': serializer.data,
            'count': batches.count(),
            'expiring_within_days': days
        })


class StockViewSet(StoreViewSetMixin, ModelViewSet):
    """
    ViewSet для управления остатками на складе
    """
    serializer_class = StockSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StockFilter
    search_fields = ['product__name', 'product__barcode']
    filterset_fields = ['product__category']
    ordering_fields = ['quantity', 'updated_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        return Stock.objects.select_related('product', 'product__category').all()

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Сводка по остаткам на складе
        """
        total_products = self.get_queryset().count()
        total_quantity = self.get_queryset().aggregate(
            total=Sum('quantity')
        )['total'] or 0

        low_stock_count = self.get_queryset().filter(quantity__lte=10).count()
        zero_stock_count = self.get_queryset().filter(quantity=0).count()

        return Response({
            'total_products': total_products,
            'total_quantity': total_quantity,
            'low_stock_products': low_stock_count,
            'out_of_stock_products': zero_stock_count
        })

    @action(detail=True, methods=['post'])
    def adjust(self, request, pk=None):
        """
        Корректировка остатков
        """
        stock = self.get_object()
        new_quantity = request.data.get('quantity')
        reason = request.data.get('reason', 'Корректировка')

        if new_quantity is None or new_quantity < 0:
            return Response(
                {'error': _('Некорректное количество')},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_quantity = stock.quantity
        stock.quantity = new_quantity
        stock.save()

        logger.info(
            f"Корректировка остатков {stock.product.name}: "
            f"{old_quantity} -> {new_quantity}. Причина: {reason}"
        )

        return Response({
            'message': _('Остатки скорректированы'),
            'old_quantity': old_quantity,
            'new_quantity': new_quantity,
            'reason': reason
        })




class SizeInfoViewSet(StoreViewSetMixin, ModelViewSet):
    """
    ViewSet для работы с размерной информацией конкретного магазина с поддержкой soft delete
    Поддерживает фильтрацию, поиск, сортировку и опциональную пагинацию
    """
    serializer_class = SizeInfoSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SizeInfoFilter
    search_fields = ['size']
    ordering_fields = ['size', 'chest', 'waist', 'length']
    ordering = ['size']
    pagination_class = SizeInfoPagination

    def get_current_store_safely(self):
        """Безопасное получение текущего магазина"""
        try:
            current_store = self.get_current_store()
            if not current_store:
                logger.warning(f"Не найден текущий магазин для пользователя {self.request.user.username}")
            return current_store
        except Exception as e:
            logger.error(f"Ошибка получения текущего магазина: {e}")
            return None

    def get_queryset(self):
        """
        Возвращает queryset АКТИВНЫХ размеров только для текущего магазина
        """
        current_store = self.get_current_store_safely()
        if current_store:
            logger.info(f"Получение активных размеров для магазина: {current_store.name}")
            # objects manager уже фильтрует по deleted_at__isnull=True
            return SizeInfo.objects.filter(store=current_store).select_related('store')

        logger.warning("Текущий магазин не найден, возвращаем пустой queryset")
        return SizeInfo.objects.none()

    @swagger_auto_schema(
        operation_description="Получить список размерной информации текущего магазина. Если не указаны параметры limit/offset - возвращает все записи без пагинации.",
        manual_parameters=[
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description="[ОПЦИОНАЛЬНО] Количество записей на странице (по умолчанию 20, максимум 100). Если не указан - возвращает все записи.",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'offset',
                openapi.IN_QUERY,
                description="[ОПЦИОНАЛЬНО] Смещение от начала списка. Работает только вместе с limit.",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'size',
                openapi.IN_QUERY,
                description="Фильтр по размеру (можно указать несколько через запятую)",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'chest_min',
                openapi.IN_QUERY,
                description="Минимальный обхват груди",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'chest_max',
                openapi.IN_QUERY,
                description="Максимальный обхват груди",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'waist_min',
                openapi.IN_QUERY,
                description="Минимальный обхват талии",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'waist_max',
                openapi.IN_QUERY,
                description="Максимальный обхват талии",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'length_min',
                openapi.IN_QUERY,
                description="Минимальная длина",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'length_max',
                openapi.IN_QUERY,
                description="Максимальная длина",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description="Поиск по размеру",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'ordering',
                openapi.IN_QUERY,
                description="Сортировка (size, chest, waist, length). Для убывания добавьте '-'",
                type=openapi.TYPE_STRING
            ),
        ],
        responses={200: SizeInfoSerializer(many=True)}
    )
    def get_queryset(self):
        """
        Возвращает queryset АКТИВНЫХ размеров только для текущего магазина
        """
        current_store = self.get_current_store_safely()
        if current_store:
            logger.info(f"Получение активных размеров для магазина: {current_store.name}")
            # objects manager уже фильтрует по deleted_at__isnull=True
            return SizeInfo.objects.filter(store=current_store).select_related('store')

        logger.warning("Текущий магазин не найден, возвращаем пустой queryset")
        return SizeInfo.objects.none()

    @swagger_auto_schema(
        operation_description="Получить список активной размерной информации текущего магазина. Если не указаны параметры limit/offset - возвращает все записи без пагинации.",
        manual_parameters=[
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description="[ОПЦИОНАЛЬНО] Количество записей на странице (по умолчанию 20, максимум 100). Если не указан - возвращает все записи.",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'offset',
                openapi.IN_QUERY,
                description="[ОПЦИОНАЛЬНО] Смещение от начала списка. Работает только вместе с limit.",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            # ... остальные параметры остаются те же
        ],
        responses={200: SizeInfoSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        """Получить список АКТИВНОЙ размерной информации текущего магазина"""
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин не найден',
                'detail': 'Пользователь должен быть связан с активным магазином',
                'count': 0,
                'results': []
            }, status=status.HTTP_400_BAD_REQUEST)

        queryset = self.filter_queryset(self.get_queryset())

        logger.info(f"SizeInfo list request для магазина {current_store.name} - query_params: {dict(request.query_params)}")
        logger.info(f"Найдено активных размеров: {queryset.count()}")

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)

            if 'store_info' not in response.data:
                response.data['store_info'] = {
                    'id': str(current_store.id),
                    'name': current_store.name
                }

            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'store_info': {
                'id': str(current_store.id),
                'name': current_store.name
            },
            'results': serializer.data
        })

    @action(detail=False, methods=['get'])
    def deleted(self, request):
        """Получить список удаленных размеров"""
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин недоступен'
            }, status=status.HTTP_400_BAD_REQUEST)

        deleted_sizes = SizeInfo.all_objects.filter(
            store=current_store,
            deleted_at__isnull=False
        ).order_by('-deleted_at')

        serializer = self.get_serializer(deleted_sizes, many=True)
        return Response({
            'results': serializer.data,
            'count': deleted_sizes.count()
        })

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Восстановить удаленный размер"""
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин недоступен'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Ищем среди всех объектов (включая удаленные)
            size_info = SizeInfo.all_objects.get(
                pk=pk,
                store=current_store,
                deleted_at__isnull=False
            )
        except SizeInfo.DoesNotExist:
            return Response({
                'error': 'Удаленный размер не найден'
            }, status=status.HTTP_404_NOT_FOUND)

        # Проверяем, нет ли уже активного размера с таким названием
        if SizeInfo.objects.filter(
            store=current_store,
            size=size_info.size
        ).exists():
            return Response({
                'error': f'Размер "{size_info.size}" уже существует. Удалите его сначала или переименуйте.'
            }, status=status.HTTP_400_BAD_REQUEST)

        size_info.restore()
        logger.info(f"Восстановлен размер '{size_info.size}' в магазине '{current_store.name}'")

        serializer = self.get_serializer(size_info)
        return Response({
            'message': f'Размер "{size_info.size}" успешно восстановлен',
            'size_info': serializer.data
        })

    @action(detail=True, methods=['delete'])
    def hard_delete(self, request, pk=None):
        """Окончательное удаление размера из БД (только для админов)"""
        if not request.user.is_staff:
            return Response({
                'error': 'Недостаточно прав для окончательного удаления'
            }, status=status.HTTP_403_FORBIDDEN)

        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин недоступен'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            size_info = SizeInfo.all_objects.get(pk=pk, store=current_store)
        except SizeInfo.DoesNotExist:
            return Response({
                'error': 'Размер не найден'
            }, status=status.HTTP_404_NOT_FOUND)

        size_name = size_info.size
        size_info.hard_delete()
        logger.warning(f"ОКОНЧАТЕЛЬНО удален размер '{size_name}' из магазина '{current_store.name}' пользователем {request.user.username}")

        return Response({
            'message': f'Размер "{size_name}" окончательно удален'
        })

    @swagger_auto_schema(
        operation_description="Создать новую размерную информацию для текущего магазина",
        request_body=SizeInfoSerializer,
        responses={
            201: SizeInfoSerializer,
            400: 'Ошибка валидации'
        }
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Создание новой размерной информации для текущего магазина"""
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин не найден',
                'detail': 'Невозможно создать размер без активного магазина'
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            # Автоматически привязываем к текущему магазину
            size_info = serializer.save(store=current_store)
            logger.info(f"Создана размерная информация: {size_info.size} для магазина {current_store.name}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        logger.warning(f"Ошибка валидации при создании размерной информации: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Обновить размерную информацию текущего магазина",
        request_body=SizeInfoSerializer,
        responses={
            200: SizeInfoSerializer,
            400: 'Ошибка валидации',
            404: 'Размерная информация не найдена'
        }
    )
    def update(self, request, *args, **kwargs):
        """Обновление размерной информации текущего магазина"""
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин не найден'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            instance = self.get_object()

            # Проверяем, что размер принадлежит текущему магазину
            if instance.store != current_store:
                logger.warning(f"Попытка изменить размер {instance.size} не своего магазина")
                return Response({
                    'error': 'Размер не принадлежит текущему магазину'
                }, status=status.HTTP_403_FORBIDDEN)

            # Проверяем, что размер не удален
            if instance.is_deleted:
                return Response({
                    'error': 'Нельзя редактировать удаленный размер'
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Ошибка получения размера для обновления: {e}")
            return Response({
                'error': 'Размер не найден'
            }, status=status.HTTP_404_NOT_FOUND)

        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            size_info = serializer.save()
            logger.info(f"Обновлена размерная информация: {size_info.size} для магазина {current_store.name}")
            return Response(serializer.data)

        logger.warning(f"Ошибка валидации при обновлении размерной информации: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        """Мягкое удаление размерной информации текущего магазина"""
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({
                'error': 'Текущий магазин не найден'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            instance = self.get_object()

            # Проверяем, что размер принадлежит текущему магазину
            if instance.store != current_store:
                logger.warning(f"Попытка удалить размер {instance.size} не своего магазина")
                return Response({
                    'error': 'Размер не принадлежит текущему магазину'
                }, status=status.HTTP_403_FORBIDDEN)

            # Проверяем, что размер еще не удален
            if instance.is_deleted:
                return Response({
                    'error': 'Размер уже удален'
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Ошибка получения размера для удаления: {e}")
            return Response({
                'error': 'Размер не найден'
            }, status=status.HTTP_404_NOT_FOUND)

        # ✅ ИЗМЕНЕНИЕ: Убираем проверку на использование в товарах при soft delete
        # При мягком удалении можно удалить размер даже если он используется
        # Это не нарушит целостность данных, так как размер останется в БД

        size_name = instance.size
        store_name = current_store.name

        # Используем soft delete
        instance.delete()  # Наш кастомный метод delete()

        logger.info(f"Мягко удалена размерная информация: {size_name} из магазина {store_name}")

        return Response({
            'message': f'Размер "{size_name}" перемещен в удаленные'
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def debug_info(self, request):
        """Упрощенный endpoint отладки с информацией о удаленных размерах"""
        if not settings.DEBUG:
            return Response({
                'error': 'Endpoint отладки доступен только в режиме разработки'
            }, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff:
            return Response({
                'error': 'Недостаточно прав доступа'
            }, status=status.HTTP_403_FORBIDDEN)

        current_store = self.get_current_store_safely()

        debug_info = {
            'user_info': {
                'username': request.user.username,
                'user_id': request.user.id,
                'is_authenticated': request.user.is_authenticated,
                'is_staff': request.user.is_staff,
            },
            'store_info': {
                'has_current_store': current_store is not None,
                'store_id': str(current_store.id) if current_store else None,
                'store_name': current_store.name if current_store else None,
            },
            'sizes_info': {
                'active_count': 0,
                'deleted_count': 0,
                'total_count': 0,
            }
        }

        if current_store:
            try:
                active_sizes = SizeInfo.objects.filter(store=current_store)
                deleted_sizes = SizeInfo.all_objects.filter(store=current_store, deleted_at__isnull=False)
                total_sizes = SizeInfo.all_objects.filter(store=current_store)

                debug_info['sizes_info'].update({
                    'active_count': active_sizes.count(),
                    'deleted_count': deleted_sizes.count(),
                    'total_count': total_sizes.count(),
                    'active_sizes': [
                        {
                            'id': size.id,
                            'size': size.size,
                            'chest': size.chest,
                            'waist': size.waist,
                            'length': size.length
                        }
                        for size in active_sizes[:5]
                    ],
                    'deleted_sizes': [
                        {
                            'id': size.id,
                            'size': size.size,
                            'deleted_at': size.deleted_at.isoformat() if size.deleted_at else None
                        }
                        for size in deleted_sizes[:5]
                    ]
                })
            except Exception as e:
                debug_info['sizes_info']['error'] = str(e)

        return Response(debug_info)

    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """
        Получить размеры сгруппированные по категориям использования
        """
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({'error': 'Текущий магазин недоступен'}, status=400)

        # Группируем размеры по первому слову в description или size
        sizes = SizeInfo.objects.filter(store=current_store)
        categories = {}

        for size in sizes:
            # Определяем категорию по description или размеру
            category_key = 'Общее'
            
            if size.description:
                first_word = size.description.split()[0].lower()
                if 'труб' in first_word:
                    category_key = 'Трубы'
                elif 'фитинг' in first_word:
                    category_key = 'Фитинги'
                elif 'кабел' in first_word:
                    category_key = 'Кабели'
                elif 'профил' in first_word:
                    category_key = 'Профили'
            
            if category_key not in categories:
                categories[category_key] = []
            
            categories[category_key].append({
                'id': size.id,
                'size': size.size,
                'dimension1': float(size.dimension1) if size.dimension1 else None,
                'dimension2': float(size.dimension2) if size.dimension2 else None,
                'dimension3': float(size.dimension3) if size.dimension3 else None,
                'dimension1_label': size.dimension1_label,
                'dimension2_label': size.dimension2_label,
                'dimension3_label': size.dimension3_label,
                'description': size.description,
                'full_description': size.full_description
            })

        return Response({
            'store': {
                'id': str(current_store.id),
                'name': current_store.name
            },
            'categories': categories,
            'total_sizes': sizes.count()
        })

    @action(detail=False, methods=['post'])
    def import_standard_sizes(self, request):
        """
        Импорт стандартных размеров для сантехники/стройматериалов
        """
        current_store = self.get_current_store_safely()
        if not current_store:
            return Response({'error': 'Текущий магазин недоступен'}, status=400)

        # Проверяем права
        if not hasattr(request.user, 'store_role') or request.user.store_role not in ['owner', 'admin']:
            return Response({
                'error': 'Недостаточно прав для импорта стандартных размеров'
            }, status=403)

        size_type = request.data.get('type', 'pipes')
        
        standard_sizes = []
        
        if size_type == 'pipes':
            # Стандартные размеры труб
            pipe_sizes = [
                ('1/2"', 15, 20, 2.5, 'Труба полипропиленовая'),
                ('3/4"', 20, 25, 2.5, 'Труба полипропиленовая'),
                ('1"', 25, 32, 3.5, 'Труба полипропиленовая'),
                ('1 1/4"', 32, 40, 4.0, 'Труба полипропиленовая'),
                ('1 1/2"', 40, 50, 5.0, 'Труба полипропиленовая'),
                ('2"', 50, 63, 6.5, 'Труба полипропиленовая'),
                ('2 1/2"', 63, 75, 6.0, 'Труба полипропиленовая'),
                ('3"', 75, 90, 7.5, 'Труба полипропиленовая'),
                ('4"', 90, 110, 10.0, 'Труба полипропиленовая'),
            ]
            
            for size_name, inner_d, outer_d, wall_thickness, desc in pipe_sizes:
                standard_sizes.append({
                    'size': size_name,
                    'dimension1': inner_d,
                    'dimension2': outer_d,
                    'dimension3': wall_thickness,
                    'dimension1_label': 'Внутр. диаметр (мм)',
                    'dimension2_label': 'Внешн. диаметр (мм)',
                    'dimension3_label': 'Толщина стенки (мм)',
                    'description': desc
                })
        
        elif size_type == 'cables':
            # Стандартные сечения кабелей
            cable_sizes = [
                ('1.5', 1.5, None, None, 'Кабель ВВГ'),
                ('2.5', 2.5, None, None, 'Кабель ВВГ'),
                ('4', 4.0, None, None, 'Кабель ВВГ'),
                ('6', 6.0, None, None, 'Кабель ВВГ'),
                ('10', 10.0, None, None, 'Кабель ВВГ'),
                ('16', 16.0, None, None, 'Кабель ВВГ'),
                ('25', 25.0, None, None, 'Кабель ВВГ'),
                ('35', 35.0, None, None, 'Кабель ВВГ'),
                ('50', 50.0, None, None, 'Кабель ВВГ'),
            ]
            
            for size_name, section, _, __, desc in cable_sizes:
                standard_sizes.append({
                    'size': f'{size_name} кв.мм',
                    'dimension1': section,
                    'dimension2': None,
                    'dimension3': None,
                    'dimension1_label': 'Сечение (кв.мм)',
                    'dimension2_label': 'Количество жил',
                    'dimension3_label': 'Диаметр (мм)',
                    'description': desc
                })

        # Импортируем размеры
        created_count = 0
        skipped_count = 0
        errors = []

        for size_data in standard_sizes:
            try:
                # Проверяем существование
                if SizeInfo.objects.filter(
                    store=current_store,
                    size=size_data['size']
                ).exists():
                    skipped_count += 1
                    continue

                # Создаем размер
                SizeInfo.objects.create(
                    store=current_store,
                    **size_data
                )
                created_count += 1

            except Exception as e:
                errors.append({
                    'size': size_data['size'],
                    'error': str(e)
                })

        return Response({
            'message': f'Импорт завершен. Создано: {created_count}, пропущено: {skipped_count}',
            'summary': {
                'created': created_count,
                'skipped': skipped_count,
                'errors': len(errors)
            },
            'errors': errors,
            'type': size_type
        })


# Дополнительные утилитные views для конкретного магазина

class InventoryStatsView(StoreViewSetMixin, generics.GenericAPIView):
    """
    Общая статистика по складу конкретного магазина
    """

    @swagger_auto_schema(
        operation_description="Получить общую статистику по складу текущего магазина",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'store_info': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_STRING),
                            'name': openapi.Schema(type=openapi.TYPE_STRING),
                        }
                    ),
                    'total_products': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'total_categories': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'total_stock_value': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'low_stock_alerts': openapi.Schema(type=openapi.TYPE_INTEGER),
                }
            )
        }
    )
    def get(self, request):
        try:
            current_store = self.get_current_store()
            if not current_store:
                return Response({
                    'error': 'Текущий магазин не найден'
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Ошибка получения текущего магазина: {e}")
            return Response({
                'error': 'Ошибка получения магазина'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Фильтруем статистику по текущему магазину
        stats = {
            'store_info': {
                'id': str(current_store.id),
                'name': current_store.name
            },
            'total_products': Product.objects.filter(store=current_store).count(),
            'total_categories': ProductCategory.objects.filter(store=current_store).count(),
            'total_size_info': SizeInfo.objects.filter(store=current_store).count(),
            'total_stock_quantity': Stock.objects.filter(
                product__store=current_store
            ).aggregate(total=Sum('quantity'))['total'] or 0,
            'low_stock_alerts': Stock.objects.filter(
                product__store=current_store,
                quantity__lte=10
            ).count(),
            'out_of_stock': Stock.objects.filter(
                product__store=current_store,
                quantity=0
            ).count(),
            'total_batches': ProductBatch.objects.filter(
                product__store=current_store
            ).count(),
        }

        # Подсчет общей стоимости склада для текущего магазина
        total_value = ProductBatch.objects.filter(
            product__store=current_store
        ).aggregate(
            total=Sum(F('quantity') * F('purchase_price'))
        )['total'] or 0
        stats['total_stock_value'] = float(total_value)

        logger.info(f"Получена статистика для магазина {current_store.name}")
        return Response(stats)


from django.http import FileResponse, HttpResponseNotFound
from django.views.decorators.csrf import csrf_exempt
import os

from .models import Product
from django.conf import settings

@csrf_exempt
def product_label_proxy(request, pk):
    """
    Отдаёт картинку товара через прокси с CORS-заголовками
    """
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return HttpResponseNotFound("Product not found")

    if not product.image_label:
        return HttpResponseNotFound("Image not found")

    file_path = os.path.join(settings.MEDIA_ROOT, str(product.image_label))

    if not os.path.exists(file_path):
        return HttpResponseNotFound("File not found")

    response = FileResponse(open(file_path, "rb"), content_type="image/png")
    response["Access-Control-Allow-Origin"] = "*"   # 🔑 главное!
    return response