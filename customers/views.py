from .models import Customer, CustomerDebt
from .serializers import CustomerSerializer, CustomerDebtSerializer
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema

class IsCashierOrAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow cashiers or admins to edit objects.
    """
    def has_permission(self, request, view):
        # Allow any user to view objects
        if request.method in permissions.SAFE_METHODS:
            return True
        # Only allow cashiers to edit objects
        return request.user.is_authenticated and request.user.is_cashier
    

class CustomerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing customers.
    Allows listing, retrieving, creating, updating, and deleting customers.
    """
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated, IsCashierOrAdminOrReadOnly]

    def perform_create(self, serializer):
        # Automatically set the user who created the customer
        serializer.save(created_by=self.request.user)

class CustomerDebtViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing customer debts.
    Allows listing, retrieving, creating, updating, and deleting customer debts.
    """
    queryset = CustomerDebt.objects.all()
    serializer_class = CustomerDebtSerializer
    permission_classes = [permissions.IsAuthenticated, IsCashierOrAdminOrReadOnly]

    def perform_create(self, serializer):
        # Automatically set the user who created the debt
        serializer.save(created_by=self.request.user)

    @swagger_auto_schema(
        operation_description="Retrieve all debts for a specific customer",
        responses={200: CustomerDebtSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        customer_id = self.kwargs.get("customer_id")
        debts = self.queryset.filter(customer_id=customer_id)
        serializer = self.get_serializer(debts, many=True)
        return Response(serializer.data)