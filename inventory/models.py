import logging
from django.db import models
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum, F
from django.conf import settings
from django.utils.text import format_lazy
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import barcode
from io import BytesIO
from barcode.writer import ImageWriter
from PIL import Image as PILImage
from io import BytesIO
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from stores.mixins import StoreOwnedModel, StoreOwnedManager


pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
addMapping('DejaVuSans', 0, 0, 'DejaVuSans')
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('inventory')


class SizeInfo(models.Model):
    SIZE_CHOICES = [
        ('S', 'S'),
        ('M', 'M'),
        ('L', 'L'),
        ('XL', 'XL'),
        ('XXL', 'XXL'),
    ]



    size = models.CharField(max_length=50, verbose_name="Размер")

    chest = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        null=True,
        blank=True,
        verbose_name="Обхват груди"
    )
    waist = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        null=True,
        blank=True,
        verbose_name="Обхват талии"
    )
    length = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        null=True,
        blank=True,
        verbose_name="Длина"
    )


    class Meta:
        verbose_name = "Размерная информация"
        verbose_name_plural = "Размерные информации"
        unique_together = ('size',)

    def __str__(self):
        return f"{self.size}"


class ProductCategory(StoreOwnedModel):
    name = models.CharField(max_length=255, unique=True, verbose_name="Название")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    objects = StoreOwnedManager()
    class Meta:
        verbose_name = "Категория товара"
        verbose_name_plural = "Категории товаров"
        ordering = ['name']
        unique_together = ['store', 'name']

    def __str__(self):
        return self.name


class AttributeType(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="Слаг")
    is_filterable = models.BooleanField(default=False, verbose_name="Фильтруемый ли?")

    class Meta:
        verbose_name = "Тип атрибута"
        verbose_name_plural = "Типы атрибутов"
        ordering = ['name']

    def __str__(self):
        return self.name


class AttributeValue(models.Model):
    attribute_type = models.ForeignKey(
        AttributeType,
        on_delete=models.CASCADE,
        related_name='values',
        verbose_name="Тип атрибута"

    )
    value = models.CharField(max_length=225, verbose_name="Значение")
    slug = models.SlugField(max_length=225, unique=True, verbose_name="Слаг")
    ordering = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Значение атрибута"
        verbose_name_plural = "Значения атрибутов"
        ordering = ['ordering', 'value']
        unique_together = ('attribute_type', 'slug')

    def __str__(self):
        return f"{self.attribute_type.name}: {self.value} ({self.slug})"

class Product(StoreOwnedModel):
    UNIT_CHOICES = [
        ('piece', 'Штука')
    ]
    name = models.CharField(max_length=255, verbose_name="Название")


    barcode = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Штрих-код"
    )
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name="Категория"
    )
    unit = models.CharField(
        max_length=50,
        choices=UNIT_CHOICES,
        default='piece',
        verbose_name="Единица измерения"
    )
    sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)],
        verbose_name="Цена продажи"
    )
    attributes = models.ManyToManyField(
        AttributeValue,
        blank=True,
        related_name='products',
        verbose_name="Атрибуты"
    )
    size = models.ForeignKey(SizeInfo, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    image_label = models.ImageField(
        upload_to='product_labels/',
        null=True,
        blank=True,
        verbose_name="Изображение этикетки"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products_created',
        verbose_name="Создан пользователем"
    )
    objects = StoreOwnedManager()

    @classmethod
    def generate_unique_barcode(cls):
        import uuid
        import random
        import time
        """Генерирует уникальный штрих-код"""
        max_attempts = 100
        attempts = 0

        while attempts < max_attempts:

            timestamp = str(int(time.time()))[-6:]  # 6 последних цифр времени

            random_part = str(random.randint(100000, 999999))  # 6 случайных цифр

            barcode_code = timestamp + random_part

            checksum = cls()._calculate_ean13_checksum(barcode_code)

            full_ean = barcode_code + checksum
            # Проверяем уникальность в базе
            if not cls.objects.filter(barcode=full_ean).exists():
                return full_ean
            attempts += 1

        data12 = str(uuid.uuid4().int)[:12]
        return data12 + cls()._calculate_ean13_checksum(data12)

    def _calculate_ean13_checksum(self, digits):
        """Вычисляет контрольную цифру EAN-13"""
        weights = [1, 3] * 6
        total = sum(int(d) * w for d, w in zip(digits, weights))
        return str((10 - (total % 10)) % 10)

    def _generate_barcode_image(self, barcode_str):
        """Генерирует изображение штрих-кода (размер 700x200, без текста)"""
        barcode_str = str(barcode_str).strip().zfill(12)[:12]
        full_ean = barcode_str + self._calculate_ean13_checksum(barcode_str)

        writer = ImageWriter()
        writer.set_options({
            'module_height': 20.0,    # Высота полосок
            'module_width': 0.4,      # Ширина полосок
            'quiet_zone': 0.0,        # Без отступов
            'font_size': 0,           # Отключаем шрифт
            'write_text': False,      # Явно отключаем текст
            'text_distance': 0.0,     # Убираем расстояние для текста
            'dpi': 600,               # Качество изображения
        })

        ean = barcode.get_barcode_class('ean13')
        buffer = BytesIO()
        try:
            ean(full_ean, writer=writer).write(buffer)
            buffer.seek(0)

            barcode_img = PILImage.open(buffer)

            # Убираем белые поля и область текста
            bbox = barcode_img.getbbox()
            if bbox:
                width, height = barcode_img.size
                crop_box = (bbox[0], bbox[1], bbox[2], int(height * 0.7))
                barcode_img = barcode_img.crop(crop_box)

            # Масштабируем до размера 700x200
            target_size = (700, 200)
            barcode_img = barcode_img.resize(target_size, PILImage.Resampling.LANCZOS)

            return barcode_img
        finally:
            buffer.close()

    def _create_label_bytes(self, barcode_img):
        """Создаёт байты изображения"""
        buffer = BytesIO()
        barcode_img.save(buffer, format="PNG", quality=95)
        buffer.seek(0)
        label_bytes = buffer.getvalue()
        buffer.close()
        return label_bytes

    def generate_label(self):
        """Основной метод генерации этикетки"""
        if not self.barcode:
            logger.warning("Штрих-код отсутствует - этикетка не будет создана")
            return False

        try:
            barcode_img = self._generate_barcode_image(self.barcode)
            label_bytes = self._create_label_bytes(barcode_img)

            label_filename = f'product_{self.id}_label.png'

            # Удаляем старый файл, если он существует
            if self.image_label:
                self.image_label.delete(save=False)

            # Сохраняем новый файл
            self.image_label.save(label_filename, ContentFile(label_bytes), save=False)
            super().save(update_fields=['image_label'])
            return True
        except Exception as e:
            logger.error(f"Ошибка генерации этикетки: {str(e)}", exc_info=True)
            return False

    def save(self, *args, **kwargs):
        """Переопределяем save для автогенерации штрихкода и этикетки"""
        is_new = self._state.adding
        update_fields = kwargs.get('update_fields')

        # Если обновляем только image_label, просто сохраняем
        if update_fields and update_fields == ['image_label']:
            super().save(*args, **kwargs)
            return

        # Генерируем штрихкод, если его нет
        if is_new and not self.barcode:
            self.barcode = self.generate_unique_barcode()

        # Сохраняем объект, чтобы получить self.id
        super().save(*args, **kwargs)

        # Генерируем этикетку для нового объекта или если штрихкод изменился
        if is_new or (update_fields and 'barcode' in update_fields):
            self.generate_label()

    def clean(self):
        """Валидация перед сохранением"""
        super().clean()
        if self.barcode:
            barcode_str = str(self.barcode).strip()
            if not barcode_str.isdigit():
                raise ValidationError({'barcode': "Штрих-код должен содержать только цифры."})

    def __str__(self):
        return f"{self.name} ({self.get_unit_display()})"

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        indexes = [
            models.Index(fields=['name', 'barcode']),
            models.Index(fields=['store', 'name']),  # ← ДОБАВИТЬ
            models.Index(fields=['store', 'barcode']),  # ← ДОБАВИТЬ
        ]
        unique_together = ['store', 'barcode']


class ProductAttribute(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='product_attributes',
        verbose_name="Товар"
    )
    attribute_value = models.ForeignKey(
        AttributeValue,
        on_delete=models.CASCADE,
        related_name='product_attributes',
        verbose_name="Значение атрибута"
    )

    class Meta:
        verbose_name = "Атрибут товара"
        verbose_name_plural = "Атрибуты товаров"
        unique_together = ('product', 'attribute_value')

    def __str__(self):
        return f"{self.product.name} - {self.attribute_value.value}"

class SizeChart(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Таблица размеров"
        verbose_name_plural = "Таблицы размеров"
        ordering = ['name']

    def __str__(self):
        return self.name



class ProductBatch(StoreOwnedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='batches'
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Количество"
    )
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Цена закупки",
    )
    size = models.ForeignKey(
        SizeInfo,  # или как у тебя называется модель размера
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="Размер"
    )
    supplier = models.CharField(max_length=255, blank=True, null=True,  verbose_name="Поставщик")
    expiration_date = models.DateField(null=True, blank=True, verbose_name="Дата истечения")
    created_at = models.DateTimeField(auto_now_add=True)
    objects = StoreOwnedManager()

    class Meta:
        verbose_name = "Партия товара"
        verbose_name_plural = "Партии товаров"
        ordering = ['expiration_date', 'created_at']  # FIFO по умолчанию

    def sell(self, quantity):
        if quantity > self.quantity:
            raise ValueError(
                f"Недостаточно товара в партии. Доступно: {self.quantity}, запрошено: {quantity}"
            )
        self.quantity = F('quantity') - quantity
        self.save(update_fields=['quantity'])
        self.refresh_from_db()

        if self.quantity == 0:
            self.delete()
            logger.info(f"Партия {self.id} удалена (товар {self.product.name})")

        return quantity

    def __str__(self):
        return f"{self.product.name} × {self.quantity} (поставщик: {self.supplier})"

class Stock(StoreOwnedModel):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='stock',
        verbose_name="Товар"
    )
    quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Количество"
    )
    updated_at = models.DateTimeField(auto_now=True)
    objects = StoreOwnedManager()
    class Meta:
        verbose_name = "Остаток на складе"
        verbose_name_plural = "Остатки на складе"

    def update_quantity(self):
        """Обновляет общее количество товара на основе партий"""
        total = self.product.batches.aggregate(
            total=Sum('quantity')
        )['total'] or 0
        self.quantity = total
        self.save(update_fields=['quantity', 'updated_at'])

    def sell(self, quantity):
        """Списывает товар по FIFO с обработкой ошибок"""
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным")

        if self.quantity < quantity:
            raise ValueError(
                f"Недостаточно товара '{self.product.name}'. Доступно: {self.quantity}, запрошено: {quantity}"
            )

        remaining = quantity
        batches = self.product.batches.order_by('expiration_date', 'created_at')

        for batch in batches:
            if remaining <= 0:
                break

            sell_amount = min(remaining, batch.quantity)
            batch.sell(sell_amount)
            remaining -= sell_amount

        self.update_quantity()
        logger.info(f"Продано {quantity} {self.product.get_unit_display()} {self.product.name}")

    def __str__(self):
        return f"{self.product.name}: {self.quantity} {self.product.get_unit_display()}"

@receiver(post_save, sender=Product)
def create_product_stock(sender, instance, created, **kwargs):
    """
    Создаем Stock ТОЛЬКО после того как Product полностью сохранен со store
    """
    if created and not hasattr(instance, 'stock'):
        # ✅ ВАЖНО: Проверяем что у Product есть store
        if hasattr(instance, 'store') and instance.store:
            try:
                stock, stock_created = Stock.objects.get_or_create(
                    product=instance,
                    defaults={
                        'store': instance.store,  # ← Берем store из Product
                        'quantity': 0
                    }
                )
                if stock_created:
                    logger.info(f"✅ Stock created for product: {instance.name} in store: {instance.store.name}")
                else:
                    logger.info(f"ℹ️ Stock already exists for product: {instance.name}")
            except Exception as e:
                logger.error(f"❌ Error creating stock for product {instance.name}: {str(e)}")
        else:
            logger.warning(f"⚠️ Cannot create stock for product {instance.name}: no store assigned")

@receiver(post_save, sender=ProductBatch)
def update_stock_on_batch_change(sender, instance, **kwargs):
    """
    Обновляем остатки при изменении партии
    """
    try:
        # Получаем или создаем Stock для продукта
        stock, created = Stock.objects.get_or_create(
            product=instance.product,
            defaults={
                'store': instance.store,  # ← Берем store из ProductBatch
                'quantity': 0
            }
        )
        
        # Обновляем количество
        stock.update_quantity()
        
        if created:
            logger.info(f"✅ Stock created during batch update for: {instance.product.name}")
        else:
            logger.debug(f"✅ Stock updated for: {instance.product.name}")
            
    except Exception as e:
        logger.error(f"❌ Error updating stock for batch {instance.id}: {str(e)}")