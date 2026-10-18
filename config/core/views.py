from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
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
    HoyResponseSerializer,
    RegistroSerializer,
    ConfiguracionLimiteHorasSerializer,
)

ESTADO_COMPLETADA = 'completada'
# Ventana (en días) para clasificar una gestión próxima como de prioridad "media".
VENTANA_MEDIA_DIAS = 3


def _obtener_o_crear_perfil(user):
    """Devuelve el perfil del organizador; si no existe, lo crea con límite 6h."""
    perfil, _ = PerfilOrganizador.objects.get_or_create(
        user=user,
        defaults={'limite_horas_diarias': 6},
    )
    return perfil


def _horas_asignadas_en_fecha(usuario, fecha, excluir_id=None):
    """
    Suma horas de gestiones ACTIVAS en una fecha.
    No cuentan completadas ni pospuestas (mismo criterio que /hoy).
    """
    gestiones = Subtarea.objects.filter(
        evento__organizador=usuario,
        plazo=fecha,
    ).exclude(
        estado__in=['completada', 'pospuesta']
    )

    if excluir_id is not None:
        gestiones = gestiones.exclude(id=excluir_id)

    return (
        gestiones.aggregate(total=models.Sum('horas_estimadas'))['total']
        or 0
    )


def _buscar_dia_que_supera_limite(usuario, limite):
    """
    Busca el día (hoy o futuro) con más horas activas que el límite propuesto.
    Si hay varios, devuelve el de mayor carga (y si empatan, el más cercano).
    """
    hoy = timezone.localdate()

    filas = (
        Subtarea.objects.filter(
            evento__organizador=usuario,
            plazo__gte=hoy,
        )
        .exclude(estado__in=['completada', 'pospuesta'])
        .values('plazo')
        .annotate(total=models.Sum('horas_estimadas'))
        .filter(total__gt=limite)
        .order_by('-total', 'plazo')
    )

    fila = filas.first()
    if not fila:
        return None

    return {
        'plazo': fila['plazo'],
        'total': fila['total'],
    }


def _grupo_por_plazo(plazo, hoy):
    """Clasifica una gestión en vencidas / para_hoy / proximas según su plazo."""
    if plazo < hoy:
        return 'vencidas'
    if plazo == hoy:
        return 'para_hoy'
    return 'proximas'


def _buscar_fechas_disponibles(usuario, subtarea, cantidad=3):
    hoy = timezone.localdate()
    configuracion = _obtener_o_crear_perfil(usuario)

    horas_necesarias = subtarea.horas_estimadas
    fechas_disponibles = []

    for dias in range(1, 31):
        fecha = hoy + timedelta(days=dias)

        if fecha > subtarea.evento.plazo_limite:
            break

        horas_ocupadas = _horas_asignadas_en_fecha(usuario, fecha)

        if (
            horas_ocupadas + horas_necesarias
            <= configuracion.limite_horas_diarias
        ):
            fechas_disponibles.append({
                'fecha': fecha.isoformat(),
                'horas_disponibles': (
                    configuracion.limite_horas_diarias - horas_ocupadas
                ),
            })

        if len(fechas_disponibles) >= cantidad:
            break

    return fechas_disponibles


def _prioridad_por_plazo(plazo, hoy):
    """Regla de priorización: vence hoy o antes -> alta; próximos 3 días -> media; resto -> baja."""
    if plazo <= hoy:
        return 'alta'
    if plazo <= hoy + timedelta(days=VENTANA_MEDIA_DIAS):
        return 'media'
    return 'baja'


@extend_schema(
    summary='Health check público',
    responses={200: dict},
)
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(request):
    return Response({
        'status': 'ok',
        'message': 'API del Organizador de Eventos funcionando correctamente',
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
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.filter(email__iexact=email).first()

    if user is None or not user.is_active or not user.check_password(password):
        return Response(
            {'detail': 'Credenciales incorrectas.'},
            status=status.HTTP_401_UNAUTHORIZED,
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
        'los datos son inválidos, responde `400` con los errores por campo.'
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
        status=status.HTTP_201_CREATED,
    )


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
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.first_name = nombre[:150]
        user.save(update_fields=['first_name'])

    if 'limite_horas_diarias' in data:
        try:
            limite = int(data.get('limite_horas_diarias'))
        except (TypeError, ValueError):
            return Response(
                {'limite_horas_diarias': ['Debe ser un número entero entre 1 y 16.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if limite < 1 or limite > 16:
            return Response(
                {'limite_horas_diarias': ['El límite diario debe estar entre 1 y 16 horas.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dia_conflictivo = _buscar_dia_que_supera_limite(request.user, limite)

        if dia_conflictivo:
            fecha = dia_conflictivo['plazo']
            fecha_txt = (
                fecha.strftime('%d/%m/%Y')
                if hasattr(fecha, 'strftime')
                else str(fecha)
            )
            return Response(
                {
                    'limite_horas_diarias': [
                        (
                            f'No puedes establecer un límite de {limite} horas: '
                            f'el {fecha_txt} ya tienes {dia_conflictivo["total"]} '
                            f'horas planificadas.'
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
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(password_nueva) < 6:
            return Response(
                {'password_nueva': ['La nueva contraseña debe tener al menos 6 caracteres.']},
                status=status.HTTP_400_BAD_REQUEST,
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


@extend_schema(
    summary='Listar eventos o crear un evento',
    description=(
        'GET lista los eventos del organizador autenticado. '
        'POST crea solo el evento (sin gestiones automáticas). '
        'Las gestiones logísticas se agregan después con '
        'POST /api/eventos/{id}/subtareas/ o desde el formulario Crear.'
    ),
    request=EventoSerializer,
    responses={
        200: EventoSerializer(many=True),
        201: EventoSerializer,
        400: dict,
    },
)
@api_view(['GET', 'POST'])
def eventos(request):
    if request.method == 'GET':
        eventos_qs = Evento.objects.filter(organizador=request.user)
        serializer = EventoSerializer(eventos_qs, many=True)
        return Response(serializer.data)

    serializer = EventoSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Solo crea el evento. No se insertan gestiones automáticas
    # (Reservar salón, Enviar invitaciones, Confirmar catering).
    # El organizador las agrega cuando quiera desde Crear o el detalle.
    evento = serializer.save(organizador=request.user)

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
            {'error': 'El evento no existe'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == 'GET':
        return Response(EventoSerializer(evento).data)

    if request.method == 'DELETE':
        evento.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = EventoSerializer(evento, data=request.data, partial=True)

    if serializer.is_valid():
        serializer.save()
        return Response(EventoSerializer(evento).data)

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST,
    )


@extend_schema(
    summary='Consultar el progreso de un evento',
    description=(
        'Devuelve el total de gestiones del evento, su distribución por estado '
        'y el porcentaje completado. Solo permite consultar eventos del '
        'organizador autenticado.'
    ),
    responses={200: dict, 404: dict},
    examples=[
        OpenApiExample(
            'Progreso del evento',
            value={
                'evento_id': 50,
                'evento': 'Prueba de reactivación',
                'total_gestiones': 3,
                'completadas': 1,
                'pendientes': 1,
                'pospuestas': 1,
                'porcentaje_progreso': 33.33,
            },
            response_only=True,
            status_codes=['200'],
        ),
    ],
)
@api_view(['GET'])
def progreso_evento(request, evento_id):
    try:
        evento = Evento.objects.get(
            id=evento_id,
            organizador=request.user,
        )
    except Evento.DoesNotExist:
        return Response(
            {'error': 'El evento no existe o no te pertenece.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    subtareas = evento.subtareas.all()
    total = subtareas.count()

    completadas = subtareas.filter(estado='completada').count()
    pendientes = subtareas.filter(estado='pendiente').count()
    pospuestas = subtareas.filter(estado='pospuesta').count()

    porcentaje = round((completadas / total) * 100, 2) if total else 0

    return Response({
        'evento_id': evento.id,
        'evento': evento.nombre,
        'total_gestiones': total,
        'completadas': completadas,
        'pendientes': pendientes,
        'pospuestas': pospuestas,
        'porcentaje_progreso': porcentaje,
    })


@api_view(['POST'])
def crear_subtarea(request, evento_id):
    try:
        evento = Evento.objects.get(id=evento_id, organizador=request.user)
    except Evento.DoesNotExist:
        return Response(
            {'error': 'El evento no existe'},
            status=status.HTTP_404_NOT_FOUND,
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
        'Al reprogramar, se verifica el límite diario de horas. Si se supera, '
        'responde 409 con el conflicto y fechas sugeridas.'
    ),
    request=SubtareaSerializer,
    examples=[
        OpenApiExample(
            'Reprogramar plazo',
            value={'plazo': '2026-10-31'},
            request_only=True,
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
        subtarea.delete()
        return Response(
            {
                'mensaje': 'Gestión eliminada correctamente.',
                'id_eliminado': subtarea_id,
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

    # Reactivación de subtareas pospuestas.
    estado_nuevo = serializer.validated_data.get('estado', subtarea.estado)

    if estado_nuevo == 'pendiente' and subtarea.estado == 'pospuesta':
        fecha_reactivacion = serializer.validated_data.get(
            'plazo',
            subtarea.plazo,
        )

        if fecha_reactivacion < timezone.localdate():
            return Response(
                {'plazo': ['No puedes reactivar una gestión con una fecha pasada.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if fecha_reactivacion > subtarea.evento.plazo_limite:
            return Response(
                {'plazo': ['La fecha no puede superar el plazo límite del evento.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.validated_data['nota'] = ''

    # Comprobar límite solo si cambian fecha u horas.
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
            fechas_sugeridas = _buscar_fechas_disponibles(
                request.user,
                subtarea,
            )

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
                    'fechas_sugeridas': fechas_sugeridas,
                    'fecha_sugerida': (
                        fechas_sugeridas[0]['fecha']
                        if fechas_sugeridas
                        else None
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

    serializer.save()
    return Response(SubtareaSerializer(subtarea).data)


@extend_schema(
    summary='Gestiones urgentes agrupadas para la vista /hoy',
    description=(
        'Devuelve las gestiones del organizador agrupadas por urgencia en '
        '`vencidas`, `para_hoy` y `proximas`, con resumen de conteos y '
        'señales de reorganización si el día actual supera el límite de horas.'
    ),
    parameters=[
        OpenApiParameter(
            'evento', int, required=False,
            description='Filtra por el id del evento (ej. ?evento=3).',
        ),
        OpenApiParameter(
            'estado', str, required=False,
            description='Filtra por estado: pendiente, en_progreso o completada.',
        ),
    ],
    responses=HoyResponseSerializer,
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
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = queryset.filter(evento_id=evento_id)

    estado_param = request.query_params.get('estado')

    completadas = queryset.filter(estado=ESTADO_COMPLETADA).count()

    horas_pendientes_hoy = (
        Subtarea.objects
        .filter(
            evento__organizador=request.user,
            plazo=hoy_fecha,
        )
        .exclude(estado__in=['completada', 'pospuesta'])
        .aggregate(total=models.Sum('horas_estimadas'))['total']
        or 0
    )

    configuracion = _obtener_o_crear_perfil(request.user)
    limite_horas_diarias = configuracion.limite_horas_diarias

    exceso_horas_hoy = max(0, horas_pendientes_hoy - limite_horas_diarias)

    if estado_param:
        queryset = queryset.filter(estado=estado_param)
    else:
        queryset = queryset.exclude(
            estado__in=['completada', 'pospuesta']
        )

    queryset = queryset.order_by('plazo', 'horas_estimadas', 'id')

    vencidas, para_hoy, proximas = [], [], []
    grupos = {'vencidas': vencidas, 'para_hoy': para_hoy, 'proximas': proximas}
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
        'limite_horas_diarias': limite_horas_diarias,
        'requiere_reorganizacion': exceso_horas_hoy > 0,
        'exceso_horas_hoy': exceso_horas_hoy,
        'resumen': {
            'total': len(vencidas) + len(para_hoy) + len(proximas),
            'vencidas': len(vencidas),
            'para_hoy': len(para_hoy),
            'proximas': len(proximas),
            'completadas': completadas,
            'horas_pendientes_hoy': horas_pendientes_hoy,
            'limite_horas_diarias': limite_horas_diarias,
            'exceso_horas_hoy': exceso_horas_hoy,
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
        'automáticamente con un límite predeterminado de 6 horas. '
        'Al actualizar, se valida que ningún día (hoy o futuro) con gestiones '
        'activas supere el nuevo límite.'
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
            fecha = dia_conflictivo['plazo']
            fecha_txt = (
                fecha.strftime('%d/%m/%Y')
                if hasattr(fecha, 'strftime')
                else str(fecha)
            )
            return Response(
                {
                    'limite_horas_diarias': [
                        (
                            f'No puedes establecer un límite de {limite} horas: '
                            f'el {fecha_txt} ya tienes {dia_conflictivo["total"]} '
                            f'horas planificadas.'
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
