from rest_framework import serializers
from .models import SMS_Template




class SmsSenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMS_Template
        fields = [
            'id', 'name', 'content', 'created_at', 'updated_at'
            ]
        read_only_fields = ['created_at', 'updated_at']


