# auth/views.py
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


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="Вход сотрудника",
        request_body=LoginSerializer,
        responses={
            200: openapi.Response('Токены', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'refresh': openapi.Schema(type=openapi.TYPE_STRING),
                    'access': openapi.Schema(type=openapi.TYPE_STRING),
                    'user': UserSerializer()
                }
            )),
            400: "Неверные данные",
            401: "Неверный логин или пароль"
        },
        tags=['Authentication']
    )
    def post(self, request):
        logger.debug(f"Login request: {request.data}")
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            logger.debug(f"Validated data: {serializer.validated_data}")
            # Получаем аутентифицированного пользователя
            user = authenticate(
                username=serializer.validated_data['username'],
                password=serializer.validated_data.get('password')
            )
            if user and user.is_active:
                return Response({
                    'refresh': serializer.validated_data['refresh'],
                    'access': serializer.validated_data['access'],
                    'user': UserSerializer(user).data  # Используем user вместо request.user
                }, status=status.HTTP_200_OK)
            return Response(
                {"error": _("Неверный логин или пароль")},
                status=status.HTTP_401_UNAUTHORIZED
            )
        logger.error(f"Login failed: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class LoginView(APIView):
#     permission_classes = [permissions.AllowAny]

#     @swagger_auto_schema(
#         operation_summary="Вход сотрудника",
#         request_body=LoginSerializer,
#         responses={
#             200: openapi.Response('Токены', schema=openapi.Schema(
#                 type=openapi.TYPE_OBJECT,
#                 properties={
#                     'refresh': openapi.Schema(type=openapi.TYPE_STRING),
#                     'access': openapi.Schema(type=openapi.TYPE_STRING),
#                     'user': UserSerializer()
#                 }
#             )),
#             400: "Неверные данные",
#             401: "Неверный логин или пароль"
#         },
#         tags=['Authentication']
#     )
#     def post(self, request):
#         print('==============================================')
#         print('LoginView.post')
#         print('request.data', request.data)
#         print('request.user', request.user)
#         print('request.auth', request.auth)
#         print('==============================================')
#         serializer = LoginSerializer(data=request.data)
#         if serializer.is_valid():
#             print('==============================================')
#             print('serializer.validated_data', serializer.validated_data)
#             print('==============================================')
#             user = authenticate(
#                 username=serializer.validated_data['username'],
#                 password=serializer.validated_data['password']
#             )
#             if user:
#                 print('==============================================')
#                 print('user', user)
#                 print('==============================================')
#                 refresh = RefreshToken.for_user(user)
#                 print('==============================================')
#                 print('refresh', str(refresh))
#                 print('==============================================')
#                 return Response({
#                     'refresh': str(refresh),
#                     'access': str(refresh.access_token),
#                     'user': UserSerializer(user).data
#                 })
#             return Response(
#                 {"error": _("Неверный логин или пароль")},
#                 status=status.HTTP_401_UNAUTHORIZED
#             )
#         print('==============================================')
#         print('serializer.errors', serializer.errors)
#         print('==============================================')
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RegisterView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

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

    def put(self, request):
        """
        Обновление профиля пользователя

        PUT /api/users/profile/

        Request Body:
            {
                "username": "string",
                "email": "string",
                "first_name": "string",
                "last_name": "string",
                "groups": ["string"],
                "employee": {
                    "role": "string",
                    "phone": "string",
                    "photo": "string"
                }
            }

        Response:
            200: {
                "id": integer,
                "username": "string",
                "email": "string",
                "first_name": "string",
                "last_name": "string",
                "groups": ["string"],
                "employee": {
                    "role": "string",
                    "phone": "string",
                    "photo": "string"
                }
            }
            400: {
                "error": "string"
            }
        """
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
        """
        Получение профиля текущего пользователя

        GET /api/users/profile/

        Response:
            200: {
                "id": integer,
                "username": "string",
                "email": "string",
                "first_name": "string",
                "last_name": "string",
                "groups": ["string"],
                "employee": {
                    "role": "string",
                    "phone": "string",
                    "photo": "string"
                }
            }
            404: {
                "error": "Пользователь не найден"
            }
        """
        user = request.user
        serializer = UserSerializer(user)
        return Response(serializer.data)


class UserListView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @swagger_auto_schema(
        operation_summary="Список пользователей с фильтрацией по имени и фамилии (поиск по name)",
        manual_parameters=[
            openapi.Parameter('name', openapi.IN_QUERY, description="Поиск по имени, фамилии или полному имени", type=openapi.TYPE_STRING),
        ],
        responses={200: UserSerializer(many=True)},
        tags=['User List']
    )
    def get(self, request, pk=None):
        search_name = request.query_params.get('name')

        users = User.objects.all()

        if search_name:
            # Добавляем аннотированное поле full_name
            users = users.annotate(
                full_name=Concat('first_name', Value(' '), 'last_name')
            ).filter(
                Q(first_name__icontains=search_name) |
                Q(last_name__icontains=search_name) |
                Q(full_name__icontains=search_name)
            )

        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

class UserDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    @swagger_auto_schema(
        operation_summary="Детальный вид пользователя по ID",
        responses={200: UserSerializer()},
        tags=['User Detail']
    )
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        serializer = UserSerializer(user)
        return Response(serializer.data)
