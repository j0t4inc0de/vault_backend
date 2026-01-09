# cuentas/views.py

from rest_framework import viewsets, generics, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import EmailTokenObtainPairSerializer, VaultFileSerializer
from .models import Account, VaultFile, PlanConfig, PackConfig
from .serializers import AccountSerializer, RegisterSerializer
from .permissions import IsAccountOwnerAndWithinLimit
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from core.utils import encrypt_text, decrypt_text
import mercadopago
import traceback


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile = user.profile

        # 1. Calcular Cuentas (Slots)
        cuentas_usadas = Account.objects.filter(user=user).count()

        # 2. Calcular Almacenamiento
        # Sumamos el tamaño real de los archivos subidos (en bytes)
        archivos = VaultFile.objects.filter(user=user)
        total_bytes = 0
        for archivo in archivos:
            try:
                if archivo.file:
                    total_bytes += archivo.file.size
            except Exception:
                pass  # Si un archivo falla, seguimos sumando el resto

        # Convertimos a MB para facilitar la vida al Frontend
        usado_mb = round(total_bytes / (1024 * 1024), 2)

        # Calculamos el % de almacenamiento (evitando división por cero)
        total_gb_permitidos = profile.total_almacenamiento_gb
        total_mb_permitidos = total_gb_permitidos * 1024
        porcentaje_storage = 0
        if total_mb_permitidos > 0:
            porcentaje_storage = round(
                (usado_mb / total_mb_permitidos) * 100, 1)

        return Response({
            "usuario": {
                "username": user.username,
                "email": user.email,
                "fecha_unio": user.date_joined.strftime("%Y-%m-%d"),
            },
            "plan": {
                "nombre": profile.plan.nombre if profile.plan else "Plan Gratuito",
                "es_premium": profile.plan.sin_anuncios if profile.plan else False,
            },
            "limites": {
                "cuentas": {
                    "usadas": cuentas_usadas,
                    "total": profile.total_cuentas_permitidas,
                    "restantes": profile.total_cuentas_permitidas - cuentas_usadas
                },
                "almacenamiento": {
                    "usado_mb": usado_mb,
                    "total_gb": total_gb_permitidos,
                    "porcentaje": porcentaje_storage
                },
                "notas": {
                    "total": profile.total_notas_permitidas
                    # Podrías agregar "usadas" si creas un modelo de Notas a futuro
                }
            },
            "gamificacion": {
                "anuncios_vistos": profile.total_anuncios_vistos,
                # 3/10 para el siguiente slot
                "progreso_recompensa": profile.total_anuncios_vistos % 10,
            }
        })


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
                raise Exception(
                    "La variable MERCADOPAGO_ACCESS_TOKEN no está configurada en settings.")

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
                    "success": "https://www.google.com/search?q=pago_exitoso",
                    "failure": "https://www.google.com/search?q=pago_fallado",
                    "pending": "https://www.google.com/search?q=pago_pendiente"
                },
                "auto_return": "approved"
            }

            # 3. Creamos la preferencia y verificamos la respuesta de MP
            print(f"Enviando a MercadoPago: {preference_data}")  # Debug en log
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
    authentication_classes = []  # No requerimos token, MP es quien llama

    def post(self, request):
        topic = request.data.get('topic') or request.data.get('type')
        mp_id = request.data.get('data', {}).get('id')

        print(f"\n🔔 Notificación MP: {topic} | ID: {mp_id}")

        if topic == 'payment' and mp_id:
            try:
                # 1. Consultar a MP el estado real del pago
                sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
                payment_info = sdk.payment().get(mp_id)
                payment = payment_info.get('response', {})

                status = payment.get('status')

                if status == 'approved':
                    # 2. Leer la metadata que guardamos al crear el pago
                    metadata = payment.get('metadata', {})
                    user_id = metadata.get('user_id')
                    purchase_type = metadata.get(
                        'type')       # 'plan' o 'pack'
                    product_id = metadata.get('product_id')

                    print(
                        f"✅ Pago Aprobado. Usuario: {user_id}, Tipo: {purchase_type}, Producto: {product_id}")

                    # 3. Procesar la entrega del producto
                    if user_id and purchase_type and product_id:
                        self.activar_producto(
                            user_id, purchase_type, product_id)

                else:
                    print(f"⚠️ Pago no aprobado. Estado: {status}")

            except Exception as e:
                print(f"❌ Error procesando webhook: {e}")

        return Response({"status": "recibido"}, status=200)

    def activar_producto(self, user_id, tipo, product_id):
        try:
            user = User.objects.get(id=user_id)
            profile = user.profile  # Accedemos al perfil (OneToOne)

            if tipo == 'plan':
                # CAMBIO DE PLAN (Suscripción)
                plan = PlanConfig.objects.get(id=product_id)
                profile.plan = plan
                print(f"🚀 Plan actualizado a: {plan.nombre}")

            elif tipo == 'pack':
                # COMPRA DE PACK (Acumulativo)
                pack = PackConfig.objects.get(id=product_id)
                profile.extra_slots_cuentas += pack.extra_slots_cuentas
                profile.extra_gb_almacenamiento += pack.extra_gb
                profile.extra_slots_notas += pack.extra_notas
                profile.extra_slots_recordatorios += pack.extra_recordatorios
                print(
                    f"📦 Pack aplicado: +{pack.extra_slots_cuentas} slots, +{pack.extra_gb}GB")

            profile.save()

        except Exception as e:
            print(f"❌ Error activando producto en DB: {e}")


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
