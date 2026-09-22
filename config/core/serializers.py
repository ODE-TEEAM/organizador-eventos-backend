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