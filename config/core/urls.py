from django.urls import path
from .views import health_check, eventos, obtener_evento, crear_subtarea
from .views import health_check, eventos, obtener_evento, crear_subtarea, hoy

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('hoy/', hoy, name='hoy'),
    path('eventos/', eventos, name='eventos'),
    path('eventos/<int:evento_id>/', obtener_evento, name='obtener_evento'),
    path('eventos/<int:evento_id>/subtareas/', crear_subtarea, name='crear_subtarea'),
]