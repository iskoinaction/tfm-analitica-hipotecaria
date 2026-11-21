"""Conectores de ingesta (uno por fuente). Interfaz común en ``base.Connector``."""
from .registry import CONNECTORS, get_connector  # noqa: F401
