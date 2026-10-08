from django.urls import path
from .views import (
    health_check,
    login,
    register,
    perfil,
    hoy,
    eventos,
    obtener_evento,
    crear_subtarea,
    actualizar_subtarea,
    configuracion_limite_horas,
)

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('login/', login, name='login'),
    path('register/', register, name='register'),
    path('perfil/', perfil, name='perfil'),
    path('hoy/', hoy, name='hoy'),
    path('eventos/', eventos, name='eventos'),
    path('eventos/<int:evento_id>/', obtener_evento, name='obtener_evento'),
    path('eventos/<int:evento_id>/subtareas/', crear_subtarea, name='crear_subtarea'),
    # C1 Sprint 3: reprogramar / editar una gestión
    path('subtareas/<int:subtarea_id>/', actualizar_subtarea, name='actualizar_subtarea'),
    path('configuracion/limite-horas/', configuracion_limite_horas,name='configuracion_limite_horas'),
]