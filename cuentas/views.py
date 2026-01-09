# cuentas/views.py

from rest_framework import viewsets, generics, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import EmailTokenObtainPairSerializer, VaultFileSerializer
from .models import Account, VaultFile
from .serializers import AccountSerializer, RegisterSerializer
from .permissions import IsAccountOwnerAndWithinLimit
from .models import PlanConfig, PackConfig
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from core.utils import encrypt_text, decrypt_text
import mercadopago
import traceback


class CreatePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # 1. Recibimos qué quiere comprar el usuario
            plan_id = request.data.get('plan_id')
            pack_id = request.data.get('pack_id')

            product_title = ""
            product_price = 0
            purchase_type = ""
            product_db_id = None

            if plan_id:
                try:
                    item = PlanConfig.objects.get(id=plan_id)
                    product_title = f"Suscripción {item.nombre}"
                    product_price = float(item.precio_mensual)
                    purchase_type = "plan"
                    product_db_id = item.id
                except PlanConfig.DoesNotExist:
                    return Response({"error": "Plan no encontrado"}, status=404)
            
            elif pack_id:
                try:
                    item = PackConfig.objects.get(id=pack_id)
                    product_title = f"Pack {item.nombre}"
                    product_price = float(item.precio)
                    purchase_type = "pack"
                    product_db_id = item.id
                except PackConfig.DoesNotExist:
                    return Response({"error": "Pack no encontrado"}, status=404)
            
            else:
                return Response({"error": "Debes enviar 'plan_id' o 'pack_id'"}, status=400)

            # 2. Configurar MercadoPago
            # Verificamos que el token exista antes de usarlo
            if not getattr(settings, 'MERCADOPAGO_ACCESS_TOKEN', None):
                 raise Exception("La variable MERCADOPAGO_ACCESS_TOKEN no está configurada en settings.")

            sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)

            preference_data = {
                "items": [
                    {
                        "id": str(product_db_id),
                        "title": product_title,
                        "quantity": 1,
                        "currency_id": "CLP",
                        "unit_price": product_price
                    }
                ],
                "metadata": {
                    "user_id": request.user.id,
                    "type": purchase_type,
                    "product_id": product_db_id
                },
                "notification_url": "http://72.60.167.16:8090/api/webhook/mercado-pago/",
                "back_urls": {
                    "success": "http://localhost:5173/payment/success",
                    "failure": "http://localhost:5173/payment/failure",
                    "pending": "http://localhost:5173/payment/pending"
                },
                "auto_return": "approved"
            }

            # 3. Creamos la preferencia y verificamos la respuesta de MP
            print(f"Enviando a MercadoPago: {preference_data}") # Debug en log
            preference_response = sdk.preference().create(preference_data)
            
            # Verificamos si MercadoPago devolvió error
            if preference_response["status"] != 201:
                 print(f"Error de MercadoPago: {preference_response}")
                 return Response({
                     "error": "Error al crear preferencia en MercadoPago", 
                     "detalle": preference_response
                 }, status=400)

            preference = preference_response["response"]

            return Response({
                "init_point": preference["init_point"],
                "preference_id": preference["id"]
            })

        except Exception as e:
            # ESTA ES LA PARTE MÁGICA:
            # Imprime el error en los logs
            traceback.print_exc()
            # Y también te lo devuelve en Postman para que lo leas
            return Response({
                "error_interno": str(e),
                "tipo_error": type(e).__name__
            }, status=500)


class MercadoPagoWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # <--- Importante: Elimina la necesidad de Token

    def post(self, request):
        print("\n🔔 === NOTIFICACIÓN DE MERCADOPAGO RECIBIDA === 🔔")

        topic = request.data.get('topic') or request.data.get('type')
        mp_id = request.data.get('data', {}).get('id')

        print(f"Tipo (topic): {topic}")
        print(f"ID del recurso: {mp_id}")
        print("Data completa:", request.data)
        print("==================================================\n")

        return Response({"status": "recibido"}, status=200)


class SecurityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = request.user.profile
        return Response({
            "configurada": bool(profile.pregunta_seguridad),
            "pregunta": profile.pregunta_seguridad
        })

    def put(self, request):
        pregunta = request.data.get('pregunta')
        respuesta = request.data.get('respuesta')

        if not pregunta or not respuesta:
            return Response({"error": "Faltan datos"}, status=400)

        profile = request.user.profile
        profile.pregunta_seguridad = pregunta
        profile.respuesta_seguridad = encrypt_text(respuesta)
        profile.save()

        return Response({"mensaje": "Seguridad configurada correctamente."})

    def post(self, request):
        respuesta_usuario = request.data.get('respuesta', '')
        profile = request.user.profile

        if not profile.respuesta_seguridad:
            return Response({"error": "No hay seguridad configurada"}, status=400)

        respuesta_real = decrypt_text(profile.respuesta_seguridad)

        if respuesta_real and respuesta_real.lower().strip() == respuesta_usuario.lower().strip():
            return Response({"verificado": True})

        return Response({"error": "Respuesta incorrecta"}, status=401)


class AdRewardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = request.user.profile
        ahora = timezone.now()

        if profile.ultima_vez_anuncio and profile.ultima_vez_anuncio.date() != ahora.date():
            profile.anuncios_vistos_hoy = 0

        # Actualizar métricas
        profile.ultima_vez_anuncio = ahora
        profile.anuncios_vistos_hoy += 1
        profile.total_anuncios_vistos += 1

        # Verificar recompensa (Cada 10 anuncios totales = 1 slot)
        # Nota: Usamos módulo % 10 == 0 para que ocurra en el 10, 20, 30...
        gano_recompensa = False
        if profile.total_anuncios_vistos % 10 == 0:
            profile.extra_slots_cuentas += 1
            gano_recompensa = True

        profile.save()

        return Response({
            "mensaje": "Anuncio registrado correctamente",
            "recompensa_obtenida": gano_recompensa,
            "progreso_para_siguiente": profile.total_anuncios_vistos % 10,
            "total_slots": profile.total_cuentas_permitidas
        })


class VaultFileViewSet(viewsets.ModelViewSet):
    # Podrías agregar el permiso de 'Freezing' aquí también si quieres bloquear subidas a morosos
    permission_classes = [IsAuthenticated]
    serializer_class = VaultFileSerializer
    # Necesario para subir archivos
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        return VaultFile.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class AccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAccountOwnerAndWithinLimit]

    serializer_class = AccountSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['site_name', 'site_url', 'email']

    def get_queryset(self):
        # El usuario siempre puede VER todas sus cuentas, incluso las congeladas.
        return Account.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        asunto = 'Bienvenido a Niun - Tu seguridad es primero'
        mensaje = f"""Hola {user.username}, 

Bienvenido a Niun.
Ya tienes tu cuenta lista para guardar contraseñas, notas y recordatorios.
Ni un olvido, ni un problema.

Atentamente,
Juan Erices.
"""
        remitente = settings.EMAIL_HOST_USER
        destinatario = [user.email]

        # 3. Enviar el correo
        try:
            print(f"Intentando enviar correo a {user.email}...")
            send_mail(asunto, mensaje, remitente,
                      destinatario, fail_silently=False)
            print("✅ Correo enviado con éxito.")
        except Exception as e:
            print(f"❌ Error al enviar el correo: {e}")
