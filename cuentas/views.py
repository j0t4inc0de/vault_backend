# cuentas/views.py

from rest_framework import viewsets, generics, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action
from .serializers import EmailTokenObtainPairSerializer, VaultFileSerializer, AnuncioSerializer
from .models import Account, VaultFile, PlanConfig, PackConfig, Anuncio
from .serializers import AccountSerializer, RegisterSerializer
from .permissions import IsAccountOwnerAndWithinLimit
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from core.utils import encrypt_text, decrypt_text
import mercadopago
import traceback


class AnuncioListView(generics.ListAPIView):
    serializer_class = AnuncioSerializer
    # O AllowAny si quieres que se vean en el login
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Anuncio.objects.all()
        # ahora = timezone.now()
        # # Filtramos: Que esté activo Y que la fecha de expiración sea mayor a 'ahora'
        # return Anuncio.objects.filter(
        #     activo=True,
        #     expira_en__gte=ahora
        # ).order_by('-creado_en')


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if not hasattr(user, 'profile'):
            from .models import Profile
            Profile.objects.create(user=user)

        profile = user.profile

        # Valores por defecto
        base_gb = 0
        base_cuentas = 10
        nombre_plan = "Plan Gratuito"
        es_premium = False

        if profile.plan:
            nombre_plan = profile.plan.nombre
            es_premium = profile.plan.sin_anuncios

            # --- 🚀 CORRECCIÓN: USAMOS LOS NOMBRES REALES DEL LOG ---
            base_gb = getattr(profile.plan, 'limite_gb_base', 0)
            base_cuentas = getattr(profile.plan, 'slots_cuentas_base', 10)

        # --- SUMAMOS LOS EXTRAS (Packs comprados) ---
        total_gb = base_gb + getattr(profile, 'extra_gb_almacenamiento', 0)
        total_cuentas = base_cuentas + \
            getattr(profile, 'extra_slots_cuentas', 0)

        # --- CÁLCULO DE USO ---
        cuentas_usadas = Account.objects.filter(user=user).count()

        archivos = VaultFile.objects.filter(user=user)
        total_bytes = sum(a.file.size for a in archivos if a.file)
        usado_mb = round(total_bytes / (1024 * 1024), 2)

        # Calcular porcentaje
        total_mb_permitidos = total_gb * 1024
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
                "nombre": nombre_plan,
                "es_premium": es_premium,
            },
            "limites": {
                "cuentas": {
                    "usadas": cuentas_usadas,
                    "total": total_cuentas,
                    "restantes": max(0, total_cuentas - cuentas_usadas)
                },
                "almacenamiento": {
                    "usado_mb": usado_mb,
                    # Ahora saldrá "5.0" (o más si tienes extras)
                    "total_gb": total_gb,
                    "porcentaje": porcentaje_storage
                },
                "notas": {
                    # También vi este nombre en tu log: 'slots_notas_base'
                    "total": getattr(profile.plan, 'slots_notas_base', 10) if profile.plan else 10
                }
            },
            "gamificacion": {
                "anuncios_vistos": profile.total_anuncios_vistos,
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
            traceback.print_exc()
            return Response({
                "error_interno": str(e),
                "tipo_error": type(e).__name__
            }, status=500)


class MercadoPagoWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        topic = request.data.get('topic') or request.data.get('type')
        mp_id = request.data.get('data', {}).get('id')

        print(f"\n🔔 Notificación MP: {topic} | ID: {mp_id}")

        if topic == 'payment' and mp_id:
            try:
                sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
                payment_info = sdk.payment().get(mp_id)
                payment = payment_info.get('response', {})

                status = payment.get('status')

                if status == 'approved':
                    metadata = payment.get('metadata', {})
                    user_id = metadata.get('user_id')
                    purchase_type = metadata.get(
                        'type')       # 'plan' o 'pack'
                    product_id = metadata.get('product_id')

                    print(
                        f"✅ Pago Aprobado. Usuario: {user_id}, Tipo: {purchase_type}, Producto: {product_id}")

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
            profile = user.profile

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
            "pregunta": profile.pregunta_seguridad,
            "tiene_pin": bool(profile.pin_boveda), # Solo decimos si existe o no
            "intentos_fallidos": profile.intentos_fallidos
        })

    def put(self, request):
        profile = request.user.profile
        data = request.data

        if 'pregunta' in data and 'respuesta' in data:
            profile.pregunta_seguridad = data['pregunta']
            profile.respuesta_seguridad = make_password(data['respuesta'].strip().lower())

        if 'pin_boveda' in data:
            pin = data['pin_boveda']
            if len(pin) < 4:
                return Response({"error": "El PIN debe tener al menos 4 dígitos"}, status=400)
            profile.pin_boveda = make_password(pin)

        profile.save()
        return Response({"mensaje": "Configuración de seguridad actualizada correctamente."})

    def post(self, request):
        pin_ingresado = request.data.get('pin_boveda')
        profile = request.user.profile
        user = request.user

        if not profile.pin_boveda:
            return Response({"error": "PIN no configurado. Configúralo en ajustes."}, status=400)

        if check_password(pin_ingresado, profile.pin_boveda):
            if profile.intentos_fallidos > 0:
                profile.intentos_fallidos = 0
                profile.save()
            return Response({"verificado": True})

        # --- FALLO Y AUTODESTRUCCIÓN ---
        profile.intentos_fallidos += 1
        profile.save()

        if profile.intentos_fallidos >= 10:
            user.delete()
            return Response(
                {"error": "Límite de intentos excedido. Cuenta eliminada por seguridad."}, 
                status=401
            )

        intentos_restantes = 10 - profile.intentos_fallidos
        return Response(
            {"error": f"PIN incorrecto. Te quedan {intentos_restantes} intentos."}, 
            status=401
        )

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
    permission_classes = [IsAuthenticated]
    serializer_class = VaultFileSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        return VaultFile.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Endpoint para descargar y descifrar el archivo.
        Uso: GET /api/files/{id}/download/
        """
        # get_object() ya asegura que el archivo pertenezca al usuario autenticado
        vault_file = self.get_object() 
        
        try:
            # 1. Leer el contenido cifrado (.enc) desde el disco
            with vault_file.file.open('rb') as f:
                encrypted_data = f.read()
            
            # 2. Descifrar los bytes usando la llave maestra
            decrypted_data = decrypt_bytes(encrypted_data)

            # 3. Determinar el tipo de contenido original (image/png, application/pdf, etc.)
            content_type, _ = mimetypes.guess_type(vault_file.name)
            if not content_type:
                content_type = 'application/octet-stream'

            # 4. Devolver la respuesta con el archivo original descifrado
            response = HttpResponse(decrypted_data, content_type=content_type)
            # Se usa el nombre original guardado en el modelo para la descarga
            response['Content-Disposition'] = f'attachment; filename="{vault_file.name}"'
            
            return response

        except Exception as e:
            print(f"Error al descifrar archivo {pk}: {e}")
            return Response(
                {"error": "No se pudo procesar el archivo o la llave es incorrecta."}, 
                status=500
            )


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class AccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAccountOwnerAndWithinLimit]

    serializer_class = AccountSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['site_name', 'site_url', 'email']

    def get_queryset(self):
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

        try:
            print(f"Intentando enviar correo a {user.email}...")
            send_mail(asunto, mensaje, remitente,
                      destinatario, fail_silently=False)
            print("✅ Correo enviado con éxito.")
        except Exception as e:
            print(f"❌ Error al enviar el correo: {e}")
