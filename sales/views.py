# sales/views.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import Transaction
from .serializers import TransactionSerializer
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters


class IsCashierOrManagerOrAdmin(permissions.BasePermission):
    """
    Доступ для пользователей с ролью admin, manager или cashier (по группе или Employee.role)
    """
    allowed_roles = ['admin', 'manager', 'cashier']

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False

        # Проверка через группы
        if user.groups.filter(name__in=self.allowed_roles).exists():
            return True

        # Проверка через Employee.role
        if hasattr(user, 'employee') and user.employee.role in self.allowed_roles:
            return True
        
        print(request.user, request.user.is_authenticated)

        return False


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsCashierOrManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['cashier', 'payment_method', 'status']
    search_fields = ['customer__name', 'cashier__username']

    @swagger_auto_schema(
        operation_description="Получить список продаж или создать новую продажу",
        responses={200: TransactionSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description="Создать новую продажу",
        request_body=TransactionSerializer,
        responses={201: TransactionSerializer()}
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @swagger_auto_schema(
        operation_description="Получить продажи конкретного кассира",
        manual_parameters=[
            openapi.Parameter('cashier_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="ID кассира")
        ],
        responses={200: TransactionSerializer(many=True)}
    )
    @action(detail=False, methods=['get'], url_path='by-cashier')
    def by_cashier(self, request):
        cashier_id = request.query_params.get('cashier_id')
        if not cashier_id:
            return Response(
                {"error": _("Требуется указать ID кассира")},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            transactions = self.queryset.filter(cashier_id=cashier_id)
            serializer = self.get_serializer(transactions, many=True)
            logger.info(f"Запрошены продажи кассира ID {cashier_id} пользователем {request.user.username}")
            return Response(serializer.data)
        except ValueError:
            return Response(
                {"error": _("Некорректный ID кассира")},
                status=status.HTTP_400_BAD_REQUEST
            )
        
