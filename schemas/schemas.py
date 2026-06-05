# schemas/schemas.py
from pydantic import BaseModel
from datetime import date
from typing import Optional, List


class DetalleTransaccionCreate(BaseModel):
    idproducto:      Optional[int] = None
    descripcion:     str
    cantidad:        int = 1
    precio_unitario: float


class TransaccionCreate(BaseModel):
    idperiodo:     int
    fecha:         date
    tipo:          str
    descripcion:   str
    monto_base:    float
    iva:           float = 0
    documento_ref: Optional[str] = None
    detalles:      List[DetalleTransaccionCreate] = []