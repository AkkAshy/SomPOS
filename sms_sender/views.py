import requests
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .models import SMS_Template
from .serializators import SmsSenderSerializer
from rest_framework.views import APIView
from .models import SMS_Template as SmsTemplate
from customers.models import Customer as UserProfile
from django.conf import settings


class SmsSenderViewSet(viewsets.ModelViewSet):
    queryset = SMS_Template.objects.all()
    serializer_class = SmsSenderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


ESKIZ_EMAIL = "asirepovakkanat@gmail.com"
ESKIZ_PASSWORD = "t3sblMZoZDnC5L5Yqx2eZvIeRA6a6FvoP20Gah0F"
ESKIZ_BASE_URL = "https://notify.eskiz.uz/api"


class SendSmsFlexibleView(APIView):
    def get_eskiz_token(self):
        url = f"{ESKIZ_BASE_URL}/auth/login"
        payload = {
            "email": ESKIZ_EMAIL,
            "password": ESKIZ_PASSWORD
        }
        response = requests.post(url, data=payload)
        response.raise_for_status()
        return response.json()["data"]["token"]

    def post(self, request, template_id=None):
        phone = request.data.get("phone")
        text_message = request.data.get("text")

        # Если нет текста, пробуем взять из шаблона
        if not text_message and template_id:
            try:
                template = SmsTemplate.objects.get(id=template_id)
                text_message = template.text
            except SmsTemplate.DoesNotExist:
                return Response({"error": "Template not found"}, status=status.HTTP_404_NOT_FOUND)

        if not text_message:
            return Response({"error": "Text message is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Определяем список получателей
        if phone:
            recipients = [phone]
        else:
            recipients = list(UserProfile.objects.values_list("phone", flat=True))
            if not recipients:
                return Response({"error": "No recipients found"}, status=status.HTTP_404_NOT_FOUND)

        # Получаем токен Eskiz
        try:
            token = self.get_eskiz_token()
        except requests.HTTPError as e:
            return Response({"error": f"Eskiz auth failed: {e}"}, status=status.HTTP_401_UNAUTHORIZED)

        results = []
        for number in recipients:
            payload = {
                'mobile_phone': number,
                'message': 'Это тест от Eskiz',
                'from': '4546',  # короткий код, если у тебя есть
                'callback_url': '',
                'unicode': '0'
            }
            headers = {
                'Authorization': f'Bearer {token}'
            }
            try:
                response = requests.post(f"{ESKIZ_BASE_URL}/message/sms/send", headers=headers, data=payload)
                response.raise_for_status()
                resp_json = response.json()
                results.append({
                    "phone": number,
                    "status": "success",
                    "response": resp_json
                })
            except requests.HTTPError as e:
                results.append({
                    "phone": number,
                    "status": "failed",
                    "error": str(e)
                })

        return Response({"status": "ok", "results": results})