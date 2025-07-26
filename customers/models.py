from django.db import models
from django.core.validators import MinValueValidator

class Customer(models.Model):
    full_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Полное имя")
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name="Телефон")
    total_spent = models.PositiveIntegerField(default=0, verbose_name="Всего потрачено")
    debts_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Количество транзакций с долгом',
        validators=[MinValueValidator(0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Покупатель"
        verbose_name_plural = "Покупатели"

    def __str__(self):
        return self.full_name or self.phone or "Анонимный покупатель"

    @property
    def total_debt(self):
        """Текущая сумма всех непогашенных долгов"""
        return self.debts.aggregate(total=models.Sum('amount'))['total'] or 0

    def update_debt_stats(self):
        """Обновляет статистику по долгам"""
        self.debts_count = self.debts.count()
        self.total_spent = self.debts.aggregate(total=models.Sum('amount'))['total'] or 0
        self.save()



class CustomerDebt(models.Model):
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.CASCADE,
        related_name='debts',
        verbose_name='Покупатель'
    )
    transaction = models.ForeignKey(
        'sales.Transaction',
        on_delete=models.CASCADE,
        related_name='debts',
        null=True,
        blank=True,
        verbose_name='Транзакция'
    )
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(0)],
        verbose_name='Сумма долга'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    
    class Meta:
        verbose_name = "Долг покупателя"
        verbose_name_plural = "Долги покупателей"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer.full_name} - {self.amount} (долг)"