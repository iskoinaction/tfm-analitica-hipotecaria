from .ecb import ECBConnector
from .eurostat import EurostatConnector
from .ine import INEConnector
from .vivienda import MivauConnector

CONNECTORS = {"ine": INEConnector(), "ecb": ECBConnector(), "eurostat": EurostatConnector(),
              "mivau": MivauConnector()}


def get_connector(source: str):
    return CONNECTORS[source]
