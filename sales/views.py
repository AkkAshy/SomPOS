from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from django.db.models import Sum, F, FloatField, DecimalField, Value, Q  # ← ДОБАВИТЬ Q
from rest_framework import pagination
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from django.db.models.functions import Coalesce
from drf_yasg import openapi
from .models import Transaction, TransactionHistory, TransactionItem
from .serializers import TransactionSerializer, FilteredTransactionHistorySerializer, TransactionItemSerializer, CashierAggregateSerializer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.utils.translation import gettext_lazy as _
from customers.views import FlexiblePagination
from .pagination import OptionalPagination
import logging
from stores.mixins import StoreViewSetMixin

logger = logging.getLogger(__name__)

class IsCashierOrManagerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name__in=['admin', 'manager', 'cashier']).exists()

class TransactionViewSet(StoreViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet для управления транзакциями с автоматической привязкой к магазину
    """
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsCashierOrManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['created_at', 'total_amount', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Возвращает транзакции только текущего магазина
        """
        # Базовый queryset
        queryset = Transaction.objects.select_related(
            'customer',
            'cashier',
            'store'
        ).prefetch_related(
            'items',
            'items__product'
        )

        # Применяем фильтрацию по магазину из миксина
        # Миксин сам отфильтрует по текущему магазину
        return super().get_queryset()

    @swagger_auto_schema(
        operation_description="Получить список продаж текущего магазина",
        manual_parameters=[
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                description="Фильтр по статусу (completed, pending, refunded)",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'payment_method',
                openapi.IN_QUERY,
                description="Фильтр по способу оплаты (cash, transfer, card, debt)",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'customer',
                openapi.IN_QUERY,
                description="ID покупателя",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'date_from',
                openapi.IN_QUERY,
                description="Дата начала периода (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE
            ),
            openapi.Parameter(
                'date_to',
                openapi.IN_QUERY,
                description="Дата окончания периода (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE
            ),
        ],
        responses={200: TransactionSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Дополнительные фильтры
        status = request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        payment_method = request.query_params.get('payment_method')
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)

        customer_id = request.query_params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        date_from = request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        # Пагинация
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="""
        Создать новую продажу в текущем магазине.
        Магазин определяется автоматически из JWT токена.
        Для оплаты в долг укажите customer_id или new_customer с full_name и phone.
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['items', 'payment_method'],
            properties={
                'payment_method': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=['cash', 'transfer', 'card', 'debt'],
                    description='Способ оплаты'
                ),
                'customer': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='ID существующего покупателя'
                ),
                'new_customer': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                        'phone': openapi.Schema(type=openapi.TYPE_STRING)
                    },
                    description='Данные нового покупателя'
                ),
                'items': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=['product_id', 'quantity'],
                        properties={
                            'product_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'price': openapi.Schema(
                                type=openapi.TYPE_NUMBER,
                                description='Цена (опционально, по умолчанию из товара)'
                            )
                        }
                    )
                )
            }
        ),
        responses={
            201: TransactionSerializer(),
            400: "Ошибка валидации",
            403: "Нет доступа к магазину"
        }
    )
    def create(self, request, *args, **kwargs):
        # Проверяем наличие магазина
        current_store = self.get_current_store()
        if not current_store:
            logger.error(f"No store found for user {request.user.username} when creating transaction")
            return Response(
                {
                    'error': 'Магазин не определен. Проверьте JWT токен.',
                    'details': 'Store ID должен быть в JWT токене'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        logger.info(f"Creating transaction for store: {current_store.name} by user: {request.user.username}")

        # Добавляем контекст с текущим магазином
        serializer = self.get_serializer(
            data=request.data,
            context={
                'request': request,
                'store': current_store  # Передаем магазин в контекст
            }
        )
        serializer.is_valid(raise_exception=True)

        # perform_create установит store и cashier
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        """
        Переопределяем для правильной установки store и cashier
        ВАЖНО: НЕ вызываем super().perform_create() чтобы избежать конфликта
        """
        # Получаем текущий магазин
        current_store = self.get_current_store()

        if not current_store:
            raise serializers.ValidationError({
                'error': 'Магазин не определен. Проверьте JWT токен.'
            })

        # Передаем store и cashier через save()
        # Сериализатор получит их в validated_data
        serializer.save(
            store=current_store,
            cashier=self.request.user
        )

        logger.info(f"Transaction created by {self.request.user.username} in store {current_store.name}")

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """
        Возврат транзакции
        """
        transaction = self.get_object()

        if transaction.status != 'completed':
            return Response(
                {'error': 'Можно вернуть только завершенные транзакции'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Возвращаем товары на склад
        for item in transaction.items.all():
            # Находим или создаем партию для возврата
            from inventory.models import ProductBatch
            batch, created = ProductBatch.objects.get_or_create(
                product=item.product,
                store=transaction.store,
                defaults={
                    'quantity': 0,
                    'purchase_price': item.price,
                    'supplier': 'Возврат'
                }
            )
            batch.quantity += item.quantity
            batch.save()

            # Обновляем stock
            item.product.stock.update_quantity()

        # Обновляем долг покупателя если была оплата в долг
        if transaction.payment_method == 'debt' and transaction.customer:
            transaction.customer.debt = max(0, transaction.customer.debt - transaction.total_amount)
            transaction.customer.save()

        # Меняем статус
        transaction.status = 'refunded'
        transaction.save()

        logger.info(f"Transaction #{transaction.id} refunded by {request.user.username}")

        serializer = self.get_serializer(transaction)
        return Response({
            'message': 'Транзакция успешно возвращена',
            'transaction': serializer.data
        })

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Статистика продаж текущего магазина
        """
        current_store = self.get_current_store()
        if not current_store:
            return Response(
                {'error': 'Магазин не определен'},
                status=status.HTTP_403_FORBIDDEN
            )

        from django.db.models import Sum, Count, Avg
        from django.utils import timezone
        from datetime import timedelta

        # Базовый queryset для текущего магазина
        queryset = Transaction.objects.filter(
            store=current_store,
            status='completed'
        )

        # Статистика за сегодня
        today = timezone.now().date()
        today_stats = queryset.filter(
            created_at__date=today
        ).aggregate(
            total=Sum('total_amount'),
            count=Count('id'),
            avg=Avg('total_amount')
        )

        # Статистика за неделю
        week_ago = today - timedelta(days=7)
        week_stats = queryset.filter(
            created_at__date__gte=week_ago
        ).aggregate(
            total=Sum('total_amount'),
            count=Count('id'),
            avg=Avg('total_amount')
        )

        # Статистика за месяц
        month_ago = today - timedelta(days=30)
        month_stats = queryset.filter(
            created_at__date__gte=month_ago
        ).aggregate(
            total=Sum('total_amount'),
            count=Count('id'),
            avg=Avg('total_amount')
        )

        # Топ товары
        from django.db.models import F
        top_products = TransactionItem.objects.filter(
            transaction__store=current_store,
            transaction__status='completed'
        ).values(
            'product__name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('price'))
        ).order_by('-total_quantity')[:10]

        return Response({
            'store': {
                'id': str(current_store.id),
                'name': current_store.name
            },
            'today': {
                'total': float(today_stats['total'] or 0),
                'count': today_stats['count'] or 0,
                'avg': float(today_stats['avg'] or 0)
            },
            'week': {
                'total': float(week_stats['total'] or 0),
                'count': week_stats['count'] or 0,
                'avg': float(week_stats['avg'] or 0)
            },
            'month': {
                'total': float(month_stats['total'] or 0),
                'count': month_stats['count'] or 0,
                'avg': float(month_stats['avg'] or 0)
            },
            'top_products': list(top_products)
        })

    @action(detail=False, methods=['get'])
    def today_sales(self, request):
        """
        Продажи за сегодня
        """
        current_store = self.get_current_store()
        if not current_store:
            return Response(
                {'error': 'Магазин не определен'},
                status=status.HTTP_403_FORBIDDEN
            )

        from django.utils import timezone

        today = timezone.now().date()
        transactions = Transaction.objects.filter(
            store=current_store,
            created_at__date=today
        ).select_related('customer', 'cashier').prefetch_related('items__product')

        serializer = self.get_serializer(transactions, many=True)

        from django.db.models import Sum
        total = transactions.filter(status='completed').aggregate(
            total=Sum('total_amount')
        )['total'] or 0

        return Response({
            'date': today.isoformat(),
            'total': float(total),
            'count': transactions.count(),
            'transactions': serializer.data
        })




# sales/views.py - ИСПРАВЛЕННАЯ ВЕРСИЯ TransactionHistoryListView

class TransactionHistoryListView(StoreViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для просмотра истории транзакций без автоматического пагинатора
    Ручная обработка limit/offset с правильным подсчетом записей
    """
    # ✅ ДОБАВЛЯЕМ БАЗОВЫЙ QUERYSET - это обязательно для ViewSet
    queryset = TransactionHistory.objects.all()

    # БЕЗ pagination_class - убираем пагинатор!
    lookup_field = 'id'
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['created_at', 'id']
    ordering = ['-created_at']
    permission_classes = [IsAuthenticated]
    filterset_fields = ['transaction']

    def get_queryset(self):
        """Базовый queryset с фильтрацией по магазину"""
        # ✅ ИСПРАВЛЕНО: Сначала применяем фильтр магазина из миксина
        queryset = super().get_queryset()

        # Затем существующая фильтрация
        queryset = queryset.filter(
            action__in=['completed', 'refunded']
        ).exclude(
            Q(details__isnull=True) | Q(details='') | Q(details='{}')
        ).select_related(
            'transaction',
            'transaction__customer',
            'transaction__cashier'
        ).prefetch_related(
            'transaction__items__product'
        )

        # Дополнительные фильтры из параметров запроса
        transaction_id = self.request.query_params.get('transaction_id')
        product_id = self.request.query_params.get('product')
        customer_id = self.request.query_params.get('customer')
        cashier_id = self.request.query_params.get('cashier')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if transaction_id:
            try:
                queryset = queryset.filter(transaction__id=int(transaction_id))
            except ValueError:
                queryset = queryset.none()

        if customer_id:
            try:
                queryset = queryset.filter(transaction__customer__id=int(customer_id))
            except ValueError:
                queryset = queryset.none()

        if cashier_id:
            try:
                queryset = queryset.filter(transaction__cashier__id=int(cashier_id))
            except ValueError:
                queryset = queryset.none()

        if product_id:
            try:
                queryset = queryset.filter(
                    transaction__items__product__id=int(product_id)
                ).distinct()
            except ValueError:
                queryset = queryset.none()

        if date_from:
            try:
                from datetime import datetime
                datetime.strptime(date_from, '%Y-%m-%d')
                queryset = queryset.filter(created_at__date__gte=date_from)
            except ValueError:
                pass

        if date_to:
            try:
                from datetime import datetime
                datetime.strptime(date_to, '%Y-%m-%d')
                queryset = queryset.filter(created_at__date__lte=date_to)
            except ValueError:
                pass

        return queryset

    def get_serializer_class(self):
        return FilteredTransactionHistorySerializer

    @swagger_auto_schema(
        operation_description="Получить историю транзакций с ручной обработкой пагинации",
        manual_parameters=[
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description="Количество записей для показа (по умолчанию все)",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'offset',
                openapi.IN_QUERY,
                description="Смещение от начала списка (по умолчанию 0)",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'transaction_id',
                openapi.IN_QUERY,
                description="Фильтр по ID транзакции",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'product',
                openapi.IN_QUERY,
                description="Фильтр по ID продукта",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'customer',
                openapi.IN_QUERY,
                description="Фильтр по ID покупателя",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'cashier',
                openapi.IN_QUERY,
                description="Фильтр по ID кассира",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'date_from',
                openapi.IN_QUERY,
                description="Дата начала периода (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE
            ),
            openapi.Parameter(
                'date_to',
                openapi.IN_QUERY,
                description="Дата окончания периода (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE
            ),
            openapi.Parameter(
                'ordering',
                openapi.IN_QUERY,
                description="Сортировка: 'created_at', '-created_at', 'id', '-id'",
                type=openapi.TYPE_STRING
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        """
        Ручная обработка пагинации без пагинатора
        """
        # Получаем параметры limit и offset
        limit = request.query_params.get('limit')
        offset = request.query_params.get('offset', 0)

        # Валидация параметров
        try:
            limit = int(limit) if limit else None
            offset = int(offset)
        except (ValueError, TypeError):
            limit = None
            offset = 0

        # Убеждаемся что offset не отрицательный
        if offset < 0:
            offset = 0

        # Ограничиваем максимальный limit
        if limit and limit > 1000:
            limit = 1000

        # Получаем базовый queryset
        queryset = self.filter_queryset(self.get_queryset())

        # ВАЖНО: Считаем общее количество записей ДО применения limit/offset
        total_count = queryset.count()

        # Применяем offset и limit
        if limit:
            paginated_queryset = queryset[offset:offset + limit]
        else:
            paginated_queryset = queryset[offset:]

        # Сериализуем
        serializer = self.get_serializer(paginated_queryset, many=True)

        # Фильтруем None значения (если они есть)
        original_data = serializer.data
        valid_data = [item for item in original_data if item is not None]

        # ✅ ДОБАВЛЯЕМ ИНФОРМАЦИЮ О ТЕКУЩЕМ МАГАЗИНЕ
        current_store = self.get_current_store()
        store_info = None
        if current_store:
            store_info = {
                'id': str(current_store.id),
                'name': current_store.name
            }

        # Логирование
        logger.info(f"TransactionHistory list: store={store_info['name'] if store_info else 'None'}, "
                   f"total_count={total_count}, limit={limit}, offset={offset}, "
                   f"returned={len(valid_data)}, filtered_out={len(original_data) - len(valid_data)}")

        # Формируем ответ
        response_data = {
            'store': store_info,  # ✅ Информация о текущем магазине
            'count': total_count,  # Общее количество записей в БД (с учетом фильтров)
            'results': valid_data  # Записи для текущей страницы
        }

        # Добавляем информацию о пагинации если параметры были переданы
        if limit or offset > 0:
            response_data.update({
                'limit': limit,
                'offset': offset,
                'returned_count': len(valid_data),  # Фактически возвращено записей
                'has_more': (offset + len(valid_data)) < total_count  # Есть ли ещё записи
            })

        return Response(response_data)

    @swagger_auto_schema(
        operation_description="Получить конкретную запись истории транзакции",
        responses={
            200: FilteredTransactionHistorySerializer,
            404: 'Запись не найдена'
        }
    )
    def retrieve(self, request, *args, **kwargs):
        """
        Получить одну запись по ID
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        # Проверяем что данные валидны
        if serializer.data is None:
            return Response(
                {'detail': 'Запись содержит неполные данные'},
                status=404
            )

        return Response(serializer.data)


# Альтернативная версия с дополнительной информацией
class DetailedTransactionHistoryListView(viewsets.ReadOnlyModelViewSet):
    """
    Версия с более подробной информацией в ответе
    """
    lookup_field = 'id'
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['created_at', 'id']
    ordering = ['-created_at']
    permission_classes = [IsAuthenticated]
    filterset_fields = ['transaction']

    def get_queryset(self):
        # Такой же как выше
        return TransactionHistory.objects.filter(
            action__in=['completed', 'refunded']
        ).exclude(
            Q(details__isnull=True) | Q(details='') | Q(details='{}')
        ).select_related(
            'transaction',
            'transaction__customer',
            'transaction__cashier'
        ).prefetch_related(
            'transaction__items__product'
        )

    def get_serializer_class(self):
        return FilteredTransactionHistorySerializer

    def list(self, request, *args, **kwargs):
        """
        Детальная версия с дополнительной навигационной информацией
        """
        # Параметры пагинации
        limit = request.query_params.get('limit')
        offset = request.query_params.get('offset', 0)

        try:
            limit = int(limit) if limit else None
            offset = int(offset)
        except (ValueError, TypeError):
            limit = None
            offset = 0

        if offset < 0:
            offset = 0
        if limit and limit > 1000:
            limit = 1000

        # Получаем данные
        queryset = self.filter_queryset(self.get_queryset())
        total_count = queryset.count()

        # Применяем пагинацию
        if limit:
            paginated_queryset = queryset[offset:offset + limit]
        else:
            paginated_queryset = queryset[offset:]

        # Сериализация
        serializer = self.get_serializer(paginated_queryset, many=True)
        valid_data = [item for item in serializer.data if item is not None]

        # Вычисляем навигационную информацию
        returned_count = len(valid_data)
        has_more = (offset + returned_count) < total_count
        has_previous = offset > 0

        # Подсчитываем примерные номера страниц (если есть limit)
        current_page = None
        total_pages = None
        if limit and limit > 0:
            current_page = (offset // limit) + 1
            total_pages = (total_count + limit - 1) // limit

        response_data = {
            # Основные данные
            'count': total_count,
            'results': valid_data,

            # Параметры запроса
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned_count': returned_count,
            },

            # Навигация
            'navigation': {
                'has_more': has_more,
                'has_previous': has_previous,
                'current_page': current_page,
                'total_pages': total_pages,
            },

            # Дополнительная информация
            'meta': {
                'query_params': dict(request.query_params),
                'total_filtered': total_count,  # После применения фильтров
            }
        }

        return Response(response_data)



from django.db.models import IntegerField, DecimalField, ExpressionWrapper
from django.utils.dateparse import parse_date
from django.db.models import Q

class CashierSalesSummaryView(APIView):
    pagination_class = pagination.PageNumberPagination

    def get(self, request):
        cashier_id = request.query_params.get('cashier_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        # Базовый queryset
        queryset = TransactionItem.objects.all()

        # Фильтрация по кассиру
        if cashier_id:
            queryset = queryset.filter(transaction__cashier_id=cashier_id)

        # Фильтрация по дате
        if start_date:
            queryset = queryset.filter(transaction__created_at__date__gte=parse_date(start_date))
        if end_date:
            queryset = queryset.filter(transaction__created_at__date__lte=parse_date(end_date))

        # Агрегация
        queryset = queryset.values(
            'transaction__cashier_id',
            'transaction__cashier__username'
        ).annotate(
            total_quantity=Coalesce(Sum('quantity'), 0, output_field=IntegerField()),
            total_amount=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F('quantity') * F('price'),
                        output_field=DecimalField(max_digits=12, decimal_places=2)
                    )
                ),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )

        data = [
            {
                'cashier_id': entry['transaction__cashier_id'],
                'cashier_name': entry['transaction__cashier__username'],
                'total_quantity': entry['total_quantity'],
                'total_amount': entry['total_amount']
            }
            for entry in queryset if entry['transaction__cashier_id'] is not None
        ]

        serializer = CashierAggregateSerializer(data, many=True)
        return Response(serializer.data)


