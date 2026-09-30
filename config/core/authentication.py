from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    """
    Autenticación por token con el esquema 'Bearer' que usa el frontend.

    El frontend envía: Authorization: Bearer <token>
    DRF por defecto usa 'Token <token>', así que solo cambiamos la palabra clave.
    """
    keyword = 'Bearer'

    def authenticate_header(self, request):
        # Hace que DRF responda 401 (y no 403) cuando falta o es inválido el token.
        return 'Bearer'