# sales/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Transaction, TransactionHistory
from customers.models import Customer
import json

@receiver(post_save, sender=Transaction)
def log_transaction(sender, instance, created, **kwargs):
    """
    ИСПРАВЛЕННАЯ версия - создает записи только когда нужно
    """
    # Определяем действие
    if created:
        action = 'created'
    else:
        action = instance.status

    # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Проверяем не существует ли уже такая запись
    existing_record = TransactionHistory.objects.filter(
        transaction=instance,
        action=action
    ).first()

    if existing_record:
        # Запись уже есть - обновляем её данные вместо создания новой
        details = {
            'total_amount': str(instance.total_amount),
            'payment_method': instance.payment_method,
            'cashier': instance.cashier.username if instance.cashier else None,
            'customer': instance.customer.full_name if instance.customer else None,
            'items': [
                {
                    'product': item.product.name,
                    'quantity': item.quantity,
                    'price': str(item.price)
                }
                for item in instance.items.all()
            ]
        }
        existing_record.details = json.dumps(details, ensure_ascii=False)
        existing_record.save()
        return  # Выходим, не создаем новую запись

    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Создаем записи только для важных событий
    important_actions = ['created', 'completed', 'refunded']
    if action not in important_actions:
        return  # Пропускаем промежуточные статусы

    # Создаем новую запись только если её еще нет
    details = {
        'total_amount': str(instance.total_amount),
        'payment_method': instance.payment_method,
        'cashier': instance.cashier.username if instance.cashier else None,
        'customer': instance.customer.full_name if instance.customer else None,
        'items': [
            {
                'product': item.product.name,
                'quantity': item.quantity,
                'price': str(item.price)
            }
            for item in instance.items.all()
        ]
    }

    TransactionHistory.objects.create(
        transaction=instance,
        action=action,
        details=json.dumps(details, ensure_ascii=False)
    )

