from .ecb import ECBConnector
from .eurostat import EurostatConnector
from .ine import INEConnector
from .tinsa import TinsaConnector

CONNECTORS = {"ine": INEConnector(), "ecb": ECBConnector(), "eurostat": EurostatConnector(), "tinsa": TinsaConnector()}


def get_connector(source: str):
    return CONNECTORS[source]
