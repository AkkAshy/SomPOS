# analytics/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from inventory.models import Product, ProductCategory
from sales.models import Transaction
from customers.models import Customer
import logging
from django.contrib.auth.models import User


logger = logging.getLogger('analytics')

class SalesSummary(models.Model):
    """
    Агрегированная статистика по продажам за день.
    Храним данные по дням, чтобы снизить нагрузку на запросы.
    """
    date = models.DateField(verbose_name=_("Дата"))
    cashier = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Кассир",
        related_name="sales_summaries"
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        verbose_name=_("Общая сумма продаж")
    )
    total_transactions = models.PositiveIntegerField(
        default=0, verbose_name=_("Количество транзакций")
    )
    total_items_sold = models.PositiveIntegerField(
        default=0, verbose_name=_("Количество проданных товаров")
    )
    payment_method = models.CharField(
        max_length=20, choices=Transaction.PAYMENT_METHODS,
        verbose_name=_("Метод оплаты")
    )

    class Meta:
        verbose_name = _("Сводка по продажам")
        verbose_name_plural = _("Сводки по продажам")
        unique_together = ('date', 'payment_method')
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - {self.get_payment_method_display()} ({self.total_amount})"


class ProductAnalytics(models.Model):
    """
    Статистика по товарам: сколько продано, выручка, популярность.
    """
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='analytics',
        verbose_name=_("Товар")
    )
    cashier = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="product_analytics"
    )
    date = models.DateField(verbose_name=_("Дата"))
    quantity_sold = models.PositiveIntegerField(
        default=0, verbose_name=_("Продано единиц")
    )
    revenue = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        verbose_name=_("Выручка")
    )

    class Meta:
        verbose_name = _("Аналитика товара")
        verbose_name_plural = _("Аналитика товаров")
        unique_together = ('product', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.product.name} - {self.date} ({self.quantity_sold} шт.)"


class CustomerAnalytics(models.Model):
    """
    Статистика по клиентам: покупки, долги, лояльность.
    """
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='analytics',
        verbose_name=_("Клиент")
    )
    cashier = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="customer_analytics"
    )
    date = models.DateField(verbose_name=_("Дата"))
    total_purchases = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        verbose_name=_("Сумма покупок")
    )
    transaction_count = models.PositiveIntegerField(
        default=0, verbose_name=_("Количество транзакций")
    )
    debt_added = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        verbose_name=_("Добавлено долга")
    )

    class Meta:
        verbose_name = _("Аналитика клиента")
        verbose_name_plural = _("Аналитика клиентов")
        unique_together = ('customer', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.customer.full_name} - {self.date} ({self.total_purchases})"