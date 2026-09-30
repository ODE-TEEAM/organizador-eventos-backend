from rest_framework import serializers
from .models import Evento, Subtarea


class SubtareaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subtarea
        fields = '__all__'
        extra_kwargs = {
            'nombre': {
                'required': True,
                'error_messages': {
                    'required': 'El nombre de la subtarea es obligatorio.',
                    'blank': 'El nombre de la subtarea no puede estar vacío.'
                }
            },
            'plazo': {
                'required': True,
                'error_messages': {
                    'required': 'El plazo de la subtarea es obligatorio.',
                    'invalid': 'El plazo no tiene un formato de fecha válido.'
                }
            },
            'horas_estimadas': {
                'required': True,
                'error_messages': {
                    'required': 'Las horas estimadas son obligatorias.',
                    'invalid': 'Las horas estimadas deben ser un número válido.'
                }
            },
            'evento': {
                'read_only': True
            },
        }

    def validate_horas_estimadas(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError(
                'Las horas estimadas deben ser mayores a 0.'
            )
        return value


class EventoSerializer(serializers.ModelSerializer):
    subtareas = SubtareaSerializer(many=True, read_only=True)

    class Meta:
        model = Evento
        fields = '__all__'
        extra_kwargs = {
            'organizador': {'read_only': True},
            'nombre': {
                'required': True,
                'error_messages': {
                    'required': 'El nombre del evento es obligatorio.',
                    'blank': 'El nombre del evento no puede estar vacio.'
                }
            },
            'tipo': {
                'required': True,
                'error_messages': {
                    'required': 'El tipo de evento es obligatorio.',
                    'blank': 'El tipo de evento no puede estar vacio.'
                }
            },
            'cliente': {
                'required': True,
                'error_messages': {
                    'required': 'El cliente es obligatorio.',
                    'blank': 'El cliente no puede estar vacio.'
                }
            },
            'fecha_hora': {
                'required': True,
                'error_messages': {
                    'required': 'La fecha y hora del evento son obligatorias.',
                    'invalid': 'La fecha y hora no tienen un formato válido.'
                }
            },
            'lugar': {
                'required': True,
                'error_messages': {
                    'required': 'El lugar del evento es obligatorio.',
                    'blank': 'El lugar no puede estar vacío.'
                }
            },
            'plazo_limite': {
                'required': True,
                'error_messages': {
                    'required': 'El plazo límite es obligatorio.',
                    'invalid': 'El plazo límite no tiene un formato valido.'
                }
            },
        }


# ===== Serializers de la vista /hoy (C5) =====
# Estos serializers describen el contrato request/response del endpoint /api/hoy/
# para que drf-spectacular genere el schema en /api/docs/ (Swagger).

class HoyQuerySerializer(serializers.Serializer):
    """Parámetros de consulta (query params) aceptados por GET /api/hoy/."""
    evento = serializers.IntegerField(
        required=False,
        help_text='Filtra las gestiones por el id del evento (ej. ?evento=3).'
    )
    estado = serializers.CharField(
        required=False,
        help_text=(
            'Filtra las gestiones por estado: pendiente, en_progreso o completada '
            '(ej. ?estado=pendiente). Sin este filtro solo se listan gestiones activas '
            '(se excluyen las completadas).'
        )
    )


class GestionHoySerializer(serializers.Serializer):
    """Una gestión (subtarea) ya clasificada dentro de un grupo de prioridad."""
    id = serializers.IntegerField()
    titulo = serializers.CharField()
    evento = serializers.CharField(help_text='Nombre del evento al que pertenece.')
    evento_id = serializers.IntegerField()
    estado = serializers.CharField(help_text='pendiente | en_progreso | completada')
    prioridad = serializers.CharField(help_text='alta | media | baja')
    fecha = serializers.DateField(help_text='Plazo de la gestión (YYYY-MM-DD).')
    horas_estimadas = serializers.DecimalField(max_digits=5, decimal_places=2)
    grupo = serializers.CharField(help_text='vencidas | para_hoy | proximas')


class ResumenHoySerializer(serializers.Serializer):
    """Contadores usados por las tarjetas resumen de la vista /hoy."""
    total = serializers.IntegerField(help_text='Gestiones activas devueltas (vencidas + para_hoy + proximas).')
    vencidas = serializers.IntegerField()
    para_hoy = serializers.IntegerField()
    proximas = serializers.IntegerField()
    completadas = serializers.IntegerField(help_text='Gestiones completadas dentro del alcance del filtro.')


class HoyResponseSerializer(serializers.Serializer):
    """Respuesta agrupada de GET /api/hoy/."""
    fecha_referencia = serializers.DateField(help_text='Fecha usada como "hoy" para clasificar.')
    resumen = ResumenHoySerializer()
    vencidas = GestionHoySerializer(many=True)
    para_hoy = GestionHoySerializer(many=True)
    proximas = GestionHoySerializer(many=True)