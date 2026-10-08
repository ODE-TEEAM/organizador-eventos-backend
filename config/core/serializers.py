from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import serializers
from .models import Evento, Subtarea, PerfilOrganizador

# Tope de año para fechas (evita valores absurdos como el año 10000).
ANIO_MAXIMO = 2100
# Rango permitido de horas estimadas por gestión.
HORAS_MINIMAS = 1
HORAS_MAXIMAS = 12


class RegistroSerializer(serializers.Serializer):
    """Crea un organizador a partir de nombre + email + password (usado por POST /api/register/)."""
    nombre = serializers.CharField(
        required=True,
        allow_blank=False,
        min_length=3,
        max_length=150,
        error_messages={
            'required': 'Cuéntanos tu nombre para personalizar tu cuenta.',
            'blank': 'El nombre no puede quedar vacío.',
            'min_length': 'Tu nombre debe tener al menos 3 caracteres.',
            'max_length': 'Tu nombre es muy largo (máximo 150 caracteres).',
        },
    )
    email = serializers.EmailField(
        required=True,
        error_messages={
            'required': 'El correo es obligatorio.',
            'blank': 'El correo no puede estar vacío.',
            'invalid': 'Escribe un correo válido.',
        },
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=6,
        error_messages={
            'required': 'La contraseña es obligatoria.',
            'min_length': 'La contraseña debe tener al menos 6 caracteres.',
        },
    )

    def validate_nombre(self, value):
        value = (value or '').strip()
        if len(value) < 3:
            raise serializers.ValidationError(
                'Tu nombre debe tener al menos 3 caracteres.'
            )
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                'Ese correo ya tiene una cuenta. Prueba iniciando sesión o usa otro correo.'
            )
        return value

    def create(self, validated_data):
        email = validated_data['email']
        # username = email: el inicio de sesión es por correo, no por username.
        # first_name = nombre: es el nombre que mostramos en el saludo y el header.
        return User.objects.create_user(
            username=email,
            email=email,
            first_name=validated_data['nombre'][:150],
            password=validated_data['password'],
        )


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
                    'invalid': 'Las horas estimadas deben ser un número entero.'
                }
            },
            'evento': {
                'read_only': True
            },
        }

    def validate_horas_estimadas(self, value):
        if value < HORAS_MINIMAS or value > HORAS_MAXIMAS:
            raise serializers.ValidationError(
                f'Las horas estimadas deben ser un número entero entre {HORAS_MINIMAS} y {HORAS_MAXIMAS}.'
            )
        return value

    def validate_plazo(self, value):
        if value.year > ANIO_MAXIMO:
            raise serializers.ValidationError(
                f'El año del plazo no puede ser mayor a {ANIO_MAXIMO}.'
            )
        # Solo exigimos fecha futura al crear o al mover el plazo (reprogramar);
        # así no bloqueamos ediciones de nombre/horas de gestiones ya vencidas.
        plazo_cambia = self.instance is None or 'plazo' in self.initial_data
        if plazo_cambia and value < timezone.now().date():
            raise serializers.ValidationError(
                'El plazo de la gestión no puede ser una fecha pasada.'
            )
        evento = self.context.get('evento')
        if evento and evento.fecha_hora and value > evento.fecha_hora.date():
            raise serializers.ValidationError(
                'El plazo de la gestión no puede ser posterior a la fecha del evento.'
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

    def validate_fecha_hora(self, value):
        if value.year > ANIO_MAXIMO:
            raise serializers.ValidationError(
                f'El año del evento no puede ser mayor a {ANIO_MAXIMO}.'
            )
        # Al crear, la fecha/hora debe ser estrictamente futura (no vale la misma
        # hora pasada del día). Al editar se permite cualquier valor para no
        # bloquear correcciones de eventos ya guardados.
        if self.instance is None and value <= timezone.now():
            raise serializers.ValidationError(
                'La fecha y hora del evento deben ser futuras.'
            )
        return value

    def validate_plazo_limite(self, value):
        if value.year > ANIO_MAXIMO:
            raise serializers.ValidationError(
                f'El año del plazo límite no puede ser mayor a {ANIO_MAXIMO}.'
            )
        if self.instance is None and value < timezone.now().date():
            raise serializers.ValidationError(
                'El plazo límite no puede ser una fecha pasada.'
            )
        return value

    def validate(self, attrs):
        fecha = attrs.get('fecha_hora', getattr(self.instance, 'fecha_hora', None))
        plazo = attrs.get('plazo_limite', getattr(self.instance, 'plazo_limite', None))
        if fecha and plazo and plazo > fecha.date():
            raise serializers.ValidationError({
                'plazo_limite': 'El plazo límite no puede ser posterior a la fecha del evento.'
            })
        return attrs


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
    horas_estimadas = serializers.IntegerField()
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
    gestiones = GestionHoySerializer(
        many=True,
        help_text='Lista plana de gestiones activas, ya ordenada por fecha y menor esfuerzo. Es la que consume el frontend.'
    )
    vencidas = GestionHoySerializer(many=True)
    para_hoy = GestionHoySerializer(many=True)
    proximas = GestionHoySerializer(many=True)

class ConfiguracionLimiteHorasSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerfilOrganizador
        fields = ['limite_horas_diarias']

    def validate_limite_horas_diarias(self, value):
        if value < 1 or value > 16:
            raise serializers.ValidationError(
                'El límite diario debe estar entre 1 y 16 horas.'
            )
        return value