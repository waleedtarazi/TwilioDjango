from django.urls import path

from . import views

urlpatterns = [
       path('incoming-call/', views.incoming_call, name='incoming_call'),

]