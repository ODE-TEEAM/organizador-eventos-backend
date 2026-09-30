from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Evento, Subtarea


class HoyEndpointTests(APITestCase):
    def setUp(self):
        hoy = timezone.localdate()
        self.evento = Evento.objects.create(
            nombre='Boda de Laura & Carlos',
            tipo='boda',
            cliente='Laura',
            fecha_hora=timezone.now(),
            lugar='Salón',
            plazo_limite=hoy,
        )
        otro = Evento.objects.create(
            nombre='Evento Corporativo Nexo',
            tipo='corporativo',
            cliente='Nexo',
            fecha_hora=timezone.now(),
            lugar='Hotel',
            plazo_limite=hoy,
        )
        # vencida (plazo ayer), alta
        Subtarea.objects.create(evento=self.evento, nombre='Vencida', plazo=hoy - timedelta(days=2), horas_estimadas=2, estado='pendiente')
        # para hoy, dos con mismo plazo -> desempate por horas (1 antes que 3)
        Subtarea.objects.create(evento=self.evento, nombre='Hoy pesada', plazo=hoy, horas_estimadas=3, estado='pendiente')
        Subtarea.objects.create(evento=self.evento, nombre='Hoy liviana', plazo=hoy, horas_estimadas=1, estado='en_progreso')
        # proxima dentro de 2 dias -> media
        Subtarea.objects.create(evento=otro, nombre='Proxima media', plazo=hoy + timedelta(days=2), horas_estimadas=4, estado='pendiente')
        # proxima lejana -> baja
        Subtarea.objects.create(evento=otro, nombre='Proxima baja', plazo=hoy + timedelta(days=10), horas_estimadas=4, estado='pendiente')
        # completada -> excluida por defecto, cuenta en resumen
        Subtarea.objects.create(evento=self.evento, nombre='Completada', plazo=hoy, horas_estimadas=1, estado='completada')
        self.otro_id = otro.id

    def test_agrupacion_orden_y_resumen(self):
        r = self.client.get('/api/hoy/')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual([g['titulo'] for g in d['vencidas']], ['Vencida'])
        # desempate por menor esfuerzo: liviana(1) antes que pesada(3)
        self.assertEqual([g['titulo'] for g in d['para_hoy']], ['Hoy liviana', 'Hoy pesada'])
        self.assertEqual([g['titulo'] for g in d['proximas']], ['Proxima media', 'Proxima baja'])
        self.assertEqual(d['resumen'], {'total': 5, 'vencidas': 1, 'para_hoy': 2, 'proximas': 2, 'completadas': 1})
        # prioridades
        self.assertEqual(d['vencidas'][0]['prioridad'], 'alta')
        self.assertEqual(d['proximas'][0]['prioridad'], 'media')
        self.assertEqual(d['proximas'][1]['prioridad'], 'baja')

    def test_filtro_por_evento(self):
        r = self.client.get(f'/api/hoy/?evento={self.otro_id}')
        d = r.json()
        self.assertEqual(d['resumen']['vencidas'], 0)
        self.assertEqual([g['titulo'] for g in d['proximas']], ['Proxima media', 'Proxima baja'])

    def test_filtro_por_estado_incluye_completadas(self):
        r = self.client.get('/api/hoy/?estado=completada')
        d = r.json()
        self.assertEqual(d['resumen']['total'], 1)
        self.assertEqual([g['titulo'] for g in d['para_hoy']], ['Completada'])

    def test_evento_invalido_400(self):
        r = self.client.get('/api/hoy/?evento=abc')
        self.assertEqual(r.status_code, 400)