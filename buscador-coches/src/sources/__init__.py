"""Registro de plataformas."""
from .autocasion import Autocasion
from .autoscout24 import AutoScout24
from .cochesnet import CochesNet
from .milanuncios import Milanuncios
from .wallapop import Wallapop

REGISTRY = {s.name: s for s in (Wallapop, AutoScout24, Autocasion, CochesNet, Milanuncios)}
