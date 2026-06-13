from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('about/', views.about, name='about'),
    path('pricing/', views.pricing, name='pricing'),
    path('support/', views.support, name='support'),
    path('security/', views.security, name='security'),
    path('customers/', views.customers, name='customers'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('api/request-demo/', views.request_demo, name='request_demo'),
]
