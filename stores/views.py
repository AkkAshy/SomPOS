# stores/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.models import User, Group
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework_simplejwt.tokens import RefreshToken
import logging

from .models import Store, StoreEmployee
from .serializers import (
    StoreSerializer, StoreCreateSerializer,
    StoreEmployeeSerializer, StoreSwitchSerializer
)
from .tokens import get_tokens_for_user_and_store
from users.serializers import UserSerializer

logger = logging.getLogger(__name__)


class StoreViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления магазинами
    """
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Показываем только магазины, к которым у пользователя есть доступ"""
        user = self.request.user
        
        # Если суперпользователь - показываем все
        if user.is_superuser:
            return Store.objects.all()
        
        # Иначе только магазины, где пользователь является сотрудником
        store_ids = StoreEmployee.objects.filter(
            user=user,
            is_active=True
        ).values_list('store_id', flat=True)
        
        return Store.objects.filter(id__in=store_ids)
    
    def perform_create(self, serializer):
        """При создании магазина автоматически делаем создателя владельцем"""
        store = serializer.save(owner=self.request.user)
        
        # Создаем связь StoreEmployee
        StoreEmployee.objects.create(
            store=store,
            user=self.request.user,
            role='owner'
        )
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def add_employee(self, request, pk=None):
        """Добавить сотрудника в магазин"""
        store = self.get_object()
        
        # Проверяем права - только владелец или админ магазина
        store_employee = StoreEmployee.objects.filter(
            store=store,
            user=request.user,
            role__in=['owner', 'admin']
        ).first()
        
        if not store_employee and not request.user.is_superuser:
            return Response(
                {'error': 'У вас нет прав для добавления сотрудников'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        user_id = request.data.get('user_id')
        role = request.data.get('role', 'cashier')
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Создаем связь
        employee, created = StoreEmployee.objects.get_or_create(
            store=store,
            user=user,
            defaults={'role': role}
        )
        
        if not created:
            employee.role = role
            employee.is_active = True
            employee.save()
        
        return Response(
            StoreEmployeeSerializer(employee).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['delete'])
    def remove_employee(self, request, pk=None):
        """Удалить сотрудника из магазина"""
        store = self.get_object()
        user_id = request.data.get('user_id')
        
        # Проверяем права
        if not StoreEmployee.objects.filter(
            store=store,
            user=request.user,
            role__in=['owner', 'admin']
        ).exists() and not request.user.is_superuser:
            return Response(
                {'error': 'У вас нет прав для удаления сотрудников'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            employee = StoreEmployee.objects.get(
                store=store,
                user_id=user_id
            )
            
            # Нельзя удалить владельца
            if employee.role == 'owner':
                return Response(
                    {'error': 'Нельзя удалить владельца магазина'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            employee.delete()
            return Response(
                {'message': 'Сотрудник удален из магазина'},
                status=status.HTTP_204_NO_CONTENT
            )
        except StoreEmployee.DoesNotExist:
            return Response(
                {'error': 'Сотрудник не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def employees(self, request, pk=None):
        """Получить список сотрудников магазина"""
        store = self.get_object()
        employees = StoreEmployee.objects.filter(store=store, is_active=True)
        serializer = StoreEmployeeSerializer(employees, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def switch(self, request):
        """Переключиться на другой магазин"""
        serializer = StoreSwitchSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            store_id = serializer.validated_data['store_id']
            
            # Генерируем новые токены с новым магазином
            tokens = get_tokens_for_user_and_store(request.user, store_id)
            
            # Сохраняем в сессию
            request.session['current_store_id'] = str(store_id)
            
            # Получаем информацию о магазине
            store = Store.objects.get(id=store_id)
            store_employee = StoreEmployee.objects.get(
                store=store,
                user=request.user
            )
            
            return Response({
                'message': 'Магазин успешно переключен',
                'access': tokens['access'],
                'refresh': tokens['refresh'],
                'store': StoreSerializer(store).data,
                'role': store_employee.role
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Получить текущий магазин пользователя"""
        if hasattr(request.user, 'current_store') and request.user.current_store:
            return Response({
                'store': StoreSerializer(request.user.current_store).data,
                'role': request.user.store_role
            })
        
        # Если текущий магазин не установлен, берем первый доступный
        membership = StoreEmployee.objects.filter(
            user=request.user,
            is_active=True
        ).select_related('store').first()
        
        if membership:
            return Response({
                'store': StoreSerializer(membership.store).data,
                'role': membership.role
            })
        
        return Response(
            {'error': 'У вас нет доступа ни к одному магазину'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Получить статистику магазина"""
        store = self.get_object()
        
        # Проверяем права на просмотр аналитики
        if not StoreEmployee.objects.filter(
            store=store,
            user=request.user,
            can_view_analytics=True
        ).exists() and not request.user.is_superuser:
            return Response(
                {'error': 'У вас нет прав для просмотра статистики'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from django.db.models import Count, Sum
        from django.utils import timezone
        
        # Подсчитываем статистику
        stats = {
            'employees_count': store.store_employees.filter(is_active=True).count(),
            'products_count': 0,  # Будет работать после добавления store к Product
            'customers_count': 0,  # Будет работать после добавления store к Customer
            'today_sales': 0,  # Будет работать после добавления store к Transaction
        }
        
        # После добавления поля store к моделям, раскомментируйте:
        # stats['products_count'] = store.products.count()
        # stats['customers_count'] = store.customers.count()
        # today = timezone.now().date()
        # stats['today_sales'] = store.transactions.filter(
        #     created_at__date=today,
        #     status='completed'
        # ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        return Response(stats)


class StoreRegisterView(APIView):
    """
    Регистрация первого администратора и создание магазина
    """
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Регистрация администратора и создание магазина",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['username', 'password', 'email', 'store_name', 'store_address'],
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING),
                'password': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING),
                'first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'phone': openapi.Schema(type=openapi.TYPE_STRING),
                'store_name': openapi.Schema(type=openapi.TYPE_STRING),
                'store_address': openapi.Schema(type=openapi.TYPE_STRING),
                'store_phone': openapi.Schema(type=openapi.TYPE_STRING),
                'store_email': openapi.Schema(type=openapi.TYPE_STRING),
                'store_description': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={201: 'Успешная регистрация', 400: 'Ошибка валидации'}
    )
    def post(self, request):
        with transaction.atomic():
            # Создаем пользователя
            user_data = {
                'username': request.data.get('username'),
                'email': request.data.get('email'),
                'first_name': request.data.get('first_name', ''),
                'last_name': request.data.get('last_name', ''),
            }
            
            # Проверяем существование пользователя
            if User.objects.filter(username=user_data['username']).exists():
                return Response(
                    {'error': 'Пользователь с таким именем уже существует'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Создаем пользователя
            user = User.objects.create_user(
                username=user_data['username'],
                email=user_data['email'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                password=request.data.get('password')
            )
            
            # Добавляем в группу admin
            admin_group, _ = Group.objects.get_or_create(name='admin')
            user.groups.add(admin_group)
            
            # Создаем Employee если модель существует
            try:
                from users.models import Employee
                Employee.objects.create(
                    user=user,
                    role='admin',
                    phone=request.data.get('phone', '')
                )
            except:
                pass  # Если модель Employee не существует, пропускаем
            
            # Создаем магазин
            store_data = {
                'name': request.data.get('store_name'),
                'address': request.data.get('store_address'),
                'phone': request.data.get('store_phone', ''),
                'email': request.data.get('store_email', ''),
                'description': request.data.get('store_description', ''),
            }
            
            store_serializer = StoreCreateSerializer(data=store_data)
            if store_serializer.is_valid():
                store = store_serializer.save(owner=user)
                
                # Создаем связь StoreEmployee
                StoreEmployee.objects.create(
                    store=store,
                    user=user,
                    role='owner'
                )
                
                # Генерируем токены с информацией о магазине
                tokens = get_tokens_for_user_and_store(user, str(store.id))
                
                return Response({
                    'user': UserSerializer(user).data,
                    'store': StoreSerializer(store).data,
                    'tokens': {
                        'refresh': tokens['refresh'],
                        'access': tokens['access'],
                    },
                    'message': 'Регистрация успешно завершена'
                }, status=status.HTTP_201_CREATED)
            else:
                user.delete()  # Откатываем создание пользователя
                return Response(
                    store_serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )


class CreateUserForStoreView(APIView):
    """
    Создание пользователя с автоматической привязкой к текущему магазину
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Создать пользователя для текущего магазина",
        request_body=UserSerializer,
        responses={201: UserSerializer}
    )
    def post(self, request):
        # Проверяем права - только владелец или админ
        if not hasattr(request.user, 'current_store'):
            return Response(
                {'error': 'Текущий магазин не установлен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if request.user.store_role not in ['owner', 'admin']:
            return Response(
                {'error': 'У вас нет прав для создания пользователей'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        with transaction.atomic():
            # Создаем пользователя
            user_serializer = UserSerializer(data=request.data)
            if user_serializer.is_valid():
                user = user_serializer.save()
                
                # Автоматически привязываем к текущему магазину
                role = request.data.get('store_role', 'cashier')
                StoreEmployee.objects.create(
                    store=request.user.current_store,
                    user=user,
                    role=role
                )
                
                logger.info(
                    f"Пользователь {user.username} создан и привязан к магазину "
                    f"{request.user.current_store.name} с ролью {role}"
                )
                
                return Response(
                    user_serializer.data,
                    status=status.HTTP_201_CREATED
                )
            
            return Response(
                user_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )


class SwitchStoreView(APIView):
    """
    Переключение на другой магазин с генерацией нового JWT токена
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Переключиться на другой магазин и получить новый токен",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['store_id'],
            properties={
                'store_id': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format='uuid',
                    description='ID магазина для переключения'
                )
            }
        ),
        responses={
            200: 'Магазин переключен',
            403: 'Нет доступа к магазину',
            404: 'Магазин не найден'
        }
    )
    def post(self, request):
        store_id = request.data.get('store_id')
        
        if not store_id:
            return Response(
                {'error': 'store_id обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Проверяем, что пользователь имеет доступ к этому магазину
        try:
            store_membership = StoreEmployee.objects.get(
                user=request.user,
                store_id=store_id,
                is_active=True
            )
        except StoreEmployee.DoesNotExist:
            return Response(
                {'error': 'У вас нет доступа к этому магазину'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Генерируем новые токены с новым магазином
        tokens = get_tokens_for_user_and_store(request.user, store_id)
        
        # Также сохраняем в сессию для веб-интерфейса
        request.session['current_store_id'] = str(store_id)
        
        return Response({
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'store': {
                'id': str(store_membership.store.id),
                'name': store_membership.store.name,
                'address': store_membership.store.address,
                'role': store_membership.role
            },
            'message': 'Магазин успешно переключен. Используйте новый access token для дальнейших запросов.'
        })


class RefreshTokenWithStoreView(APIView):
    """
    Обновление токена с сохранением информации о магазине
    """
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Обновить access token с сохранением магазина",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['refresh'],
            properties={
                'refresh': openapi.Schema(type=openapi.TYPE_STRING),
                'store_id': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    format='uuid',
                    description='ID магазина (опционально, для смены магазина)'
                )
            }
        )
    )
    def post(self, request):
        refresh_token = request.data.get('refresh')
        store_id = request.data.get('store_id')
        
        if not refresh_token:
            return Response(
                {'error': 'refresh token обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken(refresh_token)
            user_id = refresh.payload.get('user_id')
            
            user = User.objects.get(id=user_id)
            
            # Если указан новый магазин, проверяем доступ
            if store_id:
                has_access = StoreEmployee.objects.filter(
                    user=user,
                    store_id=store_id,
                    is_active=True
                ).exists()
                
                if not has_access:
                    return Response(
                        {'error': 'У вас нет доступа к указанному магазину'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                # Берем магазин из старого токена или первый доступный
                store_id = refresh.payload.get('store_id')
                if not store_id:
                    membership = StoreEmployee.objects.filter(
                        user=user,
                        is_active=True
                    ).first()
                    if membership:
                        store_id = str(membership.store.id)
            
            # Генерируем новые токены
            tokens = get_tokens_for_user_and_store(user, store_id)
            
            return Response({
                'access': tokens['access'],
                'refresh': tokens['refresh']
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )