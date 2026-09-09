"""Test de pureza del dominio: solo biblioteca estándar permitida.

El dominio no puede importar Streamlit, pandas, json, HTTP ni nada de
adapters. Este test inspecciona el código fuente de cada módulo del paquete
``src.investments.domain`` para garantizar la frontera.
"""

import re
from pathlib import Path

import src.investments.domain as dominio

_PROHIBIDOS = (
    "streamlit",
    "pandas",
    "json",
    "requests",
    "urllib",
    "http",
    "socket",
    "src.investments.adapters",
    "src.investments.application",
    "src.investments.ports",
    "src.investments.interfaces",
)

_PATRON_IMPORT = re.compile(r"^\s*(?:import|from)\s+([\w.]+)", re.MULTILINE)


def test_el_dominio_no_importa_dependencias_prohibidas() -> None:
    carpeta = Path(dominio.__file__).parent
    for modulo in sorted(carpeta.glob("*.py")):
        codigo = modulo.read_text(encoding="utf-8")
        for coincidencia in _PATRON_IMPORT.finditer(codigo):
            raiz = coincidencia.group(1)
            for prohibido in _PROHIBIDOS:
                assert raiz != prohibido and not raiz.startswith(prohibido + "."), (
                    f"{modulo.name} importa '{raiz}', prohibido en el dominio puro."
                )
