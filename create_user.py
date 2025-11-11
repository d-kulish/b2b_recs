#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User

# Create superuser
username = 'dkulish'
email = 'dkulish@example.com'
password = 'admin123'  # Change this to your preferred password

if User.objects.filter(username=username).exists():
    print(f"User '{username}' already exists!")
    user = User.objects.get(username=username)
    user.set_password(password)
    user.save()
    print(f"Password updated for '{username}'")
else:
    user = User.objects.create_superuser(username=username, email=email, password=password)
    print(f"Superuser '{username}' created successfully!")

print(f"\nLogin credentials:")
print(f"Username: {username}")
print(f"Password: {password}")
print(f"\nYou can now log in at http://127.0.0.1:8000/")
