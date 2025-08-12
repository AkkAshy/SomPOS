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
    pagination_class = pagination.PageNumberPagination
    lookup_field = 'id'
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    permission_classes = [IsAuthenticated]
    filterset_fields = ['transaction']

    def get_queryset(self):
        # Фильтруем только нужные действия
        queryset = TransactionHistory.objects.filter(
            action__in=['completed', 'refunded']
        ).exclude(
            Q(details__isnull=True) | Q(details='') | Q(details='{}')
        )


        # Дополнительные фильтры
        transaction_id = self.request.query_params.get('transaction_id')
        product_id = self.request.query_params.get('product')
        customer_id = self.request.query_params.get('customer')
        cashier_id = self.request.query_params.get('cashier')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if transaction_id:
            queryset = queryset.filter(transaction__id=transaction_id)

        if customer_id:
            queryset = queryset.filter(transaction__customer__id=customer_id)

        if cashier_id:
            queryset = queryset.filter(transaction__cashier__id=cashier_id)

        if product_id:
            try:
                product_id = int(product_id)
                queryset = queryset.filter(transaction__items__product__id=product_id).distinct()
            except ValueError:
                queryset = queryset.none()

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset

    def get_serializer_class(self):
        # Используем фильтрующий сериализатор
        return FilteredTransactionHistorySerializer

    def list(self, request, *args, **kwargs):
        """
        Переопределяем list для удаления None значений
        """
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # Фильтруем None значения (записи с неполными данными)
            valid_data = [item for item in serializer.data if item is not None]
            return self.get_paginated_response(valid_data)

        serializer = self.get_serializer(queryset, many=True)
        valid_data = [item for item in serializer.data if item is not None]
        return Response(valid_data)



from django.db.models import IntegerField, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce

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


