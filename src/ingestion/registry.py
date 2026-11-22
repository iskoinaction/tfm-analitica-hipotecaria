from .ecb import ECBConnector
from .eurostat import EurostatConnector
from .ine import INEConnector
from .tinsa import TinsaConnector
from .vivienda import MivauConnector

CONNECTORS = {"ine": INEConnector(), "ecb": ECBConnector(), "eurostat": EurostatConnector(),
              "tinsa": TinsaConnector(), "mivau": MivauConnector()}


def get_connector(source: str):
    return CONNECTORS[source]
