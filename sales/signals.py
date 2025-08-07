# sales/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Transaction, TransactionHistory
from customers.models import Customer
import json

@receiver(post_save, sender=Transaction)
def log_transaction(sender, instance, created, **kwargs):
    action = 'created' if created else instance.status
    details = {
        'total_amount': str(instance.total_amount),
        'payment_method': instance.payment_method,
        'cashier': instance.cashier.username if instance.cashier else None,
        'customer': instance.customer.full_name if instance.customer else None,
        'items': [
            {'product': item.product.name, 'quantity': item.quantity, 'price': str(item.price)}
            for item in instance.items.all()
        ]
    }
    TransactionHistory.objects.create(
        transaction=instance,
        action=action,
        details=json.dumps(details, ensure_ascii=False)
    )


@receiver(post_save, sender=Transaction)
def update_customer_last_purchase(sender, instance, **kwargs):  # ← ✅ другое имя
    customer = instance.customer
    if customer and instance.status == 'completed':  # ← Можно добавить проверку статуса
        if not customer.last_purchase_date or instance.created_at > customer.last_purchase_date:
            customer.last_purchase_date = instance.created_at
            customer.save(update_fields=['last_purchase_date'])

