# stores/middleware.py
from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from .models import StoreEmployee, Store
import logging

logger = logging.getLogger(__name__)

class CurrentStoreMiddleware(MiddlewareMixin):
    """
    Middleware для установки текущего магазина пользователя из JWT токена
    """
    def process_request(self, request):
        if request.user.is_authenticated:
            store_id = None
            store_role = None
            
            # Пытаемся получить магазин из JWT токена
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                try:
                    # Декодируем токен
                    from rest_framework_simplejwt.tokens import AccessToken
                    decoded_token = AccessToken(token)
                    
                    # Извлекаем store_id из токена
                    store_id = decoded_token.get('store_id')
                    store_role = decoded_token.get('store_role')
                    
                    logger.debug(f"Store ID from JWT token: {store_id}, Role: {store_role}")
                    
                except Exception as e:
                    logger.debug(f"Failed to decode JWT token: {e}")
            
            # Если в токене нет store_id, проверяем сессию (для веб-интерфейса)
            if not store_id:
                store_id = request.session.get('current_store_id')
                logger.debug(f"Store ID from session: {store_id}")
            
            # Устанавливаем текущий магазин
            if store_id:
                try:
                    # Получаем магазин напрямую
                    store = Store.objects.get(id=store_id, is_active=True)
                    
                    # Проверяем, что пользователь имеет доступ
                    store_membership = StoreEmployee.objects.filter(
                        user=request.user,
                        store=store,
                        is_active=True
                    ).first()
                    
                    if store_membership:
                        request.user.current_store = store
                        request.user.store_role = store_membership.role
                        request.user.store_id = str(store.id)
                        logger.debug(f"Set current store: {store.name} for user {request.user.username}")
                    else:
                        logger.warning(f"User {request.user.username} has no access to store {store_id}")
                        request.user.current_store = None
                        request.user.store_role = None
                        request.user.store_id = None
                        
                except Store.DoesNotExist:
                    logger.error(f"Store {store_id} not found")
                    request.user.current_store = None
                    request.user.store_role = None
                    request.user.store_id = None
            else:
                # Если магазин не указан в токене, берем первый доступный
                store_membership = StoreEmployee.objects.filter(
                    user=request.user,
                    is_active=True
                ).select_related('store').first()
                
                if store_membership:
                    request.user.current_store = store_membership.store
                    request.user.store_role = store_membership.role
                    request.user.store_id = str(store_membership.store.id)
                    request.session['current_store_id'] = str(store_membership.store.id)
                    logger.debug(f"Set default store: {store_membership.store.name} for user {request.user.username}")
                else:
                    logger.debug(f"User {request.user.username} has no store memberships")
                    request.user.current_store = None
                    request.user.store_role = None
                    request.user.store_id = None
        
        return None