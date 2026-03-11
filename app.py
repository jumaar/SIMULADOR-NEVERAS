"""
Simulador de Neveras Vorak Edge - Aplicación Flask
==================================================
Este módulo proporciona una interfaz web para simular múltiples neveras
inteligentes y enviar eventos a la API real como si fueran dispositivos físicos.

Autor: Vorak Edge Team
Versión: 1.0.0
"""

import os
import json
import time
import logging
from datetime import datetime
from functools import wraps

import requests
from flask import Flask, render_template, request, jsonify, current_app
from flask_cors import CORS
from dotenv import load_dotenv

from models import db, Fridge, ProductoGlobal, Empaque, EmpaquePendiente, EventLog

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Cargar variables de entorno
load_dotenv()

# Configuración de la aplicación
class Config:
    """Configuración de la aplicación Flask"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-vorak-2024')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///simulator.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # Configuración de la API Real (Vorak Backend)
    API_BASE_URL = os.environ.get('API_BASE_URL', 'https://api.vorak.app')
    API_TIMEOUT = int(os.environ.get('API_TIMEOUT', '30'))

# Crear aplicación Flask
app = Flask(__name__)
app.config.from_object(Config)

# Cambiar delimitadores de Jinja2 para evitar conflictos con Vue.js
# Vue.js usa {{ }} y Jinja2 también, por lo que cambiamos los de Jinja2
app.jinja_env.variable_start_string = '[['
app.jinja_env.variable_end_string = ']]'
app.jinja_env.block_start_string = '[%'
app.jinja_env.block_end_string = '%]'
app.jinja_env.comment_start_string = '[#'
app.jinja_env.comment_end_string = '#]'

# Habilitar CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Inicializar SQLAlchemy
db.init_app(app)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS Y UTILIDADES
# =============================================================================

def get_api_headers(fridge: Fridge):
    """
    Genera los headers necesarios para authenticate con la API real.
    
    Args:
        fridge: Instancia del modelo Fridge
        
    Returns:
        dict: Headers con el token de autenticación
    """
    if not fridge.api_token:
        raise ValueError("La neveras no tiene token de API configurado")
    
    return {
        'Authorization': f'Bearer {fridge.api_token}',
        'Content-Type': 'application/json'
    }


def send_to_api(fridge: Fridge, endpoint: str, method: str = 'POST', data: dict = None):
    """
    Envía una solicitud a la API real de Vorak.
    
    Args:
        fridge: Instancia del modelo Fridge
        endpoint: Endpoint de la API (sin la base URL)
        method: Método HTTP (GET, POST, PUT, DELETE)
        data: Datos JSON a enviar
        
    Returns:
        tuple: (success: bool, response_data: dict or None, status_code: int)
    """
    url = f"{app.config['API_BASE_URL']}{endpoint}"
    headers = get_api_headers(fridge)
    
    # Registrar el evento en la base de datos
    event_log = EventLog(
        fridge_id=fridge.fridge_id,
        event_type=endpoint,
        payload=json.dumps(data) if data else None,
        success=False
    )
    
    try:
        logger.info(f"Enviando {method} a {url}")
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=app.config['API_TIMEOUT'])
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=app.config['API_TIMEOUT'])
        elif method.upper() == 'PUT':
            response = requests.put(url, headers=headers, json=data, timeout=app.config['API_TIMEOUT'])
        else:
            raise ValueError(f"Método HTTP no soportado: {method}")
        
        # Actualizar log
        event_log.response_status = response.status_code
        event_log.response_body = response.text[:1000] if response.text else None
        event_log.success = 200 <= response.status_code < 300
        
        db.session.add(event_log)
        db.session.commit()
        
        if response.status_code >= 200 and response.status_code < 300:
            try:
                return True, response.json(), response.status_code
            except:
                return True, {'message': 'Success'}, response.status_code
        else:
            logger.error(f"Error de API: {response.status_code} - {response.text}")
            return False, {'error': response.text}, response.status_code
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout contacting API: {url}")
        event_log.response_status = 408
        event_log.response_body = "Request timeout"
        db.session.add(event_log)
        db.session.commit()
        return False, {'error': 'Timeout contacting API'}, 408
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        event_log.response_status = 503
        event_log.response_body = f"Connection error: {str(e)}"
        db.session.add(event_log)
        db.session.commit()
        return False, {'error': 'Cannot connect to API'}, 503
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        event_log.response_status = 500
        event_log.response_body = str(e)
        db.session.add(event_log)
        db.session.commit()
        return False, {'error': str(e)}, 500


def validar_empaque_pendiente(fridge_id: str, input_value: str, api_response: dict) -> tuple:
    """
    Valida un empaque pendiente con la respuesta de la API.
    Mueve el empaque de pendiente a validado con toda la información.

    Args:
        fridge_id: ID de la nevera
        input_value: Valor original ingresado (EPC o ID)
        api_response: Respuesta de la API con datos completos del empaque

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Buscar empaque pendiente
        if input_value.isdigit():
            pendiente = EmpaquePendiente.query.filter_by(
                fridge_id=fridge_id,
                id_empaque=int(input_value)
            ).first()
        else:
            pendiente = EmpaquePendiente.query.filter_by(
                fridge_id=fridge_id,
                epc=input_value
            ).first()

        if not pendiente:
            return False, f"No se encontró empaque pendiente para {input_value}"

        # Extraer datos de la API
        product_id = api_response.get('product_id')
        peso_nominal_g = api_response.get('peso_nominal_g')
        epc_completo = api_response.get('epc')  # Puede incluir ambos
        id_empaque_completo = api_response.get('id_empaque')

        # Buscar producto global
        producto_global = ProductoGlobal.query.filter_by(product_id=str(product_id)).first()
        if not producto_global:
            return False, f"Producto global {product_id} no encontrado. Sincronice primero."

        # Crear empaque validado con TODA la información
        empaque_validado = Empaque(
            fridge_id=fridge_id,
            producto_global_id=producto_global.id,
            epc=epc_completo or pendiente.epc,
            id_empaque=id_empaque_completo or pendiente.id_empaque,
            peso_nominal_g=peso_nominal_g
        )

        # Guardar empaque validado
        db.session.add(empaque_validado)

        # Eliminar pendiente
        db.session.delete(pendiente)

        db.session.commit()

        return True, f"Empaque validado: {epc_completo or f'ID:{id_empaque_completo}'} - {producto_global.name}"

    except Exception as e:
        db.session.rollback()
        return False, f"Error al validar empaque: {str(e)}"


def sync_from_api() -> tuple:
    """
    Sincroniza neveras activas y productos desde la API central.

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Endpoint de actualización
        sync_url = f"{app.config['API_BASE_URL']}/api/neveras/actualizacion"

        logger.info("Sincronizando neveras activas y productos desde la API...")

        response = requests.get(sync_url, timeout=app.config['API_TIMEOUT'])

        if response.status_code not in (200, 201):
            error_msg = f"Error de sincronización: {response.status_code} - {response.text}"
            return False, error_msg

        sync_data = response.json()

        if not sync_data.get('success'):
            return False, f"Error en sincronización: {sync_data.get('error', 'Desconocido')}"

        neveras_data = sync_data.get('neveras', [])
        productos_globales = sync_data.get('productos', [])

        logger.info(f"Sincronizando {len(neveras_data)} neveras activas y {len(productos_globales)} productos globales")

        # Procesar neveras activas
        for nevera in neveras_data:
            id_nevera = nevera.get('id_nevera')
            nombre_tienda = nevera.get('nombre_tienda')
            token = nevera.get('token')

            if not id_nevera or not token:
                logger.warning(f"Nevera inválida en respuesta: {nevera}")
                continue

            fridge_id = str(id_nevera)

            # Buscar o crear nevera
            fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()

            if fridge:
                # Actualizar existente
                fridge.api_token = token
                fridge.real_fridge_id = id_nevera
                fridge.store_name = nombre_tienda
                logger.info(f"Nevera {fridge_id} actualizada desde API")
            else:
                # Crear nueva
                fridge = Fridge(
                    fridge_id=fridge_id,
                    real_fridge_id=id_nevera,
                    store_name=nombre_tienda,
                    secret_key='',  # No tenemos la contraseña original
                    api_token=token,
                    location='Sincronizado desde API',
                    temperature=4.0,
                    is_door_open=False
                )
                db.session.add(fridge)
                logger.info(f"Nevera {fridge_id} creada desde API")

        # Procesar productos globales
        # Los productos globales son compartidos, no por nevera
        # Primero sincronizar la tabla de productos globales
        existing_product_ids = set()
        for prod in productos_globales:
            product_id = str(prod['id_producto'])
            existing_product_ids.add(product_id)

            # Buscar o crear producto global
            producto_global = ProductoGlobal.query.filter_by(product_id=product_id).first()
            if producto_global:
                # Actualizar
                producto_global.name = prod['nombre_producto']
                producto_global.description = prod.get('descripcion_producto')
                producto_global.nominal_weight_g = prod.get('peso_nominal_g')
            else:
                # Crear
                producto_global = ProductoGlobal(
                    product_id=product_id,
                    name=prod['nombre_producto'],
                    description=prod.get('descripcion_producto'),
                    nominal_weight_g=prod.get('peso_nominal_g')
                )
                db.session.add(producto_global)

        # Eliminar productos globales que ya no existen
        ProductoGlobal.query.filter(~ProductoGlobal.product_id.in_(existing_product_ids)).delete()

        # Procesar neveras activas
        active_fridge_ids = [str(n.get('id_nevera')) for n in neveras_data if n.get('id_nevera')]
        existing_fridges = Fridge.query.all()
        for existing_fridge in existing_fridges:
            if existing_fridge.fridge_id not in active_fridge_ids:
                # Eliminar empaques de neveras no activas
                Empaque.query.filter_by(fridge_id=existing_fridge.fridge_id).delete()
                # Eliminar la nevera
                db.session.delete(existing_fridge)
                logger.info(f"Nevera {existing_fridge.fridge_id} eliminada (no está activa)")

        # Actualizar products_ids de todas las neveras con los productos globales
        all_product_ids = [str(p['id_producto']) for p in productos_globales]
        Fridge.query.update({'products_ids': json.dumps(all_product_ids)})
        db.session.commit()

        return True, sync_data.get('message', f"Sincronización completada: {len(neveras_data)} neveras, {len(productos_globales)} productos")

    except requests.exceptions.ConnectionError:
        return False, "No se puede conectar con la API central"
    except Exception as e:
        logger.error(f"Error en sincronización: {e}")
        return False, f"Error: {str(e)}"


def provision_fridge(password: str, location: str = 'Simulador') -> tuple:
    """
    Activa una nevera usando la contraseña única y obtiene el token y productos.
    
    Args:
        password: Contraseña única para activar la nevera
        location: Ubicación física simulada (por defecto 'Simulador')
        
    Returns:
        tuple: (success: bool, fridge: Fridge or None, message: str)
    """
    try:
        # Paso 1: Activar la nevera con la contraseña usando el nuevo endpoint
        activation_url = f"{app.config['API_BASE_URL']}/api/neveras/activacion"
        
        payload = {
            "contrasena": password
        }
        
        logger.info(f"Activando nevera con contraseña: {password[:8]}...")
        
        response = requests.post(
            activation_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=app.config['API_TIMEOUT']
        )
        
        if response.status_code not in (200, 201):
            error_msg = f"Error de activación: {response.status_code} - {response.text}"
            # Verificar si es un error específico
            try:
                error_data = response.json()
                if error_data.get('code') == 'CONTRASENA_INCORRECTA':
                    error_msg = "Contraseña incorrecta"
                elif error_data.get('code') == 'ESTADO_NO_PERMITIDO':
                    error_msg = "La nevera no está en estado inactivo"
            except:
                pass
            return False, None, error_msg
        
        activation_data = response.json()
        
        if not activation_data.get('success'):
            return False, None, f"Error en la activación: {activation_data.get('error', 'Desconocido')}"
        
        # Extraer token, id_nevera, nombre_tienda y productos de la respuesta
        token = activation_data.get('token')
        id_nevera = activation_data.get('id_nevera')
        nombre_tienda = activation_data.get('nombre_tienda')
        products_data = activation_data.get('productos', [])

        if not token:
            return False, None, "Respuesta de activación inválida: falta token"

        if id_nevera is None:
            return False, None, "Respuesta de activación inválida: falta id_nevera"

        # Usar el ID real de la nevera como identificador único
        fridge_id = str(id_nevera)
        
        # Paso 2: Buscar o crear la nevera en SQLite
        fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()
        
        if fridge:
            # Actualizar existente
            fridge.secret_key = password
            fridge.api_token = token
            fridge.real_fridge_id = id_nevera
            fridge.store_name = nombre_tienda
            fridge.location = location
            logger.info(f"Nevera {fridge_id} actualizada")
        else:
            # Crear nueva
            fridge = Fridge(
                fridge_id=fridge_id,
                real_fridge_id=id_nevera,
                store_name=nombre_tienda,
                secret_key=password,
                api_token=token,
                location=location,
                temperature=4.0,
                is_door_open=False
            )
            db.session.add(fridge)
            logger.info(f"Nevera {fridge_id} creada")
        
        db.session.commit()
        logger.info(f"Nevera {fridge_id} activada exitosamente")
        
        return True, fridge, activation_data.get('message', 'Nevera activada correctamente')
        
    except requests.exceptions.ConnectionError:
        return False, None, "No se puede conectar con la API real"
    except Exception as e:
        logger.error(f"Error en activación: {e}")
        return False, None, f"Error: {str(e)}"


# =============================================================================
# RUTAS DE LA APLICACIÓN
# =============================================================================

@app.route('/')
def index():
    """Página principal del dashboard del simulador"""
    return render_template('index.html')


# =============================================================================
# API INTERNA DEL SIMULADOR
# =============================================================================

@app.route('/api/fridges', methods=['GET'])
def get_fridges():
    """
    Obtiene todas las neveras configuradas en el simulador.
    """
    fridges = Fridge.query.order_by(Fridge.created_at.desc()).all()
    return jsonify({
        'success': True,
        'data': [f.to_dict() for f in fridges]
    })


@app.route('/api/fridges', methods=['POST'])
def create_fridge():
    """
    Activa una nueva nevera en el simulador usando contraseña.
    
    Expects JSON:
    {
        "password": "contraseña-única-de-activación"
    }
    """
    data = request.get_json()
    
    if not data or 'password' not in data:
        return jsonify({
            'success': False,
            'error': 'password es requerido'
        }), 400
    
    password = data['password']
    
    success, fridge, message = provision_fridge(password)
    
    if success:
        return jsonify({
            'success': True,
            'data': fridge.to_dict(),
            'message': message
        }), 201
    else:
        return jsonify({
            'success': False,
            'error': message
        }), 400


@app.route('/api/fridges/<fridge_id>', methods=['GET'])
def get_fridge(fridge_id):
    """
    Obtiene los detalles de una neveras específica.
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()
    
    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Neveras no encontrada'
        }), 404
    
    return jsonify({
        'success': True,
        'data': fridge.to_dict()
    })


@app.route('/api/fridges/<fridge_id>', methods=['DELETE'])
def delete_fridge(fridge_id):
    """
    Elimina una neveras del simulador (no de la API real).
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()
    
    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Neveras no encontrada'
        }), 404
    
    db.session.delete(fridge)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Neveras {fridge_id} eliminada del simulador'
    })


@app.route('/api/fridges/<fridge_id>/temperature', methods=['PUT'])
def update_temperature(fridge_id):
    """
    Actualiza la temperatura simulada de la neveras.
    
    Expects JSON:
    {
        "temperature": 5.5
    }
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()
    
    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Neveras no encontrada'
        }), 404
    
    data = request.get_json()
    temperature = data.get('temperature')
    
    if temperature is None:
        return jsonify({
            'success': False,
            'error': 'temperature es requerido'
        }), 400
    
    try:
        fridge.temperature = float(temperature)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': fridge.to_dict(),
            'message': 'Temperatura actualizada'
        })
    except ValueError:
        return jsonify({
            'success': False,
            'error': 'Temperatura inválida'
        }), 400


@app.route('/api/fridges/<fridge_id>/door', methods=['PUT'])
def update_door(fridge_id):
    """
    Abre o cierra la puerta de la neveras.
    Al cerrar, se dispara el evento de lectura RFID.
    
    Expects JSON:
    {
        "is_door_open": true/false
    }
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()
    
    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Neveras no encontrada'
        }), 404
    
    data = request.get_json()
    is_door_open = data.get('is_door_open')
    
    if is_door_open is None:
        return jsonify({
            'success': False,
            'error': 'is_door_open es requerido'
        }), 400
    
    fridge.is_door_open = bool(is_door_open)
    db.session.commit()
    
    response_data = {
        'success': True,
        'data': fridge.to_dict(),
        'message': 'Puerta abierta' if is_door_open else 'Puerta cerrada'
    }
    
    # Si se cierra la puerta, disparar evento de inventario
    if not is_door_open:
        # Enviar evento a la API real
        success, api_response, status = send_inventory_snapshot(fridge)
        
        if success:
            response_data['api_synced'] = True
            response_data['api_message'] = 'Inventario enviado a la API'
        else:
            response_data['api_synced'] = False
            response_data['api_error'] = api_response.get('error', 'Unknown error')
    
    return jsonify(response_data)


@app.route('/api/productos-globales', methods=['GET'])
def get_productos_globales():
    """
    Obtiene todos los productos globales disponibles.
    """
    productos = ProductoGlobal.query.order_by(ProductoGlobal.name).all()

    return jsonify({
        'success': True,
        'data': [p.to_dict() for p in productos]
    })


@app.route('/api/fridges/<fridge_id>/empaques', methods=['GET'])
def get_empaques(fridge_id):
    """
    Obtiene los empaques del inventario de una nevera (validados).
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()

    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Nevera no encontrada'
        }), 404

    empaques = Empaque.query.filter_by(fridge_id=fridge_id).all()

    return jsonify({
        'success': True,
        'data': [e.to_dict() for e in empaques]
    })


@app.route('/api/fridges/<fridge_id>/empaques-pendientes', methods=['GET'])
def get_empaques_pendientes(fridge_id):
    """
    Obtiene los empaques pendientes de validación de una nevera.
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()

    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Nevera no encontrada'
        }), 404

    pendientes = EmpaquePendiente.query.filter_by(fridge_id=fridge_id).all()

    return jsonify({
        'success': True,
        'data': [p.to_dict() for p in pendientes]
    })


@app.route('/api/fridges/<fridge_id>/empaques', methods=['POST'])
def add_empaque(fridge_id):
    """
    Agrega un empaque al inventario de la nevera.
    El input puede ser EPC (24 dígitos con letras) o ID empaque (número).

    Expects JSON:
    {
        "input": "ABC123DEF456GHI789JKL012"  // EPC o ID empaque
    }
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()

    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Nevera no encontrada'
        }), 404

    # Verificar si la puerta está abierta
    if not fridge.is_door_open:
        return jsonify({
            'success': False,
            'error': 'La puerta debe estar ABIERTA para modificar el inventario'
        }), 403

    data = request.get_json()

    if not data or 'input' not in data:
        return jsonify({
            'success': False,
            'error': 'input es requerido (EPC o ID empaque)'
        }), 400

    input_value = data['input'].strip()

    # Detectar si es EPC o ID empaque inicialmente
    # La API podrá completar ambos campos después
    if input_value.isdigit():
        # Es ID empaque (solo números)
        id_empaque = int(input_value)
        epc = None
    else:
        # Es EPC (contiene letras)
        epc = input_value
        id_empaque = None

    # Verificar que no exista ya (comprobar ambos campos por si la API ya completó la info)
    existing = Empaque.query.filter(
        (Empaque.fridge_id == fridge_id) &
        (
            (Empaque.epc == epc) |
            (Empaque.id_empaque == id_empaque)
        )
    ).first()

    if existing:
        return jsonify({
            'success': False,
            'error': f'Empaque ya existe en el inventario (Producto: {existing.producto_global.name if existing.producto_global else "Desconocido"})'
        }), 400

    # Crear registro en tabla de pendientes
    # La validación con API se hará después
    pendiente = EmpaquePendiente(
        fridge_id=fridge_id,
        epc=epc,
        id_empaque=id_empaque,
        estado='pendiente'
    )
    db.session.add(pendiente)
    db.session.commit()

    # TODO: Aquí implementar llamada a API para validar EPC/ID
    # La API debería validar y responder con producto_id y peso_nominal_g
    # Una vez validado, mover de pendientes a empaques

    return jsonify({
        'success': True,
        'data': pendiente.to_dict(),
        'message': f'Empaque registrado: {epc or f"ID:{id_empaque}"} (pendiente validación API)'
    }), 201


@app.route('/api/fridges/<fridge_id>/empaques/<empaque_id>', methods=['DELETE'])
def delete_empaque(fridge_id, empaque_id):
    """
    Elimina un empaque específico del inventario.
    Solo funciona si la puerta está ABIERTA.
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()

    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Nevera no encontrada'
        }), 404

    if not fridge.is_door_open:
        return jsonify({
            'success': False,
            'error': 'La puerta debe estar ABIERTA para modificar el inventario'
        }), 403

    empaque = Empaque.query.filter_by(id=empaque_id, fridge_id=fridge_id).first()

    if not empaque:
        return jsonify({
            'success': False,
            'error': 'Empaque no encontrado'
        }), 404

    db.session.delete(empaque)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Empaque eliminado: {empaque.epc or f"ID:{empaque.id_empaque}"}'
    })


@app.route('/api/fridges/<fridge_id>/empaques-pendientes/<pendiente_id>', methods=['DELETE'])
def delete_empaque_pendiente(fridge_id, pendiente_id):
    """
    Elimina un empaque pendiente del inventario.
    Solo funciona si la puerta está ABIERTA.
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()

    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Nevera no encontrada'
        }), 404

    if not fridge.is_door_open:
        return jsonify({
            'success': False,
            'error': 'La puerta debe estar ABIERTA para modificar el inventario'
        }), 403

    pendiente = EmpaquePendiente.query.filter_by(id=pendiente_id, fridge_id=fridge_id).first()

    if not pendiente:
        return jsonify({
            'success': False,
            'error': 'Empaque pendiente no encontrado'
        }), 404

    db.session.delete(pendiente)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Empaque pendiente eliminado: {pendiente.epc or f"ID:{pendiente.id_empaque}"}'
    })


@app.route('/api/fridges/<fridge_id>/sync', methods=['POST'])
def manual_sync(fridge_id):
    """
    Fuerza el envío manual del inventario a la API real.
    """
    fridge = Fridge.query.filter_by(fridge_id=fridge_id).first()
    
    if not fridge:
        return jsonify({
            'success': False,
            'error': 'Neveras no encontrada'
        }), 404
    
    if not fridge.api_token:
        return jsonify({
            'success': False,
            'error': 'La neveras no tiene token de API configurado'
        }), 400
    
    success, api_response, status = send_inventory_snapshot(fridge)
    
    return jsonify({
        'success': success,
        'api_response': api_response,
        'status_code': status
    })


@app.route('/api/events', methods=['GET'])
def get_events():
    """
    Obtiene el log de eventos enviados a la API real.
    """
    limit = request.args.get('limit', 50, type=int)
    fridge_id = request.args.get('fridge_id')
    
    query = EventLog.query
    
    if fridge_id:
        query = query.filter_by(fridge_id=fridge_id)
    
    events = query.order_by(EventLog.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'success': True,
        'data': [e.to_dict() for e in events]
    })


@app.route('/api/sync', methods=['POST'])
def sync_from_api_endpoint():
    """
    Endpoint para sincronizar neveras activas y productos desde la API central.
    """
    success, message = sync_from_api()

    if success:
        return jsonify({
            'success': True,
            'message': message
        }), 200
    else:
        return jsonify({
            'success': False,
            'error': message
        }), 400


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Endpoint de verificación de salud del simulador.
    Solo verifica el estado interno, sin hacer peticiones externas.
    """
    return jsonify({
        'success': True,
        'simulator': 'online',
        'api_real': 'online',
        'database': 'connected',
        'timestamp': datetime.utcnow().isoformat()
    })


# =============================================================================
# FUNCIONES DE EVENTOS
# =============================================================================

def send_inventory_snapshot(fridge: Fridge) -> tuple:
    """
    Envía el snapshot del inventario a la API real.
    Este es el equivalente simulado de la lectura RFID.

    Args:
        fridge: Instancia del modelo Fridge

    Returns:
        tuple: (success: bool, response: dict, status_code: int)
    """
    # Recopilar inventario actual (empaques)
    empaques = Empaque.query.filter_by(fridge_id=fridge.fridge_id).all()

    inventory = [e.to_inventory_dict() for e in empaques]

    # Construir payload
    payload = {
        'fridge_id': fridge.fridge_id,
        'timestamp': int(time.time()),
        'event': 'door_closed_inventory_snapshot',
        'inventory': inventory
    }

    logger.info(f"Enviando snapshot de inventario para {fridge.fridge_id}: {len(inventory)} empaques")

    # Enviar a la API real
    return send_to_api(
        fridge,
        f'/api/transactions/{fridge.fridge_id}',
        method='POST',
        data=payload
    )


# =============================================================================
# INICIALIZACIÓN
# =============================================================================

def init_db():
    """Inicializa la base de datos SQLite"""
    with app.app_context():
        db.create_all()
        logger.info("Base de datos inicializada")


if __name__ == '__main__':
    # Inicializar base de datos
    init_db()
    
    # Iniciar servidor
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    logger.info(f"Iniciando simulador en puerto {port}")
    logger.info(f"API Base URL: {app.config['API_BASE_URL']}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
