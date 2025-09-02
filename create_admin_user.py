import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sompos.settings")
django.setup()

from django.contrib.auth.models import User, Group
from users.models import Employee

user = User.objects.get(username="admin")

group, _ = Group.objects.get_or_create(name="admin")
user.groups.add(group)

Employee.objects.create(
    user=user,
    role="admin",
    phone="+998905755748",
    photo=None
)

print("✅ Исправлено!")
