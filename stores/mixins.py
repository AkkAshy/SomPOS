# stores/mixins.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)
from django.db import models
from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework import serializers
from .models import Store
import logging

logger = logging.getLogger(__name__)


class StoreOwnedModel(models.Model):
    """
    Абстрактная модель для всех сущностей, принадлежащих магазину
    """
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='%(class)s_set',
        verbose_name="Магазин",
        editable=False
    )

    class Meta:
        abstract = True


class StoreFilteredQuerySet(models.QuerySet):
    """
    QuerySet, который автоматически фильтрует по магазину
    """
    def for_store(self, store):
        """Фильтрация по конкретному магазину"""
        if store:
            return self.filter(store=store)
        return self.none()

    def for_user(self, user):
        """Фильтрация по магазину пользователя"""
        if hasattr(user, 'current_store') and user.current_store:
            return self.filter(store=user.current_store)
        return self.none()


class StoreOwnedManager(models.Manager):
    """
    Менеджер для моделей, принадлежащих магазину
    """
    def get_queryset(self):
        return StoreFilteredQuerySet(self.model, using=self._db)

    def for_store(self, store):
        return self.get_queryset().for_store(store)

    def for_user(self, user):
        return self.get_queryset().for_user(user)


# class StoreViewSetMixin:
#     """
#     Миксин для ViewSet'ов с автоматической фильтрацией по магазину
#     """
#     def get_current_store(self):
#         """Получить текущий магазин с резервными способами"""
#         user = self.request.user

#         # Способ 1: Из атрибутов пользователя (установлено middleware)
#         if hasattr(user, 'current_store') and user.current_store:
#             logger.debug(f"✅ Store from user attribute: {user.current_store.name}")
#             return user.current_store

#         # ✅ ДОБАВЛЯЕМ: Способ 2 - через Employee модель (ваш основной случай)
#         if hasattr(user, 'employee') and user.employee and user.employee.store:
#             store = user.employee.store
#             logger.debug(f"✅ Store from Employee model: {store.name}")
#             # Кешируем для следующих запросов
#             user.current_store = store
#             return store

#         # Способ 3: Из JWT токена напрямую
#         try:
#             auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
#             if auth_header.startswith('Bearer '):
#                 token = auth_header.split(' ')[1]
#                 from rest_framework_simplejwt.tokens import AccessToken
#                 decoded_token = AccessToken(token)
#                 store_id = decoded_token.get('store_id')

#                 if store_id:
#                     from stores.models import Store
#                     store = Store.objects.get(id=store_id, is_active=True)
#                     logger.debug(f"✅ Store from JWT token: {store.name}")
#                     # Кешируем для следующих запросов
#                     user.current_store = store
#                     return store
#         except Exception as e:
#             logger.debug(f"Failed to get store from JWT: {e}")

#         # ✅ ИСПРАВЛЯЕМ: Способ 4 - для админов берем первый доступный магазин
#         if user.groups.filter(name='admin').exists():
#             try:
#                 from stores.models import Store
#                 first_store = Store.objects.filter(is_active=True).first()
#                 if first_store:
#                     logger.debug(f"✅ Store for admin from first available: {first_store.name}")
#                     user.current_store = first_store
#                     return first_store
#             except Exception as e:
#                 logger.debug(f"Failed to get first store for admin: {e}")

#         # ✅ ДОБАВЛЯЕМ: Способ 5 - из параметров запроса (для тестирования)
#         store_id = self.request.query_params.get('store_id')
#         if store_id:
#             try:
#                 from stores.models import Store
#                 store = Store.objects.get(id=store_id, is_active=True)
#                 logger.debug(f"✅ Store from query parameter: {store.name}")
#                 return store
#             except Exception as e:
#                 logger.debug(f"Invalid store_id parameter: {store_id}, error: {e}")

#         logger.warning(f"❌ No store found for user {user.username}")
#         return None

#     def get_queryset(self):
#         """Автоматически фильтруем по магазину"""
#         queryset = super().get_queryset()

#         # Проверяем, что модель поддерживает магазины
#         if not hasattr(queryset.model, 'store'):
#             logger.debug(f"Model {queryset.model.__name__} doesn't have store field, skipping filter")
#             return queryset

#         # Получаем текущий магазин
#         current_store = self.get_current_store()

#         if current_store:
#             queryset = queryset.filter(store=current_store)
#             logger.debug(f"✅ Filtered queryset by store: {current_store.name}")
#         else:
#             # ✅ ИСПРАВЛЯЕМ: Для сканирования не блокируем доступ полностью
#             # Вместо пустого queryset, логируем предупреждение
#             logger.warning(f"⚠️ No store found for {queryset.model.__name__}, returning unfiltered queryset")
#             # Для некоторых операций (как сканирование) может потребоваться доступ ко всем данным
#             # queryset = queryset.none()  # Закомментируем эту строку

#         return queryset

#     def perform_create(self, serializer):
#         """✅ ИСПРАВЛЕННОЕ создание с правильным порядком операций"""
#         current_store = self.get_current_store()

#         if not current_store:
#             logger.error(f"❌ Cannot create {serializer.Meta.model.__name__}: no store found")
#             raise ValidationError({
#                 'non_field_errors': ['Магазин не определен. Переавторизуйтесь или выберите магазин.'],
#                 'debug_info': {
#                     'user_id': self.request.user.id,
#                     'username': self.request.user.username,
#                     'has_current_store': hasattr(self.request.user, 'current_store'),
#                     'current_store_value': getattr(self.request.user, 'current_store', None),
#                     'has_employee': hasattr(self.request.user, 'employee'),
#                     'employee_store': getattr(self.request.user.employee, 'store', None) if hasattr(self.request.user, 'employee') and self.request.user.employee else None
#                 }
#             })

#         # Подготавливаем данные для сохранения
#         save_kwargs = {'store': current_store}

#         # Дополнительные поля
#         if hasattr(serializer.Meta.model, 'created_by'):
#             save_kwargs['created_by'] = self.request.user

#         if hasattr(serializer.Meta.model, 'cashier'):
#             save_kwargs['cashier'] = self.request.user

#         try:
#             # ✅ ВАЖНО: Для Product - особый случай
#             if serializer.Meta.model.__name__ == 'Product':
#                 # Если instance уже создан в serializer.create(), просто дополняем его
#                 if hasattr(serializer, 'instance') and serializer.instance and not serializer.instance.pk:
#                     instance = serializer.instance
#                     for key, value in save_kwargs.items():
#                         setattr(instance, key, value)
#                     instance.save()
#                     serializer.instance = instance
#                 else:
#                     # Обычное сохранение
#                     serializer.save(**save_kwargs)
#             else:
#                 # Для всех остальных моделей - обычное сохранение
#                 serializer.save(**save_kwargs)

#             logger.info(f"✅ Created {serializer.Meta.model.__name__} for store {current_store.name}")

#         except Exception as e:
#             logger.error(f"❌ Error creating {serializer.Meta.model.__name__}: {str(e)}")
#             raise

#     def perform_update(self, serializer):
#         """Проверяем принадлежность к магазину при обновлении"""
#         instance = self.get_object()
#         current_store = self.get_current_store()

#         if hasattr(instance, 'store') and current_store:
#             if instance.store != current_store:
#                 raise PermissionDenied("Вы не можете редактировать данные другого магазина")

#         serializer.save()

#     def perform_destroy(self, instance):
#         """Проверяем принадлежность к магазину при удалении"""
#         current_store = self.get_current_store()

#         if hasattr(instance, 'store') and current_store:
#             if instance.store != current_store:
#                 raise PermissionDenied("Вы не можете удалять данные другого магазина")

#         instance.delete()
class StoreViewSetMixin:
    """
    Миксин для ViewSet'ов с автоматической фильтрацией по магазину
    """
    def get_current_store(self):
        """Получить текущий магазин с резервными способами"""
        user = self.request.user

        # Способ 1: Из атрибутов пользователя (установлено middleware)
        if hasattr(user, 'current_store') and user.current_store:
            # ✅ ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: есть ли у пользователя доступ к этому магазину
            if self._user_has_access_to_store(user, user.current_store):
                logger.debug(f"✅ Store from user attribute: {user.current_store.name}")
                return user.current_store
            else:
                logger.warning(f"⚠️ User {user.username} has no access to store {user.current_store.name}")

        # Способ 2: Через Employee модель
        if hasattr(user, 'employee') and user.employee and user.employee.store:
            store = user.employee.store
            if self._user_has_access_to_store(user, store):
                logger.debug(f"✅ Store from Employee model: {store.name}")
                user.current_store = store
                return store

        # Способ 3: Из JWT токена напрямую
        try:
            auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                from rest_framework_simplejwt.tokens import AccessToken
                decoded_token = AccessToken(token)
                store_id = decoded_token.get('store_id')

                if store_id:
                    from stores.models import Store
                    store = Store.objects.get(id=store_id, is_active=True)

                    # ✅ ПРОВЕРЯЕМ ДОСТУП К МАГАЗИНУ ИЗ ТОКЕНА
                    if self._user_has_access_to_store(user, store):
                        logger.debug(f"✅ Store from JWT token: {store.name}")
                        user.current_store = store
                        return store
                    else:
                        logger.warning(f"⚠️ User {user.username} has no access to store from JWT: {store.name}")

        except Exception as e:
            logger.debug(f"Failed to get store from JWT: {e}")

        # ✅ ИСПРАВЛЕНО: Способ 4 - Берем ПЕРВЫЙ ДОСТУПНЫЙ магазин пользователя
        accessible_stores = self._get_user_accessible_stores(user)
        if accessible_stores:
            first_store = accessible_stores.first()
            logger.debug(f"✅ Using first accessible store: {first_store.name}")
            user.current_store = first_store
            return first_store

        logger.warning(f"❌ No accessible stores found for user {user.username}")
        return None

    def _user_has_access_to_store(self, user, store):
        """Проверяет, есть ли у пользователя доступ к конкретному магазину"""
        from stores.models import StoreEmployee

        return StoreEmployee.objects.filter(
            user=user,
            store=store,
            is_active=True
        ).exists()

    def _get_user_accessible_stores(self, user):
        """Получает все магазины, к которым у пользователя есть доступ"""
        from stores.models import StoreEmployee, Store

        # Получаем ID магазинов, где пользователь является активным сотрудником
        accessible_store_ids = StoreEmployee.objects.filter(
            user=user,
            is_active=True
        ).values_list('store_id', flat=True)

        # Возвращаем только активные магазины
        return Store.objects.filter(
            id__in=accessible_store_ids,
            is_active=True
        )

    def get_queryset(self):
        """Автоматически фильтруем по магазину"""
        queryset = super().get_queryset()

        # Проверяем, что модель поддерживает магазины
        if not hasattr(queryset.model, 'store'):
            logger.debug(f"Model {queryset.model.__name__} doesn't have store field, skipping filter")
            return queryset

        # Получаем текущий магазин
        current_store = self.get_current_store()

        if current_store:
            queryset = queryset.filter(store=current_store)
            logger.debug(f"✅ Filtered queryset by store: {current_store.name}")
        else:
            # ✅ ИСПРАВЛЕНО: Если магазин не найден, возвращаем пустой queryset
            logger.warning(f"⚠️ No store found for {queryset.model.__name__}, returning empty queryset")
            queryset = queryset.none()

        return queryset

    def perform_create(self, serializer):
        """✅ ИСПРАВЛЕННОЕ создание с правильным порядком операций"""
        current_store = self.get_current_store()

        if not current_store:
            logger.error(f"❌ Cannot create {serializer.Meta.model.__name__}: no store found")
            raise ValidationError({
                'non_field_errors': ['Магазин не определен. Переавторизуйтесь или выберите магазин.'],
                'debug_info': {
                    'user_id': self.request.user.id,
                    'username': self.request.user.username,
                    'accessible_stores': list(self._get_user_accessible_stores(self.request.user).values_list('name', flat=True))
                }
            })

        # Подготавливаем данные для сохранения
        save_kwargs = {'store': current_store}

        # Дополнительные поля
        if hasattr(serializer.Meta.model, 'created_by'):
            save_kwargs['created_by'] = self.request.user

        if hasattr(serializer.Meta.model, 'cashier'):
            save_kwargs['cashier'] = self.request.user

        try:
            # ✅ ВАЖНО: Для Product - особый случай
            if serializer.Meta.model.__name__ == 'Product':
                # Если instance уже создан в serializer.create(), просто дополняем его
                if hasattr(serializer, 'instance') and serializer.instance and not serializer.instance.pk:
                    instance = serializer.instance
                    for key, value in save_kwargs.items():
                        setattr(instance, key, value)
                    instance.save()
                    serializer.instance = instance
                else:
                    # Обычное сохранение
                    serializer.save(**save_kwargs)
            else:
                # Для всех остальных моделей - обычное сохранение
                serializer.save(**save_kwargs)

            logger.info(f"✅ Created {serializer.Meta.model.__name__} for store {current_store.name}")

        except Exception as e:
            logger.error(f"❌ Error creating {serializer.Meta.model.__name__}: {str(e)}")
            raise

    def perform_update(self, serializer):
        """Проверяем принадлежность к магазину при обновлении"""
        instance = self.get_object()
        current_store = self.get_current_store()

        if hasattr(instance, 'store') and current_store:
            if instance.store != current_store:
                raise PermissionDenied("Вы не можете редактировать данные другого магазина")

        serializer.save()

    def perform_destroy(self, instance):
        """Проверяем принадлежность к магазину при удалении"""
        current_store = self.get_current_store()

        if hasattr(instance, 'store') and current_store:
            if instance.store != current_store:
                raise PermissionDenied("Вы не можете удалять данные другого магазина")

        instance.delete()

class StoreSerializerMixin:
    """
    Миксин для сериализаторов - убирает store из полей
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Убираем поле store из сериализатора, если оно есть
        if 'store' in self.fields:
            self.fields.pop('store')




class StorePermissionMixin:
    """
    Миксин для проверки прав доступа на основе роли в магазине
    """
    def has_store_permission(self, user, permission_name):
        """Проверяет, есть ли у пользователя разрешение в текущем магазине"""
        if not hasattr(user, 'current_store') or not user.current_store:
            return False

        from .models import StoreEmployee
        try:
            membership = StoreEmployee.objects.get(
                user=user,
                store=user.current_store,
                is_active=True
            )
            return getattr(membership, permission_name, False)
        except StoreEmployee.DoesNotExist:
            return False

    def check_store_permission(self, user, permission_name):
        """Проверяет разрешение и выбрасывает исключение если нет доступа"""
        if not self.has_store_permission(user, permission_name):
            raise PermissionDenied(f"У вас нет разрешения: {permission_name}")