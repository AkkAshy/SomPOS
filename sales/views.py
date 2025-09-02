# sales/views.py
from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from django.db.models import Sum, F, FloatField, DecimalField, Value
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

logger = logging.getLogger(__name__)

class IsCashierOrManagerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name__in=['admin', 'manager', 'cashier']).exists()

class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsCashierOrManagerOrAdmin]

    @swagger_auto_schema(
        operation_description="Получить список продаж или создать новую продажу",
        responses={200: TransactionSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description="Создать новую продажу. Для оплаты в долг укажите customer_id или new_customer с full_name и phone.",
        request_body=TransactionSerializer,
        responses={201: TransactionSerializer(), 400: "Invalid data"},
        security=[{'Bearer': []}]
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()




class TransactionHistoryListView(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для просмотра истории транзакций без автоматического пагинатора
    Ручная обработка limit/offset с правильным подсчетом записей
    """
    # БЕЗ pagination_class - убираем пагинатор!
    lookup_field = 'id'
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['created_at', 'id']
    ordering = ['-created_at']
    permission_classes = [IsAuthenticated]
    filterset_fields = ['transaction']

    def get_queryset(self):
        """
        Базовый queryset с фильтрацией
        """
        queryset = TransactionHistory.objects.filter(
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

        # Логирование
        logger.info(f"TransactionHistory list: total_count={total_count}, "
                   f"limit={limit}, offset={offset}, "
                   f"returned={len(valid_data)}, filtered_out={len(original_data) - len(valid_data)}")

        # Формируем ответ
        response_data = {
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


