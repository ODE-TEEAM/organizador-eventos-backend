from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework.authtoken.models import Token
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import Evento, Subtarea
from .serializers import (
    EventoSerializer,
    SubtareaSerializer,
    HoyQuerySerializer,
    HoyResponseSerializer,
    RegistroSerializer,
)

ESTADO_COMPLETADA = 'completada'
# Ventana (en días) para clasificar una gestión próxima como de prioridad "media".
VENTANA_MEDIA_DIAS = 3


@extend_schema(
    summary='Health check público',
    responses={200: dict},
)
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(request):
    return Response({
        "status": "ok",
        "message": "API del Organizador de Eventos funcionando correctamente"
    })


@extend_schema(
    summary='Iniciar sesión (devuelve token + datos del usuario)',
    description=(
        'Recibe `email` y `password`. Si las credenciales son correctas devuelve el '
        'token (en `token`, `access` y `access_token`) y los datos del usuario. '
        'Si son incorrectas responde `401`.'
    ),
    request=dict,
    examples=[
        OpenApiExample(
            'Request',
            value={'email': 'ana@hestia.com', 'password': 'clave123'},
            request_only=True,
        ),
        OpenApiExample(
            'Respuesta exitosa',
            value={
                'token': '9f1c...', 'access': '9f1c...', 'access_token': '9f1c...',
                'email': 'ana@hestia.com', 'nombre': 'Ana Pérez',
                'user': {'id': 1, 'email': 'ana@hestia.com', 'nombre': 'Ana Pérez'},
            },
            response_only=True,
        ),
        OpenApiExample(
            'Credenciales incorrectas',
            value={'detail': 'Credenciales incorrectas.'},
            response_only=True,
            status_codes=['401'],
        ),
    ],
    responses={200: dict, 401: dict},
)
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def login(request):
    email = (request.data.get('email') or '').strip()
    password = request.data.get('password') or ''

    if not email or not password:
        return Response(
            {'detail': 'Email y password son obligatorios.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = User.objects.filter(email__iexact=email).first()

    if user is None or not user.is_active or not user.check_password(password):
        return Response(
            {'detail': 'Credenciales incorrectas.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    token, _ = Token.objects.get_or_create(user=user)
    nombre = user.get_full_name() or user.username

    return Response({
        'token': token.key,
        'access': token.key,
        'access_token': token.key,
        'email': user.email,
        'nombre': nombre,
        'user': {
            'id': user.id,
            'email': user.email,
            'nombre': nombre,
        },
    })


@extend_schema(
    summary='Crear cuenta de organizador (registro)',
    description=(
        'Recibe `nombre`, `email` y `password` (mínimo 6 caracteres) y crea la cuenta '
        'del organizador. El `nombre` se guarda como nombre visible (saludo y header). '
        'Devuelve `201` con los datos del usuario y su token. Si el correo ya existe o '
        'los datos son inválidos, responde `400` con los errores por campo '
        '(ej. `{"email": ["..."]}`).'
    ),
    request=RegistroSerializer,
    examples=[
        OpenApiExample(
            'Request',
            value={'nombre': 'Mauricio', 'email': 'nuevo@hestia.com', 'password': 'clave123'},
            request_only=True,
        ),
        OpenApiExample(
            'Cuenta creada',
            value={
                'id': 3, 'email': 'nuevo@hestia.com', 'nombre': 'Mauricio',
                'token': '7c2a...',
            },
            response_only=True,
            status_codes=['201'],
        ),
        OpenApiExample(
            'Correo duplicado',
            value={'email': ['Ese correo ya tiene una cuenta. Prueba iniciando sesión o usa otro correo.']},
            response_only=True,
            status_codes=['400'],
        ),
    ],
    responses={201: dict, 400: dict},
)
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def register(request):
    serializer = RegistroSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    token, _ = Token.objects.get_or_create(user=user)

    return Response(
        {
            'id': user.id,
            'email': user.email,
            'nombre': user.get_full_name() or user.username,
            'token': token.key,
        },
        status=status.HTTP_201_CREATED
    )


@extend_schema(
    summary='Leer o actualizar el perfil del organizador autenticado',
    description=(
        'GET devuelve `id`, `email` y `nombre` del usuario autenticado. '
        'PATCH acepta `nombre` (mínimo 3 caracteres) y/o `password_actual` + '
        '`password_nueva` (mínimo 6 caracteres) para cambiar la contraseña. '
        'El token de sesión sigue siendo válido después del cambio.'
    ),
    request=dict,
    responses={200: dict, 400: dict},
)
@api_view(['GET', 'PATCH'])
def perfil(request):
    user = request.user

    if request.method == 'GET':
        return Response({
            'id': user.id,
            'email': user.email,
            'nombre': user.get_full_name() or user.username,
        })

    data = request.data

    if 'nombre' in data:
        nombre = (data.get('nombre') or '').strip()
        if len(nombre) < 3:
            return Response(
                {'nombre': ['El nombre debe tener al menos 3 caracteres.']},
                status=status.HTTP_400_BAD_REQUEST
            )
        user.first_name = nombre[:150]
        user.save(update_fields=['first_name'])

    if 'password_actual' in data or 'password_nueva' in data:
        password_actual = data.get('password_actual') or ''
        password_nueva = data.get('password_nueva') or ''

        if not user.check_password(password_actual):
            return Response(
                {'password_actual': ['La contraseña actual no es correcta.']},
                status=status.HTTP_400_BAD_REQUEST
            )
        if len(password_nueva) < 6:
            return Response(
                {'password_nueva': ['La nueva contraseña debe tener al menos 6 caracteres.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(password_nueva)
        user.save(update_fields=['password'])

    return Response({
        'id': user.id,
        'email': user.email,
        'nombre': user.get_full_name() or user.username,
    })


@api_view(['GET', 'POST'])
def eventos(request):
    if request.method == 'GET':
        eventos = Evento.objects.filter(organizador=request.user)
        serializer = EventoSerializer(eventos, many=True)
        return Response(serializer.data)

    if request.method == 'POST':
        serializer = EventoSerializer(data=request.data)

        if serializer.is_valid():
            evento = serializer.save(organizador=request.user)

            Subtarea.objects.create(
                evento=evento,
                nombre='Reservar salón',
                plazo=evento.plazo_limite,
                horas_estimadas=2
            )

            Subtarea.objects.create(
                evento=evento,
                nombre='Enviar invitaciones',
                plazo=evento.plazo_limite,
                horas_estimadas=2
            )

            Subtarea.objects.create(
                evento=evento,
                nombre='Confirmar catering',
                plazo=evento.plazo_limite,
                horas_estimadas=2
            )

            return Response(
                EventoSerializer(evento).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET', 'PUT', 'PATCH'])
def obtener_evento(request, evento_id):
    try:
        evento = Evento.objects.get(id=evento_id, organizador=request.user)
    except Evento.DoesNotExist:
        return Response(
            {"error": "El evento no existe"},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == 'GET':
        serializer = EventoSerializer(evento)
        return Response(serializer.data)

    # PUT/PATCH: edición del evento. `partial=True` permite enviar solo los
    # campos que cambiaron; el serializer valida y devuelve errores por campo.
    serializer = EventoSerializer(evento, data=request.data, partial=True)

    if serializer.is_valid():
        serializer.save()
        return Response(EventoSerializer(evento).data)

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


@api_view(['POST'])
def crear_subtarea(request, evento_id):
    try:
        evento = Evento.objects.get(id=evento_id, organizador=request.user)
    except Evento.DoesNotExist:
        return Response(
            {"error": "El evento no existe"},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = SubtareaSerializer(data=request.data)

    if serializer.is_valid():
        subtarea = serializer.save(evento=evento)
        return Response(
            SubtareaSerializer(subtarea).data,
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


@extend_schema(
    summary='Reprogramar o editar una gestión (subtarea)',
    description=(
        'Permite actualizar campos de una gestión del organizador autenticado. '
        'Para el C1 del Sprint 3 el campo principal es `plazo` (reprogramar fecha). '
        'También acepta `nombre`, `horas_estimadas` y `estado` de forma parcial.\n\n'
        'Solo se puede editar una subtarea de un evento propio. '
        'Tras cambiar el plazo, `GET /api/hoy/` refleja el nuevo grupo '
        '(vencidas / para_hoy / proximas).'
    ),
    request=SubtareaSerializer,
    examples=[
        OpenApiExample(
            'Reprogramar plazo',
            value={'plazo': '2026-10-12'},
            request_only=True,
        ),
        OpenApiExample(
            'Respuesta',
            value={
                'id': 15,
                'nombre': 'Confirmar catering',
                'plazo': '2026-10-12',
                'horas_estimadas': '2.00',
                'estado': 'pendiente',
            },
            response_only=True,
        ),
    ],
    responses={200: SubtareaSerializer, 400: dict, 404: dict},
)
@api_view(['GET', 'PUT', 'PATCH'])
def actualizar_subtarea(request, subtarea_id):
    try:
        subtarea = Subtarea.objects.select_related('evento').get(
            id=subtarea_id,
            evento__organizador=request.user,
        )
    except Subtarea.DoesNotExist:
        return Response(
            {'error': 'La gestión no existe o no te pertenece.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == 'GET':
        return Response(SubtareaSerializer(subtarea).data)

    serializer = SubtareaSerializer(
        subtarea,
        data=request.data,
        partial=True,
    )

    if serializer.is_valid():
        serializer.save()
        return Response(SubtareaSerializer(subtarea).data)

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST,
    )

def _grupo_por_plazo(plazo, hoy):
    """Clasifica una gestión en vencidas / para_hoy / proximas según su plazo."""
    if plazo < hoy:
        return 'vencidas'
    if plazo == hoy:
        return 'para_hoy'
    return 'proximas'


def _prioridad_por_plazo(plazo, hoy):
    """Regla de priorización: vence hoy o antes -> alta; próximos 3 días -> media; resto -> baja."""
    if plazo <= hoy:
        return 'alta'
    if plazo <= hoy + timedelta(days=VENTANA_MEDIA_DIAS):
        return 'media'
    return 'baja'


@extend_schema(
    summary='Gestiones urgentes agrupadas para la vista /hoy',
    description=(
        'Devuelve las gestiones (subtareas) del organizador agrupadas por urgencia en '
        '`vencidas`, `para_hoy` y `proximas`, junto con un `resumen` de conteos.\n\n'
        '**Regla de orden:** cada grupo se ordena por `fecha` (plazo) ascendente y, '
        'ante empate, por menor esfuerzo estimado (`horas_estimadas`).\n\n'
        '**Regla de prioridad:** `alta` si vence hoy o antes, `media` si vence dentro '
        'de los próximos 3 días, `baja` en el resto.\n\n'
        '**Filtros (query params):** `?evento=<id>` limita a un evento y '
        '`?estado=<pendiente|en_progreso|completada>` limita a un estado. Sin filtro de '
        'estado solo se listan gestiones activas (se excluyen las completadas).'
    ),
    parameters=[
        OpenApiParameter(
            'evento', int, required=False,
            description='Filtra por el id del evento (ej. ?evento=3).'
        ),
        OpenApiParameter(
            'estado', str, required=False,
            description='Filtra por estado: pendiente, en_progreso o completada.'
        ),
    ],
    responses=HoyResponseSerializer,
    examples=[
        OpenApiExample(
            'Respuesta agrupada',
            value={
                'fecha_referencia': '2026-09-16',
                'resumen': {
                    'total': 4, 'vencidas': 1, 'para_hoy': 2,
                    'proximas': 1, 'completadas': 1
                },
                'vencidas': [
                    {
                        'id': 1, 'titulo': 'Confirmar menú con catering',
                        'evento': 'Boda de Laura & Carlos', 'evento_id': 3,
                        'estado': 'pendiente', 'prioridad': 'alta',
                        'fecha': '2026-09-14', 'horas_estimadas': '2.00',
                        'grupo': 'vencidas'
                    }
                ],
                'para_hoy': [
                    {
                        'id': 4, 'titulo': 'Solicitar cotización de sonido',
                        'evento': 'Boda de Laura & Carlos', 'evento_id': 3,
                        'estado': 'pendiente', 'prioridad': 'alta',
                        'fecha': '2026-09-16', 'horas_estimadas': '3.00',
                        'grupo': 'para_hoy'
                    }
                ],
                'proximas': [
                    {
                        'id': 6, 'titulo': 'Diseñar programa del evento',
                        'evento': 'Evento Corporativo Nexo', 'evento_id': 5,
                        'estado': 'pendiente', 'prioridad': 'media',
                        'fecha': '2026-09-18', 'horas_estimadas': '4.00',
                        'grupo': 'proximas'
                    }
                ],
            },
            response_only=True,
        ),
    ],
)
@api_view(['GET'])
def hoy(request):
    hoy_fecha = timezone.localdate()

    queryset = Subtarea.objects.select_related('evento').filter(
        evento__organizador=request.user
    )

    evento_param = request.query_params.get('evento')
    if evento_param:
        try:
            evento_id = int(evento_param)
        except (TypeError, ValueError):
            return Response(
                {'error': "El parámetro 'evento' debe ser un número entero."},
                status=status.HTTP_400_BAD_REQUEST
            )
        queryset = queryset.filter(evento_id=evento_id)

    estado_param = request.query_params.get('estado')

    # Conteo de completadas dentro del alcance del filtro de evento.
    completadas = queryset.filter(estado=ESTADO_COMPLETADA).count()

    if estado_param:
        queryset = queryset.filter(estado=estado_param)
    else:
        queryset = queryset.exclude(estado=ESTADO_COMPLETADA)

    # Orden cronológico con desempate por menor esfuerzo estimado.
    queryset = queryset.order_by('plazo', 'horas_estimadas', 'id')

    vencidas, para_hoy, proximas = [], [], []
    grupos = {'vencidas': vencidas, 'para_hoy': para_hoy, 'proximas': proximas}
    # Lista plana (ya ordenada) que consume el frontend en /hoy.
    gestiones = []

    for subtarea in queryset:
        grupo = _grupo_por_plazo(subtarea.plazo, hoy_fecha)
        item = {
            'id': subtarea.id,
            'titulo': subtarea.nombre,
            'evento': subtarea.evento.nombre,
            'evento_id': subtarea.evento_id,
            'estado': subtarea.estado,
            'prioridad': _prioridad_por_plazo(subtarea.plazo, hoy_fecha),
            'fecha': subtarea.plazo,
            'horas_estimadas': subtarea.horas_estimadas,
            'grupo': grupo,
        }
        grupos[grupo].append(item)
        gestiones.append(item)

    return Response({
        'fecha_referencia': hoy_fecha,
        'resumen': {
            'total': len(vencidas) + len(para_hoy) + len(proximas),
            'vencidas': len(vencidas),
            'para_hoy': len(para_hoy),
            'proximas': len(proximas),
            'completadas': completadas,
        },
        'gestiones': gestiones,
        'vencidas': vencidas,
        'para_hoy': para_hoy,
        'proximas': proximas,
    })