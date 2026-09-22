from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Evento, Subtarea
from .serializers import EventoSerializer, SubtareaSerializer


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