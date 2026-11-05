"""Registro de plataformas."""
from .autocasion import Autocasion
from .autoscout24 import AutoScout24
from .cochesnet import CochesNet
from .milanuncios import Milanuncios
from .monitors import Autohero, Clicars, Flexicar, Renew
from .ocasionplus import OcasionPlus
from .wallapop import Wallapop

REGISTRY = {s.name: s for s in (OcasionPlus, Flexicar, Clicars, Autohero, Renew,
                                AutoScout24, CochesNet, Wallapop, Milanuncios, Autocasion)}
