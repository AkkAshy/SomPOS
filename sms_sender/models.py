from django.db import models

class SMS_Template(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Название шаблона")
    content = models.TextField(help_text="Содержимое SMS-шаблона")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SMS Шаблон"
        verbose_name_plural = "SMS Шаблоны"
        ordering = ['-created_at']

    def __str__(self):
        return self.name