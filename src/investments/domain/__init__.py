"""Dominio puro de inversiones.

Reglas duras de esta capa:

- Solo biblioteca estándar (``decimal``, ``datetime``, ``dataclasses``,
  ``enum``, ``typing``). Prohibido importar Streamlit, pandas, HTTP,
  lectura de ficheros o cualquier adaptador.
- ``Decimal`` siempre para dinero y cantidades; nunca ``float``.
- Ninguna ausencia de datos se convierte en cero: se devuelve ``None``
  con cobertura y motivo.
- Fechas de negocio (``date``) separadas de timestamps de recepción
  (``datetime`` con zona horaria UTC).
"""
