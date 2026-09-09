"""Excepciones del dominio de inversiones.

Todos los mensajes están en español. Las excepciones señalan violaciones de
invariantes del dominio; nunca se usan para ocultar una ausencia de datos
(las ausencias se modelan con ``None`` + cobertura + motivo).
"""


class ErrorDeDominio(Exception):
    """Error base de todas las excepciones del dominio de inversiones."""


class ValorInvalidoError(ErrorDeDominio):
    """Un valor no cumple los invariantes del objeto de valor.

    Por ejemplo: usar ``float`` para dinero, una moneda que no es ISO 4217
    o un tipo de cambio no positivo.
    """


class MonedaIncompatibleError(ErrorDeDominio):
    """Operación aritmética entre importes de monedas distintas."""


class PatasNoReconcilianError(ErrorDeDominio):
    """Las patas de una operación no reconcilian con el total declarado
    por la fuente dentro de la precisión declarada."""


class OperacionInvalidaError(ErrorDeDominio):
    """Una entidad u operación viola un invariante del dominio.

    Por ejemplo: fecha de negocio expresada como ``datetime``, timestamp sin
    zona horaria, P&L inventado sin coste demostrable, o un incidente de
    conciliación que pretende reemplazar el estado verificado.
    """
