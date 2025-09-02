# stores/views.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)
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

# ✅ ДОБАВЛЯЕМ простые функции
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import json

@csrf_exempt
@require_http_methods(["POST"])
def simple_store_register(request):
    """
    ПРОСТАЯ регистрация магазина без DRF
    """
    logger.info("Simple store registration started")
    
    try:
        # Парсим JSON
        data = json.loads(request.body.decode('utf-8'))
        logger.info(f"Registration data received: {list(data.keys())}")
        
        # Базовая валидация
        required_fields = ['username', 'password', 'email', 'store_name', 'store_address']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return JsonResponse({
                'error': f'Отсутствуют обязательные поля: {", ".join(missing_fields)}'
            }, status=400)
        
        # Проверяем существование пользователя
        if User.objects.filter(username=data['username']).exists():
            return JsonResponse({
                'error': 'Пользователь с таким именем уже существует'
            }, status=400)
        
        if User.objects.filter(email=data['email']).exists():
            return JsonResponse({
                'error': 'Пользователь с таким email уже существует'
            }, status=400)
        
        # Проверяем существование магазина
        if Store.objects.filter(name__iexact=data['store_name']).exists():
            return JsonResponse({
                'error': 'Магазин с таким названием уже существует'
            }, status=400)
        
        with transaction.atomic():
            # Создаем пользователя
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                password=data['password']
            )
            logger.info(f"User created: {user.username}")
            
            # Добавляем в группу admin
            admin_group, created = Group.objects.get_or_create(name='admin')
            user.groups.add(admin_group)
            
            # Создаем Employee если модель существует
            try:
                from users.models import Employee
                Employee.objects.create(
                    user=user,
                    role='admin',
                    phone=data.get('phone', '')
                )
                logger.info(f"Employee record created for {user.username}")
            except ImportError:
                logger.warning("Employee model not found, skipping")
            except Exception as e:
                logger.error(f"Error creating Employee: {e}")
            
            # Создаем магазин
            store = Store.objects.create(
                name=data['store_name'],
                address=data['store_address'],
                phone=data.get('store_phone', ''),
                email=data.get('store_email', ''),
                description=data.get('store_description', ''),
                owner=user
            )
            logger.info(f"Store created: {store.name}")
            
            # Создаем связь StoreEmployee
            store_employee = StoreEmployee.objects.create(
                store=store,
                user=user,
                role='owner'
            )
            logger.info(f"StoreEmployee created: {user.username} -> {store.name}")
            
            # Генерируем токены
            tokens = get_tokens_for_user_and_store(user, str(store.id))
            
            response_data = {
                'success': True,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                },
                'store': {
                    'id': str(store.id),
                    'name': store.name,
                    'address': store.address,
                    'phone': store.phone,
                    'email': store.email,
                },
                'tokens': {
                    'refresh': tokens['refresh'],
                    'access': tokens['access'],
                    'store_id': tokens.get('store_id'),
                    'store_name': tokens.get('store_name'),
                },
                'role': store_employee.role,
                'message': 'Регистрация успешно завершена'
            }
            
            logger.info(f"Registration completed successfully for {user.username}")
            return JsonResponse(response_data, status=201)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный формат JSON'}, status=400)
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Внутренняя ошибка сервера',
            'details': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def simple_refresh_token(request):
    """Простое обновление токена без DRF"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        refresh_token = data.get('refresh')
        store_id = data.get('store_id')
        
        if not refresh_token:
            return JsonResponse({'error': 'refresh token обязателен'}, status=400)
        
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken(refresh_token)
        user_id = refresh.payload.get('user_id')
        
        user = User.objects.get(id=user_id)
        
        if store_id:
            has_access = StoreEmployee.objects.filter(
                user=user,
                store_id=store_id,
                is_active=True
            ).exists()
            
            if not has_access:
                return JsonResponse(
                    {'error': 'У вас нет доступа к указанному магазину'},
                    status=403
                )
        else:
            store_id = refresh.payload.get('store_id')
            if not store_id:
                membership = StoreEmployee.objects.filter(
                    user=user,
                    is_active=True
                ).first()
                if membership:
                    store_id = str(membership.store.id)
        
        tokens = get_tokens_for_user_and_store(user, store_id)
        
        return JsonResponse({
            'access': tokens['access'],
            'refresh': tokens['refresh']
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


class StoreRegisterView(APIView):
    """
    ИСПРАВЛЕНО: Регистрация первого администратора и создание магазина
    """
    # ✅ УБИРАЕМ АУТЕНТИФИКАЦИЮ ПОЛНОСТЬЮ
    permission_classes = []  # Пустой список вместо [permissions.AllowAny]
    authentication_classes = []  # Отключаем все виды аутентификации
    
    @swagger_auto_schema(
        operation_description="Регистрация администратора и создание магазина (без аутентификации)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['username', 'password', 'email', 'store_name', 'store_address'],
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING, example='admin'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, example='secure123'),
                'email': openapi.Schema(type=openapi.TYPE_STRING, example='admin@store.com'),
                'first_name': openapi.Schema(type=openapi.TYPE_STRING, example='John'),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING, example='Doe'),
                'phone': openapi.Schema(type=openapi.TYPE_STRING, example='+998901234567'),
                'store_name': openapi.Schema(type=openapi.TYPE_STRING, example='My Store'),
                'store_address': openapi.Schema(type=openapi.TYPE_STRING, example='123 Main St'),
                'store_phone': openapi.Schema(type=openapi.TYPE_STRING, example='+998901234568'),
                'store_email': openapi.Schema(type=openapi.TYPE_STRING, example='store@example.com'),
                'store_description': openapi.Schema(type=openapi.TYPE_STRING, example='My amazing store'),
            }
        ),
        responses={
            201: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'user': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'store': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'tokens': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'message': openapi.Schema(type=openapi.TYPE_STRING)
                }
            ),
            400: 'Ошибка валидации'
        }
    )
    def post(self, request):
        logger.info("Store registration started")
        logger.debug(f"Request data: {request.data}")
        
        # Базовая валидация входных данных
        required_fields = ['username', 'password', 'email', 'store_name', 'store_address']
        missing_fields = [field for field in required_fields if not request.data.get(field)]
        
        if missing_fields:
            return Response(
                {'error': f'Отсутствуют обязательные поля: {", ".join(missing_fields)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            try:
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
                
                if User.objects.filter(email=user_data['email']).exists():
                    return Response(
                        {'error': 'Пользователь с таким email уже существует'},
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
                
                logger.info(f"User created: {user.username}")
                
                # Добавляем в группу admin
                admin_group, created = Group.objects.get_or_create(name='admin')
                user.groups.add(admin_group)
                
                # Создаем Employee если модель существует
                try:
                    from users.models import Employee
                    Employee.objects.create(
                        user=user,
                        role='admin',
                        phone=request.data.get('phone', '')
                    )
                    logger.info(f"Employee record created for {user.username}")
                except ImportError:
                    logger.warning("Employee model not found, skipping")
                except Exception as e:
                    logger.error(f"Error creating Employee: {e}")
                
                # Создаем магазин
                store_data = {
                    'name': request.data.get('store_name'),
                    'address': request.data.get('store_address'),
                    'phone': request.data.get('store_phone', ''),
                    'email': request.data.get('store_email', ''),
                    'description': request.data.get('store_description', ''),
                }
                
                # Проверяем уникальность имени магазина
                if Store.objects.filter(name__iexact=store_data['name']).exists():
                    return Response(
                        {'error': 'Магазин с таким названием уже существует'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                store_serializer = StoreCreateSerializer(data=store_data)
                if store_serializer.is_valid():
                    store = store_serializer.save(owner=user)
                    logger.info(f"Store created: {store.name}")
                    
                    # Создаем связь StoreEmployee
                    store_employee = StoreEmployee.objects.create(
                        store=store,
                        user=user,
                        role='owner'
                    )
                    logger.info(f"StoreEmployee created: {user.username} -> {store.name}")
                    
                    # Генерируем токены с информацией о магазине
                    tokens = get_tokens_for_user_and_store(user, str(store.id))
                    
                    response_data = {
                        'success': True,
                        'user': {
                            'id': user.id,
                            'username': user.username,
                            'email': user.email,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                        },
                        'store': {
                            'id': str(store.id),
                            'name': store.name,
                            'address': store.address,
                            'phone': store.phone,
                            'email': store.email,
                        },
                        'tokens': {
                            'refresh': tokens['refresh'],
                            'access': tokens['access'],
                            'store_id': tokens.get('store_id'),
                            'store_name': tokens.get('store_name'),
                        },
                        'role': store_employee.role,
                        'message': 'Регистрация успешно завершена'
                    }
                    
                    logger.info(f"Registration completed successfully for {user.username}")
                    return Response(response_data, status=status.HTTP_201_CREATED)
                else:
                    logger.error(f"Store serializer errors: {store_serializer.errors}")
                    return Response(
                        {'error': 'Ошибка данных магазина', 'details': store_serializer.errors},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                    
            except Exception as e:
                logger.error(f"Registration error: {str(e)}", exc_info=True)
                return Response(
                    {'error': 'Внутренняя ошибка сервера', 'details': str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


# ✅ ИСПРАВЛЯЕМ остальные views тоже
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


class CreateUserForStoreView(APIView):
    """
    Создание пользователя с автоматической привязкой к текущему магазину
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Создать пользователя для текущего магазина",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['username', 'password', 'email'],
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING),
                'password': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING),
                'first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'phone': openapi.Schema(type=openapi.TYPE_STRING),
                'store_role': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    enum=['admin', 'manager', 'cashier', 'stockkeeper'],
                    default='cashier'
                ),
            }
        ),
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
            user_data = {
                'username': request.data.get('username'),
                'email': request.data.get('email'),
                'first_name': request.data.get('first_name', ''),
                'last_name': request.data.get('last_name', ''),
                'password': request.data.get('password')
            }
            
            if User.objects.filter(username=user_data['username']).exists():
                return Response(
                    {'error': 'Пользователь с таким именем уже существует'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user = User.objects.create_user(**user_data)
            
            # Автоматически привязываем к текущему магазину
            role = request.data.get('store_role', 'cashier')
            StoreEmployee.objects.create(
                store=request.user.current_store,
                user=user,
                role=role
            )
            
            # Создаем Employee если есть модель
            try:
                from users.models import Employee
                Employee.objects.create(
                    user=user,
                    role=role,
                    phone=request.data.get('phone', '')
                )
            except:
                pass
            
            # Добавляем в соответствующую группу
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)
            
            logger.info(
                f"Пользователь {user.username} создан и привязан к магазину "
                f"{request.user.current_store.name} с ролью {role}"
            )
            
            return Response(
                UserSerializer(user).data,
                status=status.HTTP_201_CREATED
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
    permission_classes = []  # Разрешаем всем для обновления токена
    authentication_classes = []
    
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