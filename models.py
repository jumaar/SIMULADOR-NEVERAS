"""
Modelos de Base de Datos para el Simulador de Neveras Vorak Edge
SQLite + SQLAlchemy
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Fridge(db.Model):
    """
    Representa una neveras inteligente simulada.
    Persiste la configuración y estado actual de la nevera.
    """
    __tablename__ = 'fridges'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fridge_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    real_fridge_id = db.Column(db.Integer, nullable=True)  # ID real de la nevera de la API
    store_name = db.Column(db.String(128), nullable=True)  # Nombre de la tienda
    secret_key = db.Column(db.String(128), nullable=False)
    api_token = db.Column(db.String(256), nullable=True)
    location = db.Column(db.String(128), nullable=True, default='Unknown')

    # Productos asociados a esta nevera (de la activación)
    products_ids = db.Column(db.Text, nullable=True)  # JSON string con lista de product_ids

    # Estado simulado de sensores
    temperature = db.Column(db.Float, nullable=False, default=4.0)
    is_door_open = db.Column(db.Boolean, nullable=False, default=False)
    weight_adjustment = db.Column(db.Float, nullable=False, default=0.0)

    # Última sincronización con la API
    last_sync = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relación con empaques
    empaques = db.relationship('Empaque', backref='fridge', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON"""
        return {
            'id': self.id,
            'fridge_id': self.fridge_id,
            'real_fridge_id': self.real_fridge_id,
            'store_name': self.store_name,
            'location': self.location,
            'temperature': self.temperature,
            'is_door_open': self.is_door_open,
            'weight_adjustment': self.weight_adjustment,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'has_token': self.api_token is not None,
            'products_ids': self.products_ids,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<Fridge {self.fridge_id}>'


class ProductoGlobal(db.Model):
    """
    Representa un producto global disponible en el sistema.
    Estos son los productos base que se sincronizan desde la API central.
    """
    __tablename__ = 'productos_globales'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Identificación del producto (ID del producto de la API)
    product_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(256), nullable=True)
    nominal_weight_g = db.Column(db.Integer, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relación con empaques
    empaques = db.relationship('Empaque', backref='producto_global', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON"""
        return {
            'id': self.id,
            'product_id': self.product_id,
            'name': self.name,
            'description': self.description,
            'nominal_weight_g': self.nominal_weight_g,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<ProductoGlobal {self.product_id} ({self.name})>'


class Empaque(db.Model):
    """
    Representa un empaque individual en el inventario de una nevera.
    Cada empaque tiene un EPC o ID único y pertenece a un producto global.
    """
    __tablename__ = 'inventario_empaques'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fridge_id = db.Column(db.String(64), db.ForeignKey('fridges.fridge_id'), nullable=False, index=True)
    producto_global_id = db.Column(db.Integer, db.ForeignKey('productos_globales.id'), nullable=True, index=True)

    # Identificación del empaque
    epc = db.Column(db.String(24), nullable=True)  # EPC de 24 dígitos (puede contener letras)
    id_empaque = db.Column(db.Integer, nullable=True)  # ID numérico del empaque

    # Datos que se obtienen de la API después de agregar
    peso_nominal_g = db.Column(db.Float, nullable=True)  # Peso real del empaque

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Índices únicos - Un empaque puede tener ambos EPC e ID
    __table_args__ = (
        db.UniqueConstraint('fridge_id', 'epc', name='uix_fridge_epc'),
        db.UniqueConstraint('fridge_id', 'id_empaque', name='uix_fridge_id_empaque'),
        # Permitir que un empaque tenga ambos, pero no duplicados
    )

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON"""
        return {
            'id': self.id,
            'fridge_id': self.fridge_id,
            'producto_global_id': self.producto_global_id,
            'product_id': self.producto_global.product_id if self.producto_global else None,
            'product_name': self.producto_global.name if self.producto_global else None,
            'epc': self.epc,
            'id_empaque': self.id_empaque,
            'peso_nominal_g': self.peso_nominal_g,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def to_inventory_dict(self):
        """Formato para el payload de inventario enviado a la API"""
        return {
            'epc': self.epc,
            'id_empaque': self.id_empaque,
            'peso_nominal_g': self.peso_nominal_g
        }

    def __repr__(self):
        identifiers = []
        if self.epc:
            identifiers.append(f"EPC:{self.epc}")
        if self.id_empaque:
            identifiers.append(f"ID:{self.id_empaque}")
        identifier = " | ".join(identifiers) if identifiers else "Sin ID"
        return f'<Empaque {identifier} ({self.producto_global.name if self.producto_global else "Unknown"})>'


class EmpaquePendiente(db.Model):
    """
    Tabla para rastrear empaques que esperan validación de la API.
    Una vez validados, se pasan a la tabla inventario_empaques.
    """
    __tablename__ = 'empaques_pendientes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fridge_id = db.Column(db.String(64), db.ForeignKey('fridges.fridge_id'), nullable=False, index=True)

    # Identificación del empaque pendiente
    epc = db.Column(db.String(24), nullable=True)
    id_empaque = db.Column(db.Integer, nullable=True)

    # Estado de validación
    estado = db.Column(db.String(20), nullable=False, default='pendiente')  # pendiente, validado, error
    mensaje_error = db.Column(db.String(256), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Índices únicos (mismo que Empaque)
    __table_args__ = (
        db.UniqueConstraint('fridge_id', 'epc', name='uix_pendiente_fridge_epc'),
        db.UniqueConstraint('fridge_id', 'id_empaque', name='uix_pendiente_fridge_id_empaque'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'fridge_id': self.fridge_id,
            'epc': self.epc,
            'id_empaque': self.id_empaque,
            'estado': self.estado,
            'mensaje_error': self.mensaje_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        identifiers = []
        if self.epc:
            identifiers.append(f"EPC:{self.epc}")
        if self.id_empaque:
            identifiers.append(f"ID:{self.id_empaque}")
        identifier = " | ".join(identifiers) if identifiers else "Sin ID"
        return f'<EmpaquePendiente {identifier} ({self.estado})>'


class EventLog(db.Model):
    """
    Log de eventos enviados a la API real.
    Útil para debugging y auditoría.
    """
    __tablename__ = 'event_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fridge_id = db.Column(db.String(64), nullable=False, index=True)
    event_type = db.Column(db.String(64), nullable=False)
    payload = db.Column(db.Text, nullable=True)
    response_status = db.Column(db.Integer, nullable=True)
    response_body = db.Column(db.Text, nullable=True)
    success = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'fridge_id': self.fridge_id,
            'event_type': self.event_type,
            'success': self.success,
            'response_status': self.response_status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f'<EventLog {self.event_type} - {"OK" if self.success else "FAIL"}>'


class VentaPendiente(db.Model):
    """
    Representa una venta pendiente de liquidación.
    Productos que han sido vendidos pero aún no liquidados con la API.
    """
    __tablename__ = 'ventas_pendientes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fridge_id = db.Column(db.String(64), db.ForeignKey('fridges.fridge_id'), nullable=False, index=True)
    producto_global_id = db.Column(db.Integer, db.ForeignKey('productos_globales.id'), nullable=True, index=True)

    # Identificación del empaque vendido
    epc = db.Column(db.String(24), nullable=True)
    id_empaque = db.Column(db.Integer, nullable=True)

    # Datos del producto vendido
    peso_nominal_g = db.Column(db.Float, nullable=True)

    # Estado de liquidación
    estado = db.Column(db.String(20), nullable=False, default='pendiente')  # pendiente, liquidado, error

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    fridge = db.relationship('Fridge', backref='ventas_pendientes')
    producto_global = db.relationship('ProductoGlobal', backref='ventas_pendientes')

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON"""
        return {
            'id': self.id,
            'fridge_id': self.fridge_id,
            'producto_global_id': self.producto_global_id,
            'product_id': self.producto_global.product_id if self.producto_global else None,
            'product_name': self.producto_global.name if self.producto_global else None,
            'epc': self.epc,
            'id_empaque': self.id_empaque,
            'peso_nominal_g': self.peso_nominal_g,
            'estado': self.estado,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        identifiers = []
        if self.epc:
            identifiers.append(f"EPC:{self.epc}")
        if self.id_empaque:
            identifiers.append(f"ID:{self.id_empaque}")
        identifier = " | ".join(identifiers) if identifiers else "Sin ID"
        return f'<VentaPendiente {identifier} ({self.estado})>'
