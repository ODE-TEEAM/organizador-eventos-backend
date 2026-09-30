from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Evento, Subtarea
from .serializers import (
    EventoSerializer,
    SubtareaSerializer,
    HoyQuerySerializer,
    HoyResponseSerializer,
)

ESTADO_COMPLETADA = 'completada'
# Ventana (en días) para clasificar una gestión próxima como de prioridad "media".
VENTANA_MEDIA_DIAS = 3


@api_view(['GET'])
def health_check(request):
    return Response({
        "status": "ok",
        "message": "API del Organizador de Eventos funcionando correctamente"
    })


@api_view(['GET', 'POST'])
def eventos(request):
    if request.method == 'GET':
        eventos = Evento.objects.all()
        serializer = EventoSerializer(eventos, many=True)
        return Response(serializer.data)

    if request.method == 'POST':
        serializer = EventoSerializer(data=request.data)

        if serializer.is_valid():
            evento = serializer.save()

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


@api_view(['GET'])
def obtener_evento(request, evento_id):
    try:
        evento = Evento.objects.get(id=evento_id)
    except Evento.DoesNotExist:
        return Response(
            {"error": "El evento no existe"},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = EventoSerializer(evento)
    return Response(serializer.data)


@api_view(['POST'])
def crear_subtarea(request, evento_id):
    try:
        evento = Evento.objects.get(id=evento_id)
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

    queryset = Subtarea.objects.select_related('evento').all()

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

    for subtarea in queryset:
        grupo = _grupo_por_plazo(subtarea.plazo, hoy_fecha)
        grupos[grupo].append({
            'id': subtarea.id,
            'titulo': subtarea.nombre,
            'evento': subtarea.evento.nombre,
            'evento_id': subtarea.evento_id,
            'estado': subtarea.estado,
            'prioridad': _prioridad_por_plazo(subtarea.plazo, hoy_fecha),
            'fecha': subtarea.plazo,
            'horas_estimadas': subtarea.horas_estimadas,
            'grupo': grupo,
        })

    return Response({
        'fecha_referencia': hoy_fecha,
        'resumen': {
            'total': len(vencidas) + len(para_hoy) + len(proximas),
            'vencidas': len(vencidas),
            'para_hoy': len(para_hoy),
            'proximas': len(proximas),
            'completadas': completadas,
        },
        'vencidas': vencidas,
        'para_hoy': para_hoy,
        'proximas': proximas,
    })