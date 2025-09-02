# stores/tokens.py
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import StoreEmployee

class StoreTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Кастомный сериализатор для JWT токена с информацией о магазине
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Получаем первый активный магазин пользователя
        store_membership = StoreEmployee.objects.filter(
            user=user,
            is_active=True
        ).select_related('store').first()
        
        if store_membership:
            # Добавляем информацию о магазине в токен
            token['store_id'] = str(store_membership.store.id)
            token['store_name'] = store_membership.store.name
            token['store_role'] = store_membership.role
        
        # Добавляем дополнительную информацию о пользователе
        token['username'] = user.username
        token['email'] = user.email
        token['full_name'] = user.get_full_name()
        
        return token


def get_tokens_for_user_and_store(user, store_id=None):
    """
    Генерирует токены для пользователя с указанным магазином
    """
    refresh = RefreshToken.for_user(user)
    
    if store_id:
        # Проверяем, что пользователь имеет доступ к этому магазину
        store_membership = StoreEmployee.objects.filter(
            user=user,
            store_id=store_id,
            is_active=True
        ).select_related('store').first()
        
        if store_membership:
            # Добавляем информацию о магазине в токен
            refresh['store_id'] = str(store_membership.store.id)
            refresh['store_name'] = store_membership.store.name
            refresh['store_role'] = store_membership.role
            
            # Добавляем в access token тоже
            access = refresh.access_token
            access['store_id'] = str(store_membership.store.id)
            access['store_name'] = store_membership.store.name
            access['store_role'] = store_membership.role
    else:
        # Если магазин не указан, берем первый доступный
        store_membership = StoreEmployee.objects.filter(
            user=user,
            is_active=True
        ).select_related('store').first()
        
        if store_membership:
            refresh['store_id'] = str(store_membership.store.id)
            refresh['store_name'] = store_membership.store.name
            refresh['store_role'] = store_membership.role
            
            access = refresh.access_token
            access['store_id'] = str(store_membership.store.id)
            access['store_name'] = store_membership.store.name
            access['store_role'] = store_membership.role
    
    # Добавляем информацию о пользователе
    refresh['username'] = user.username
    refresh['email'] = user.email
    refresh['full_name'] = user.get_full_name()
    
    access = refresh.access_token
    access['username'] = user.username
    access['email'] = user.email
    access['full_name'] = user.get_full_name()
    
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'store_id': refresh.get('store_id'),
        'store_name': refresh.get('store_name'),
        'store_role': refresh.get('store_role')
    }