# auth/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group

class Employee(models.Model):
    ROLE_CHOICES = (
        ('admin', _('Админ')),
        ('stockkeeper', _('Складчик')),
        ('manager', _('Менеджер')),
        ('cashier', _('Кассир')),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')
    phone = models.CharField(max_length=20, blank=True, null=True)
    photo = models.ImageField(upload_to='employee_photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Сотрудник')
        verbose_name_plural = _('Сотрудники')

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.role})"

@receiver(post_save, sender=Employee)  # Сигнал после сохранения Employee
def assign_group_to_user(sender, instance, created, **kwargs):
    # Получаем или создаём группу, соответствующую роли
    group, _ = Group.objects.get_or_create(name=instance.role)
    # Удаляем пользователя из всех других групп
    instance.user.groups.clear()
    # Добавляем пользователя в группу, соответствующую его роли
    instance.user.groups.add(group)