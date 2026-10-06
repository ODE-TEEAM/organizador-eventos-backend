from django.conf import settings
from django.db import models


class Evento(models.Model):
    organizador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='eventos',
        null=True,
        blank=True,
    )
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=50)
    cliente = models.CharField(max_length=200)
    fecha_hora = models.DateTimeField()
    lugar = models.CharField(max_length=200)
    plazo_limite = models.DateField()

    def __str__(self):
        return self.nombre


class Subtarea(models.Model):
    evento = models.ForeignKey(
        Evento,
        on_delete=models.CASCADE,
        related_name='subtareas'
    )
    nombre = models.CharField(max_length=200)
    plazo = models.DateField()
    horas_estimadas = models.DecimalField(max_digits=5, decimal_places=2)
    estado = models.CharField(max_length=20, default='pendiente')

    def __str__(self):
        return self.nombre


class PerfilOrganizador(models.Model):
    """
    C2 Sprint 3: límite diario de horas de gestión por organizador.
    Default 6h. Rango permitido: 1 a 16.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='perfil_organizador',
    )
    limite_horas_diarias = models.PositiveSmallIntegerField(default=6)

    def __str__(self):
        return f'Perfil de {self.user_id} ({self.limite_horas_diarias}h/día)'