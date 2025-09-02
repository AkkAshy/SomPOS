# stores/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Временные заглушки, пока не созданы views
urlpatterns = [
    # Пока пустой список URL, чтобы приложение запускалось
]

# После создания views.py, замените на:

from .views import (
    StoreViewSet, StoreRegisterView, CreateUserForStoreView,
    SwitchStoreView, RefreshTokenWithStoreView
)

router = DefaultRouter()
router.register(r'stores', StoreViewSet, basename='store')

urlpatterns = [
    # Регистрация первого админа и магазина
    path('register/', StoreRegisterView.as_view(), name='store-register'),

    # Переключение магазина с новым токеном
    path('switch-store/', SwitchStoreView.as_view(), name='switch-store'),

    # Обновление токена с магазином
    path('refresh-token/', RefreshTokenWithStoreView.as_view(), name='refresh-token-store'),

    # Создание пользователя для текущего магазина
    path('create-user/', CreateUserForStoreView.as_view(), name='create-store-user'),

    # CRUD магазинов
    path('', include(router.urls)),
]
