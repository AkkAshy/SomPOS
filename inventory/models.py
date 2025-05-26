import os
import logging
from django.db import models
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum


LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')

logger = logging.getLogger('inventory')

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(os.path.join(LOG_DIR, 'pos.log'))]
)



class ProductCategory(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class Product(models.Model):
    UNIT_CHOICES = [('piece', 'Штука'), ('kg', 'Килограмм'), ('liter', 'Литр')]
    name = models.CharField(max_length=255)
    barcode = models.CharField(max_length=100, unique=True, null=True, blank=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT)
    unit = models.CharField(max_length=50, choices=UNIT_CHOICES, default='piece')
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        logger.debug(f"[SomPOS] Saving product: {self.name}")
        super().save(*args, **kwargs)
        logger.info(f"[SomPOS] Product saved: {self.name}")
    def __str__(self): return self.name

class ProductBatch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    expiration_date = models.DateField(null=True, blank=True)  # Срок годности
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        logger.debug(f"[SomPOS] Saving batch for {self.product.name}: {self.quantity}")
        super().save(*args, **kwargs)
        logger.info(f"[SomPOS] Batch saved for {self.product.name}: {self.quantity}, expires: {self.expiration_date}")
        # Обновляем Stock
        self.product.stock.update_quantity()
    
    def __str__(self): return f"{self.product.name}: {self.quantity} (Expires: {self.expiration_date})"

class Stock(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, unique=True)
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    updated_at = models.DateTimeField(auto_now=True)
    
    def update_quantity(self):
        # Суммируем количество из всех партий
        total = self.product.batches.aggregate(total=Sum('quantity'))['total'] or 0
        self.quantity = total
        self.save()
    
    def save(self, *args, **kwargs):
        logger.debug(f"[SomPOS] Updating stock for {self.product.name}: {self.quantity}")
        super().save(*args, **kwargs)
        logger.info(f"[SomPOS] Stock updated for {self.product.name}: {self.quantity}")
    
    def __str__(self): return f"{self.product.name}: {self.quantity}"

@receiver(post_save, sender=Product)
def create_stock(sender, instance, created, **kwargs):
    if created:
        Stock.objects.create(product=instance)
        logging.info(f"[SomPOS] Created stock for product: {instance.name}")