# stores/mixins.py
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
        editable=False  # Не редактируется через формы
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
        """Фильтрация по магазину пользователя из токена"""
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


class StoreViewSetMixin:
    """
    Миксин для ViewSet'ов с автоматической фильтрацией по магазину из JWT
    """
    def get_queryset(self):
        """Автоматически фильтруем по магазину из JWT токена"""
        queryset = super().get_queryset()

        # Получаем магазин из токена (установлен в middleware)
        if hasattr(self.request.user, 'current_store'):
            store = self.request.user.current_store
            if store:
                # Фильтруем только если у модели есть поле store
                if hasattr(queryset.model, 'store'):
                    queryset = queryset.filter(store=store)
                    logger.debug(f"Filtered queryset for store: {store.name}")
            else:
                # Если магазин не определен, возвращаем пустой queryset
                logger.warning(f"No store found for user {self.request.user.username}")
                queryset = queryset.none()
        else:
            # Для неаутентифицированных пользователей
            queryset = queryset.none()

        return queryset

    def perform_create(self, serializer):
        """Автоматически добавляем магазин из JWT токена при создании"""
        if not hasattr(self.request.user, 'current_store') or not self.request.user.current_store:
            raise ValidationError({
                'error': 'Магазин не определен. Переавторизуйтесь или выберите магазин.'
            })

        # Добавляем магазин к данным
        save_kwargs = {'store': self.request.user.current_store}

        # Если модель имеет поле created_by, добавляем пользователя
        if hasattr(serializer.Meta.model, 'created_by'):
            save_kwargs['created_by'] = self.request.user

        # Если модель имеет поле cashier (для транзакций)
        if hasattr(serializer.Meta.model, 'cashier'):
            save_kwargs['cashier'] = self.request.user

        serializer.save(**save_kwargs)
        logger.info(f"Created {serializer.Meta.model.__name__} for store {self.request.user.current_store.name}")

    def perform_update(self, serializer):
        """Проверяем, что обновляемый объект принадлежит текущему магазину"""
        instance = self.get_object()

        if hasattr(instance, 'store'):
            if instance.store != self.request.user.current_store:
                raise PermissionDenied("Вы не можете редактировать данные другого магазина")

        serializer.save()

    def perform_destroy(self, instance):
        """Проверяем, что удаляемый объект принадлежит текущему магазину"""
        if hasattr(instance, 'store'):
            if instance.store != self.request.user.current_store:
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

    def validate(self, attrs):
        """Дополнительная валидация с учетом магазина"""
        attrs = super().validate(attrs)

        request = self.context.get('request')
        if request and hasattr(request.user, 'current_store'):
            # Можно добавить дополнительные проверки здесь
            pass

        return attrs


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