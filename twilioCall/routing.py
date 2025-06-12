from django.urls import re_path, path

from . import consuemrs
websocket_urlpatterns = [
    path('twilio-stream/', consuemrs.MediaStreamConsumer.as_asgi()),
] 