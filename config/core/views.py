from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models, transaction
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

from .models import Evento, Subtarea, PerfilOrganizador
from .serializers import (
    EventoSerializer,
    SubtareaSerializer,
    HoyQuerySerializer,
    HoyResponseSerializer,
    RegistroSerializer,
    ConfiguracionLimiteHorasSerializer,
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
def _obtener_o_crear_perfil(user):
    """Devuelve el perfil del organizador; si no existe, lo crea con límite 6h."""
    perfil, _ = PerfilOrganizador.objects.get_or_create(
        user=user,
        defaults={'limite_horas_diarias': 6},
    )
    return perfil

def _horas_asignadas_en_fecha(usuario, fecha, excluir_id=None):
    gestiones = Subtarea.objects.filter(
        evento__organizador=usuario,
        plazo=fecha,
    )

    if excluir_id is not None:
        gestiones = gestiones.exclude(id=excluir_id)

    return (
        gestiones.aggregate(total=models.Sum('horas_estimadas'))['total']
        or 0
    )

def _buscar_dia_que_supera_limite(usuario, limite):
    hoy = timezone.localdate()

    total_hoy = _horas_asignadas_en_fecha(usuario, hoy)

    if total_hoy > limite:
        return {
            'plazo': hoy,
            'total': total_hoy,
        }

    return None

@extend_schema(
    summary='Leer o actualizar el perfil del organizador autenticado',
    description=(
        'GET devuelve `id`, `email`, `nombre` y `limite_horas_diarias` (default 6). '
        'PATCH acepta `nombre`, `limite_horas_diarias` (1–16) y/o cambio de contraseña '
        '(`password_actual` + `password_nueva`).'
    ),
    request=dict,
    responses={200: dict, 400: dict},
)
@api_view(['GET', 'PATCH'])
def perfil(request):
    user = request.user
    perfil_org = _obtener_o_crear_perfil(user)

    if request.method == 'GET':
        return Response({
            'id': user.id,
            'email': user.email,
            'nombre': user.get_full_name() or user.username,
            'limite_horas_diarias': perfil_org.limite_horas_diarias,
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

    if 'limite_horas_diarias' in data:
        try:
            limite = int(data.get('limite_horas_diarias'))
        except (TypeError, ValueError):
            return Response(
                {'limite_horas_diarias': ['Debe ser un número entero entre 1 y 16.']},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if limite < 1 or limite > 16:
            return Response(
                {'limite_horas_diarias': ['El límite diario debe estar entre 1 y 16 horas.']},
                status=status.HTTP_400_BAD_REQUEST
            )



        dia_conflictivo = _buscar_dia_que_supera_limite(
            request.user,
            limite,
        )

        if dia_conflictivo:
            return Response(
                {
                    'limite_horas_diarias': [
                        (
                            f'No puedes establecer un límite de {limite} horas: '
                            f'hoy ya tienes {dia_conflictivo["total"]} '
                            f'horas asignadas.'
                        )
                    ],
                    'fecha_conflicto': dia_conflictivo['plazo'],
                    'horas_asignadas': dia_conflictivo['total'],
                    'limite_solicitado': limite,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        perfil_org.limite_horas_diarias = limite
        perfil_org.save(update_fields=['limite_horas_diarias'])

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

        perfil_org.refresh_from_db()

        return Response({
            'id': user.id,
            'email': user.email,
            'nombre': user.get_full_name() or user.username,
            'limite_horas_diarias': perfil_org.limite_horas_diarias,
        })

@api_view(['GET', 'POST'])
def eventos(request):
    if request.method == 'GET':
        eventos = Evento.objects.filter(organizador=request.user)
        serializer = EventoSerializer(eventos, many=True)
        return Response(serializer.data)

    
    if request.method == 'POST':
        serializer = EventoSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        fecha_gestiones = serializer.validated_data['plazo_limite']
        horas_predeterminadas = 6

        configuracion = _obtener_o_crear_perfil(request.user)

        horas_existentes = _horas_asignadas_en_fecha(
            request.user,
            fecha_gestiones,
        )

        horas_totales = horas_existentes + horas_predeterminadas
        fecha_formateada = fecha_gestiones.strftime('%d-%m-%Y')
        if horas_totales > configuracion.limite_horas_diarias:
            return Response(
                {
                    'conflicto': True,
                    'mensaje': (
                        f'No se puede crear el evento: sus tres gestiones '
                        f'iniciales requieren {horas_predeterminadas} horas '
                        f'el: {fecha_formateada}. Ya hay {horas_existentes} '
                        f'horas asignadas y el límite diario es de '
                        f'{configuracion.limite_horas_diarias} horas.'
                    ),
                    'fecha': fecha_gestiones,
                    'horas_existentes': horas_existentes,
                    'horas_nuevas': horas_predeterminadas,
                    'horas_totales': horas_totales,
                    'limite_horas': configuracion.limite_horas_diarias,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            evento = serializer.save(organizador=request.user)

            Subtarea.objects.create(
                evento=evento,
                nombre='Reservar salón',
                plazo=evento.plazo_limite,
                horas_estimadas=2,
            )

            Subtarea.objects.create(
                evento=evento,
                nombre='Enviar invitaciones',
                plazo=evento.plazo_limite,
                horas_estimadas=2,
            )

            Subtarea.objects.create(
                evento=evento,
                nombre='Confirmar catering',
                plazo=evento.plazo_limite,
                horas_estimadas=2,
            )

        return Response(
            EventoSerializer(evento).data,
            status=status.HTTP_201_CREATED,
        )



@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
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

    if request.method == 'DELETE':
        evento.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

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

    serializer = SubtareaSerializer(
        data=request.data,
        context={'evento': evento},
    )

    
    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    fecha = serializer.validated_data['plazo']
    horas_nuevas = serializer.validated_data['horas_estimadas']

    configuracion = _obtener_o_crear_perfil(request.user)

    horas_existentes = _horas_asignadas_en_fecha(
        request.user,
        fecha,
    )

    horas_totales = horas_existentes + horas_nuevas

    if horas_totales > configuracion.limite_horas_diarias:
        return Response(
            {
                'conflicto': True,
                'mensaje': (
                    f'La gestión supera el límite diario. '
                    f'Quedarías con {horas_totales} horas asignadas '
                    f'el {fecha}, pero tu límite es de '
                    f'{configuracion.limite_horas_diarias} horas.'
                ),
                'fecha': fecha,
                'horas_existentes': horas_existentes,
                'horas_nuevas': horas_nuevas,
                'horas_totales': horas_totales,
                'limite_horas': configuracion.limite_horas_diarias,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    subtarea = serializer.save(evento=evento)

    return Response(
        SubtareaSerializer(
            subtarea,
            context={'evento': evento},
        ).data,
        status=status.HTTP_201_CREATED,
    )



@extend_schema(
    summary='Reprogramar o editar una gestión (subtarea)',
    description=(
        'Permite actualizar campos de una gestión del organizador autenticado. '
        'Para el C1 del Sprint 3 el campo principal es `plazo` (reprogramar fecha). '
        'También acepta `nombre`, `horas_estimadas` y `estado` de forma parcial.\n\n'
        'Al reprogramar una gestión, se verifica el límite diario de horas del '
        'organizador. Si la nueva fecha supera el límite configurado, se devuelve '
        'un conflicto con las horas planificadas y el límite, sin guardar el cambio.'
    ),
    request=SubtareaSerializer,
    examples=[
        OpenApiExample(
            'Reprogramar plazo',
            value={'plazo': '2026-10-31'},
            request_only=True,
        ),
        OpenApiExample(
            'Respuesta',
            value={
                'id': 15,
                'nombre': 'Confirmar catering',
                'plazo': '2026-10-31',
                'horas_estimadas': 2,
                'estado': 'pendiente',
            },
            response_only=True,
        ),
        OpenApiExample(
            'Conflicto por límite diario',
            value={
                'conflicto': True,
                'mensaje': 'Quedarías con 12 horas planificadas (límite 10 horas).',
                'horas_planificadas': 12,
                'limite_horas': 10,
                'fecha': '2026-10-31',
            },
            response_only=True,
            status_codes=['409'],
        ),
    ],
    responses={
        200: SubtareaSerializer,
        400: dict,
        404: dict,
        409: dict,
    },
)
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
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

    
    if request.method == 'DELETE':
        print(f"DELETE recibido para subtarea {subtarea.id}")
        subtarea.delete()

        existe = Subtarea.objects.filter(id=subtarea_id).exists()
        print(f"¿Sigue existiendo la subtarea {subtarea_id}? {existe}")

        return Response(
            {
                'mensaje': 'Gestión eliminada correctamente.',
                'id_eliminado': subtarea_id,
                'sigue_existiendo': existe,
            },
            status=status.HTTP_200_OK,
        )

    serializer = SubtareaSerializer(
        subtarea,
        data=request.data,
        partial=True,
        context={'evento': subtarea.evento},
    )


    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    # C3: comprobar el límite únicamente si cambian la fecha o las horas.
    fecha_nueva = serializer.validated_data.get('plazo', subtarea.plazo)
    horas_nuevas = serializer.validated_data.get(
        'horas_estimadas',
        subtarea.horas_estimadas,
    )

    cambia_planificacion = (
        'plazo' in serializer.validated_data
        or 'horas_estimadas' in serializer.validated_data
    )

    if cambia_planificacion:
        configuracion = _obtener_o_crear_perfil(request.user)

        horas_existentes = _horas_asignadas_en_fecha(
            request.user,
            fecha_nueva,
            excluir_id=subtarea.id,
        )

        horas_totales = horas_existentes + horas_nuevas
        limite_horas = configuracion.limite_horas_diarias

        if horas_totales > limite_horas:
            fecha_tope = subtarea.evento.fecha_hora.date()
            fecha_sugerida = fecha_nueva + timedelta(days=1)

            for _ in range(30):
                if fecha_sugerida > fecha_tope:
                    fecha_sugerida = None
                    break

                horas_fecha_sugerida = _horas_asignadas_en_fecha(
                    request.user,
                    fecha_sugerida,
                    excluir_id=subtarea.id,
                )

                if horas_fecha_sugerida + horas_nuevas <= limite_horas:
                    break

                fecha_sugerida += timedelta(days=1)

            return Response(
                {
                    'conflicto': True,
                    'mensaje': (
                        f'Quedarías con {horas_totales} horas planificadas '
                        f'el {fecha_nueva}, pero tu límite es de '
                        f'{limite_horas} horas.'
                    ),
                    'horas_planificadas': horas_totales,
                    'limite_horas': limite_horas,
                    'fecha': fecha_nueva,
                    'fecha_sugerida': fecha_sugerida,
                },
                status=status.HTTP_409_CONFLICT,
            )

    serializer.save()
    return Response(SubtareaSerializer(subtarea).data)


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
        queryset = queryset.exclude(
            estado__in=['completada', 'pospuesta']
        )

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

@extend_schema(
    summary='Consultar y actualizar límite diario de horas',
    description=(
        'Devuelve o actualiza el límite diario de horas de gestión del '
        'organizador autenticado. Si aún no tiene configuración, se crea '
        'automáticamente con un límite predeterminado de 6 horas.'
    ),
    request=ConfiguracionLimiteHorasSerializer,
    responses={
        200: ConfiguracionLimiteHorasSerializer,
        400: dict,
    },
)

@api_view(['GET', 'PUT'])
def configuracion_limite_horas(request):
    configuracion, _ = PerfilOrganizador.objects.get_or_create(
        user=request.user,
        defaults={'limite_horas_diarias': 6},
    )

    if request.method == 'GET':
        return Response(
            ConfiguracionLimiteHorasSerializer(configuracion).data
        )

    serializer = ConfiguracionLimiteHorasSerializer(
        configuracion,
        data=request.data,
    )

    if serializer.is_valid():
        limite = serializer.validated_data['limite_horas_diarias']

        dia_conflictivo = _buscar_dia_que_supera_limite(
            request.user,
            limite,
        )

        if dia_conflictivo:
            return Response(
                {
                    'limite_horas_diarias': [
                        (
                            f'No puedes establecer un límite de {limite} horas: '
                            f'hoy ya tienes {dia_conflictivo["total"]} '
                            f'horas asignadas.'
                        )
                    ],
                    'fecha_conflicto': dia_conflictivo['plazo'],
                    'horas_asignadas': dia_conflictivo['total'],
                    'limite_solicitado': limite,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()
        return Response(
            ConfiguracionLimiteHorasSerializer(configuracion).data
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST,
    )
    
