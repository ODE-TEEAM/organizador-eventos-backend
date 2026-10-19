# Organizador de Eventos — API (Backend)

API REST del organizador de eventos independientes (Django + DRF).

## URLs públicas

 Recurso | URL 

 API base | https://organizador-eventos-backend-05nj.onrender.com/api/ 
 Health | https://organizador-eventos-backend-05nj.onrender.com/api/health/ 
 Swagger (docs) | https://organizador-eventos-backend-05nj.onrender.com/api/docs/ 
 Frontend | https://organizador-eventos-frontend.vercel.app 

## Cuenta demo 

- **Email:** prueba1@gmail.com  
- **Contraseña:** 123456  

## Cómo probar

1. Abrir el [frontend](https://organizador-eventos-frontend.vercel.app) o [Swagger](https://organizador-eventos-backend-05nj.onrender.com/api/docs/).
2. Iniciar sesión con la cuenta demo.
3. Crear un evento 
4. Agregar gestiones logísticas (nombre, plazo, horas estimadas).
5. Revisar la vista **Hoy** (vencidas / para hoy / próximas).
6. Reprogramar, marcar como hecha o posponer gestiones.
7. Consultar el progreso del evento.

## Autenticación

Tras `POST /api/login/` o `POST /api/register/`, usar el header:

```http
Authorization: Bearer <token>