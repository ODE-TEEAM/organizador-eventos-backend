from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Evento, Subtarea


def _auth(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {'HTTP_AUTHORIZATION': f'Bearer {token.key}'}


class AuthTests(APITestCase):
    def setUp(self):
        self.ana = User.objects.create_user(username='ana', email='ana@hestia.com', password='clave123')
        self.beto = User.objects.create_user(username='beto', email='beto@hestia.com', password='clave456')
        hoy = timezone.localdate()
        self.ev_ana = Evento.objects.create(
            organizador=self.ana, nombre='Boda Ana', tipo='boda', cliente='Ana',
            fecha_hora=timezone.now(), lugar='Salón', plazo_limite=hoy,
        )
        Subtarea.objects.create(evento=self.ev_ana, nombre='Gestión Ana', plazo=hoy, horas_estimadas=2)
        self.ev_beto = Evento.objects.create(
            organizador=self.beto, nombre='Evento Beto', tipo='corp', cliente='Beto',
            fecha_hora=timezone.now(), lugar='Hotel', plazo_limite=hoy + timedelta(days=1),
        )
        Subtarea.objects.create(evento=self.ev_beto, nombre='Gestión Beto', plazo=hoy, horas_estimadas=1)

    # ---- Login ----
    def test_login_ok(self):
        r = self.client.post('/api/login/', {'email': 'ana@hestia.com', 'password': 'clave123'}, format='json')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d.get('token'))
        self.assertEqual(d['token'], d['access'])
        self.assertEqual(d['email'], 'ana@hestia.com')
        self.assertEqual(d['user']['id'], self.ana.id)

    def test_login_mala_clave_401(self):
        r = self.client.post('/api/login/', {'email': 'ana@hestia.com', 'password': 'mal'}, format='json')
        self.assertEqual(r.status_code, 401)

    def test_login_email_inexistente_401(self):
        r = self.client.post('/api/login/', {'email': 'nadie@x.com', 'password': 'clave123'}, format='json')
        self.assertEqual(r.status_code, 401)

    def test_login_faltan_campos_400(self):
        r = self.client.post('/api/login/', {'email': 'ana@hestia.com'}, format='json')
        self.assertEqual(r.status_code, 400)

    # ---- Rutas protegidas ----
    def test_eventos_sin_token_401(self):
        self.assertEqual(self.client.get('/api/eventos/').status_code, 401)

    def test_hoy_sin_token_401(self):
        self.assertEqual(self.client.get('/api/hoy/').status_code, 401)

    def test_eventos_token_invalido_401(self):
        r = self.client.get('/api/eventos/', HTTP_AUTHORIZATION='Bearer token-falso')
        self.assertEqual(r.status_code, 401)

    # ---- Aislamiento ----
    def test_listado_solo_eventos_propios(self):
        r = self.client.get('/api/eventos/', **_auth(self.ana))
        ids = [e['id'] for e in r.json()]
        self.assertEqual(ids, [self.ev_ana.id])

    def test_detalle_evento_ajeno_404(self):
        r = self.client.get(f'/api/eventos/{self.ev_beto.id}/', **_auth(self.ana))
        self.assertEqual(r.status_code, 404)

    def test_detalle_evento_propio_200(self):
        r = self.client.get(f'/api/eventos/{self.ev_ana.id}/', **_auth(self.ana))
        self.assertEqual(r.status_code, 200)

    def test_crear_subtarea_en_evento_ajeno_404(self):
        r = self.client.post(
            f'/api/eventos/{self.ev_beto.id}/subtareas/',
            {'nombre': 'x', 'plazo': '2026-10-01', 'horas_estimadas': '1'},
            format='json', **_auth(self.ana),
        )
        self.assertEqual(r.status_code, 404)

    def test_crear_evento_asigna_organizador(self):
        r = self.client.post(
            '/api/eventos/',
            {'nombre': 'Nuevo', 'tipo': 'boda', 'cliente': 'C', 'fecha_hora': '2026-12-01T10:00:00Z',
             'lugar': 'L', 'plazo_limite': '2026-11-01'},
            format='json', **_auth(self.beto),
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Evento.objects.get(id=r.json()['id']).organizador_id, self.beto.id)

    def test_hoy_aislado(self):
        r = self.client.get('/api/hoy/', **_auth(self.ana))
        d = r.json()
        titulos = [g['titulo'] for g in d['para_hoy']]