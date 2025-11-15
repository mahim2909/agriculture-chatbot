from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_view, name='chat'),
    path('process-voice/', views.process_voice, name='process_voice'),
]
