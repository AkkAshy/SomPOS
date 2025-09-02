# users/views.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .serializers import LoginSerializer, UserSerializer
from rest_framework_simplejwt.tokens import RefreshToken
import logging
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.db.models import Q, Value
from django.db.models.functions import Concat

User = get_user_model()

logger = logging.getLogger(__name__)

# ✅ ДОБАВЛЯЕМ простую функцию логина
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import json

@csrf_exempt
@require_http_methods(["POST"])
def simple_login(request):
    """
    Простой логин без DRF
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        username = data.get('username')
        password = data.get('password')
        store_id = data.get('store_id')
        
        if not username or not password:
            return JsonResponse(
                {'error': 'Username и password обязательны'},
                status=400
            )
        
        # Аутентификация
        user = authenticate(username=username, password=password)
        
        if not user or not user.is_active:
            return JsonResponse(
                {'error': 'Неверный логин или пароль'},
                status=401
            )
        
        # Получаем магазины
        from stores.models import StoreEmployee
        store_memberships = StoreEmployee.objects.filter(
            user=user,
            is_active=True
        ).select_related('store')
        
        if not store_memberships.exists():
            return JsonResponse(
                {'error': 'Пользователь не привязан ни к одному магазину'},
                status=403
            )
        
        # Определяем текущий магазин
        if store_id:
            current_membership = store_memberships.filter(store_id=store_id).first()
            if not current_membership:
                return JsonResponse(
                    {'error': 'У вас нет доступа к указанному магазину'},
                    status=403
                )
        else:
            current_membership = store_memberships.first()
        
        # Генерируем токены
        from stores.tokens import get_tokens_for_user_and_store
        tokens = get_tokens_for_user_and_store(user, str(current_membership.store.id))
        
        # Формируем список магазинов
        available_stores = []
        for membership in store_memberships:
            available_stores.append({
                'id': str(membership.store.id),
                'name': membership.store.name,
                'role': membership.role,
                'is_current': str(membership.store.id) == str(current_membership.store.id)
            })
        
        return JsonResponse({
            'success': True,
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'current_store': {
                'id': str(current_membership.store.id),
                'name': current_membership.store.name,
                'role': current_membership.role
            },
            'available_stores': available_stores
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный формат JSON'}, status=400)
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


class LoginView(APIView):
    """
    ИСПРАВЛЕННЫЙ LoginView - возвращает токены с информацией о магазине
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @swagger_auto_schema(
        operation_summary="Вход пользователя с получением токенов",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING, example='testadmin'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, example='secure123'),
                'store_id': openapi.Schema(type=openapi.TYPE_STRING, format='uuid', description='ID магазина (опционально)')
            },
            required=['username', 'password']
        ),
        responses={
            200: openapi.Response('Успешный вход', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'access': openapi.Schema(type=openapi.TYPE_STRING),
                    'refresh': openapi.Schema(type=openapi.TYPE_STRING),
                    'user': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'current_store': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'available_stores': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT)
                    )
                }
            )),
            400: "Неверные данные",
            401: "Неверный логин или пароль"
        },
        tags=['Authentication']
    )
    def post(self, request):
        logger.info("Login attempt started")
        
        username = request.data.get('username')
        password = request.data.get('password')
        store_id = request.data.get('store_id')
        
        if not username or not password:
            return Response(
                {'error': 'Username и password обязательны'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Аутентификация пользователя
        user = authenticate(username=username, password=password)
        
        if not user:
            return Response(
                {"error": "Неверный логин или пароль"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if not user.is_active:
            return Response(
                {"error": "Аккаунт деактивирован"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        logger.info(f"User {username} authenticated successfully")
        
        # Получаем магазины пользователя
        from stores.models import StoreEmployee
        store_memberships = StoreEmployee.objects.filter(
            user=user,
            is_active=True
        ).select_related('store')
        
        if not store_memberships.exists():
            return Response(
                {"error": "Пользователь не привязан ни к одному магазину. Обратитесь к администратору."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Определяем текущий магазин
        if store_id:
            # Проверяем доступ к указанному магазину
            current_membership = store_memberships.filter(store_id=store_id).first()
            if not current_membership:
                return Response(
                    {"error": "У вас нет доступа к указанному магазину"},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            # Берем первый доступный магазин
            current_membership = store_memberships.first()
        
        # Генерируем токены с информацией о магазине
        from stores.tokens import get_tokens_for_user_and_store
        tokens = get_tokens_for_user_and_store(user, str(current_membership.store.id))
        
        # Формируем список всех доступных магазинов
        available_stores = []
        for membership in store_memberships:
            available_stores.append({
                'id': str(membership.store.id),
                'name': membership.store.name,
                'role': membership.role,
                'logo': membership.store.logo.url if membership.store.logo else None,
                'is_current': str(membership.store.id) == str(current_membership.store.id)
            })
        
        response_data = {
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.get_full_name() or user.username
            },
            'current_store': {
                'id': str(current_membership.store.id),
                'name': current_membership.store.name,
                'role': current_membership.role
            },
            'available_stores': available_stores,
            'message': 'Успешный вход в систему'
        }
        
        logger.info(f"Login successful for {username} with store {current_membership.store.name}")
        return Response(response_data, status=status.HTTP_200_OK)


# ДОБАВЛЯЕМ простую функцию логина тоже
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import json

@csrf_exempt
@require_http_methods(["POST"])
def simple_login(request):
    """
    Простой логин без DRF
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        username = data.get('username')
        password = data.get('password')
        store_id = data.get('store_id')
        
        if not username or not password:
            return JsonResponse(
                {'error': 'Username и password обязательны'},
                status=400
            )
        
        # Аутентификация
        user = authenticate(username=username, password=password)
        
        if not user or not user.is_active:
            return JsonResponse(
                {'error': 'Неверный логин или пароль'},
                status=401
            )
        
        # Получаем магазины
        from stores.models import StoreEmployee
        store_memberships = StoreEmployee.objects.filter(
            user=user,
            is_active=True
        ).select_related('store')
        
        if not store_memberships.exists():
            return JsonResponse(
                {'error': 'Пользователь не привязан ни к одному магазину'},
                status=403
            )
        
        # Определяем текущий магазин
        if store_id:
            current_membership = store_memberships.filter(store_id=store_id).first()
            if not current_membership:
                return JsonResponse(
                    {'error': 'У вас нет доступа к указанному магазину'},
                    status=403
                )
        else:
            current_membership = store_memberships.first()
        
        # Генерируем токены
        from stores.tokens import get_tokens_for_user_and_store
        tokens = get_tokens_for_user_and_store(user, str(current_membership.store.id))
        
        # Формируем список магазинов
        available_stores = []
        for membership in store_memberships:
            available_stores.append({
                'id': str(membership.store.id),
                'name': membership.store.name,
                'role': membership.role,
                'is_current': str(membership.store.id) == str(current_membership.store.id)
            })
        
        return JsonResponse({
            'success': True,
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'current_store': {
                'id': str(current_membership.store.id),
                'name': current_membership.store.name,
                'role': current_membership.role
            },
            'available_stores': available_stores
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный формат JSON'}, status=400)
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Внутренняя ошибка сервера'}, status=500)


# Остальные views остаются без изменений...
class RegisterView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @swagger_auto_schema(
        operation_summary="Регистрация сотрудника",
        request_body=UserSerializer,
        responses={201: UserSerializer, 400: "Неверные данные"},
        tags=['Registration']
    )
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Обновление профиля пользователя",
        request_body=UserSerializer,
        responses={200: UserSerializer, 400: "Неверные данные"},
        tags=['Update Profile']
    )
    def patch(self, request):
        user = request.user
        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    @swagger_auto_schema(
        operation_summary="Получение профиля пользователя",
        responses={200: UserSerializer, 404: "Пользователь не найден"},
        tags=['Profile']
    )
    def get(self, request):
        user = request.user
        serializer = UserSerializer(user)
        return Response(serializer.data)


class UserListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Список пользователей с фильтрацией по имени, фамилии или ID",
        manual_parameters=[
            openapi.Parameter(
                'name',
                openapi.IN_QUERY,
                description="Поиск по имени, фамилии или полному имени",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'id',
                openapi.IN_QUERY,
                description="Поиск по ID пользователя",
                type=openapi.TYPE_INTEGER
            ),
        ],
        responses={200: UserSerializer(many=True)},
        tags=['User List']
    )
    def get(self, request, pk=None):
        search_name = request.query_params.get('name')
        search_id = request.query_params.get('id')

        users = User.objects.all()

        if search_name or search_id:
            filters = Q()
            if search_name:
                users = users.annotate(
                    full_name=Concat('first_name', Value(' '), 'last_name')
                )
                filters |= (
                    Q(first_name__icontains=search_name) |
                    Q(last_name__icontains=search_name) |
                    Q(full_name__icontains=search_name)
                )
            if search_id:
                try:
                    search_id = int(search_id)
                    filters |= Q(id__exact=search_id)
                except ValueError:
                    logger.warning(f"Invalid ID format: {search_id}")
                    return Response(
                        {"error": "Параметр 'id' должен быть целым числом"},
                        status=400
                    )

            users = users.filter(filters)

        serializer = UserSerializer(users, many=True)
        logger.debug(f"Retrieved {len(users)} users with filters: name={search_name}, id={search_id}")
        return Response(serializer.data)


class UserDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Детальный вид пользователя по ID",
        responses={200: UserSerializer()},
        tags=['User Detail']
    )
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        serializer = UserSerializer(user)
        return Response(serializer.data)