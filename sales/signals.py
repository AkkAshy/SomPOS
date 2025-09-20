# sales/signals.py - УЛУЧШЕННАЯ ВЕРСИЯ
from django.db.models.signals import post_save
from django.dispatch import receiver

from django.db.models import F
from sales.models import Transaction, TransactionHistory
from analytics.models import CashRegister
from django.apps import apps
import logging
import json
from django.utils import timezone

logger = logging.getLogger('sales')

@receiver(post_save, sender=Transaction, dispatch_uid="transaction_history_signal")
def create_transaction_history(sender, instance, created, **kwargs):
    """
    ✅ ЕДИНСТВЕННАЯ задача: создание истории транзакций
    Аналитика обрабатывается в analytics/signals.py
    """

    # Определяем действие
    if created:
        action = 'created'
    else:
        action = instance.status

    # Записываем только важные события (расширили для кассы)
    important_actions = ['created', 'completed', 'refunded', 'cash_added', 'cash_withdrawn']
    if action not in important_actions:
        return

    # Проверяем что у транзакции есть store
    if not hasattr(instance, 'store') or not instance.store:
        logger.error(f"❌ Transaction {instance.id} has no store, cannot create history")
        return

    # Проверяем, не существует ли уже такая запись
    existing_record = TransactionHistory.objects.filter(
        transaction=instance,
        action=action
    ).first()

    if existing_record:
        logger.info(f"📝 History record already exists for transaction {instance.id}, action {action}")
        # Обновляем детали на всякий случай
        details = _build_transaction_details(instance)
        existing_record.details = json.dumps(details, ensure_ascii=False)
        existing_record.save()
        return

    # Создаем новую запись истории
    details = _build_transaction_details(instance)

    try:
        TransactionHistory.objects.create(
            transaction=instance,
            action=action,
            details=json.dumps(details, ensure_ascii=False),
            store=instance.store
        )
        logger.info(f"✅ Created transaction history for {instance.id} with action '{action}' in store {instance.store.name}")
    except Exception as e:
        logger.error(f"❌ Error creating transaction history for {instance.id}: {str(e)}")


def _build_transaction_details(instance):
    """Создает детали транзакции для записи в историю"""
    try:
        items = [
            {
                'product': item.product.name,
                'quantity': str(item.quantity),
                'price': str(item.price),
                'subtotal': str(item.quantity * item.price),
                'unit_display': item.unit_display or 'шт',
                'size': item.size_snapshot.get('size') if item.size_snapshot else None
            }
            for item in instance.items.all()
        ]
    except Exception as e:
        logger.error(f"Error building items for transaction {instance.id}: {str(e)}")
        items = []

    # Добавляем информацию о кассе
    cash_info = {}
    if hasattr(instance, 'cash_register') and instance.cash_register:
        cash_info = {
            'cash_register_id': instance.cash_register.id,
            'cash_register_balance': str(instance.cash_register.current_balance),
            'cash_register_opened': instance.cash_register.date_opened.isoformat()
        }

    return {
        'transaction_id': instance.id,
        'total_amount': str(instance.total_amount),
        'cash_amount': str(getattr(instance, 'cash_amount', 0)),
        'payment_method': instance.payment_method,
        'cashier': instance.cashier.username if instance.cashier else None,
        'customer': instance.customer.full_name if instance.customer else None,
        'items_count': len(items),
        'items': items,
        'store_id': str(instance.store.id),
        'store_name': instance.store.name,
        'cash_info': cash_info  # ✅ Касса в деталях!
    }



@receiver(post_save, sender=Transaction)
def update_cash_register_on_transaction(sender, instance: Transaction, created, **kwargs):
    """
    Обновляет баланс кассы после продажи.
    Работает только для completed транзакций.
    Логика:
    - Если метод оплаты "cash", добавляем всю сумму в кассу.
    - Если "hybrid", добавляем только cash_amount.
    - Если "card", "transfer" или "debt", не трогаем кассу.
    """
    print("Signal: update_cash_register_on_transaction triggered")
    if not created:  # только новые продажи
        return
    
    if instance.status != "completed":
        return

    cash_register = instance.cash_register
    if not cash_register:
        return

    # === Логика для разных методов оплаты ===
    if instance.payment_method == "cash":
        cash_register.balance = F("balance") + instance.total_amount
    elif instance.payment_method == "hybrid":
        if instance.cash_amount > 0:
            cash_register.balance = F("balance") + instance.cash_amount
        # остальное (карта/перевод) идёт в банк, но не в кассу
    else:
        # карта, перевод, долг → не трогаем кассу
        return

    cash_register.save(update_fields=["balance"])