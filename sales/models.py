# sales/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from inventory.models import Product, Stock
import logging
from stores.mixins import StoreOwnedModel, StoreOwnedManager

logger = logging.getLogger('sales')

class Transaction(StoreOwnedModel):
    PAYMENT_METHODS = [
        ('cash', 'Наличные'),
        ('transfer', 'Перевод'),
        ('card', 'Карта'),
        ('debt', 'В долг'),
    ]

    cashier = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sales_transactions'
    )
    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchases'
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default='cash'
    )
    status = models.CharField(
        max_length=20,
        choices=[('completed', 'Completed'), ('pending', 'Pending'), ('refunded', 'Refunded')],
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = StoreOwnedManager()  # ← ДОБАВИТЬ после полей

    class Meta:
        verbose_name = "Продажа"
        verbose_name_plural = "Продажи"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'created_at']),  # ← ДОБАВИТЬ
        ]

    def __str__(self):
        return f"Продажа #{self.id} от {self.created_at}"

    def process_sale(self):
        """Обрабатывает продажу: списывает товары и обновляет долг, если нужно"""
        if self.status != 'pending':
            raise ValueError("Продажа уже обработана или отменена")

        # Списываем товары со склада
        for item in self.items.all():
            stock = item.product.stock
            stock.sell(item.quantity)  # Используем метод sell из Stock

        # Обрабатываем долг, если способ оплаты — "в долг"
        if self.payment_method == 'debt':
            if not self.customer:
                raise ValueError("Для продажи в долг нужен покупатель")
            self.customer.add_debt(self.total_amount)

        # Обновляем total_spent и loyalty_points
        if self.customer:
            self.customer.total_spent += self.total_amount
            self.customer.loyalty_points += int(self.total_amount // 10)  # 1 балл за 10 рублей
            self.customer.save(update_fields=['total_spent', 'loyalty_points'])

        self.status = 'completed'
        self.save(update_fields=['status'])
        logger.info(f"Продажа #{self.id} завершена: {self.total_amount} ({self.payment_method})")

class TransactionItem(StoreOwnedModel):
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='sale_items'
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    objects = StoreOwnedManager()

    class Meta:
        verbose_name = "Элемент продажи"
        verbose_name_plural = "Элементы продаж"

    def __str__(self):
        return f"{self.product.name} × {self.quantity} в продаже #{self.transaction.id}"

class TransactionHistory(StoreOwnedModel):
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='history'
    )
    action = models.CharField(
        max_length=50,
        choices=[('created', 'Создана'), ('completed', 'Завершена'), ('refunded', 'Возвращена')]
    )
    details = models.TextField()  # JSON или текст с информацией
    created_at = models.DateTimeField(auto_now_add=True)

    objects = StoreOwnedManager()

    class Meta:
        verbose_name = "История продажи"
        verbose_name_plural = "История продаж"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # если магазин не указан → берём из транзакции
        if not self.store_id and self.transaction_id:
            self.store = self.transaction.store
        else:
            # защита: если кто-то попробует подменить
            if self.store_id != self.transaction.store_id:
                raise ValueError("Магазин истории должен совпадать с магазином транзакции")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.action} для продажи #{self.transaction.id} от {self.created_at}"