from src.dedupe import dedupe
from src.fraud import fraud_reasons
from src.models import Listing


def _l(i, **kw):
    base = dict(plataforma="p%d" % i, id_externo=str(i), url="u%d" % i, titulo="Toyota Yaris", precio=4000,
                anio=2012, km=150000, modelo_key="Toyota Yaris", motor_key="1.33 VVT-i", num_fotos=8,
                descripcion="Toyota Yaris 1.33 en muy buen estado, ITV en vigor, libro de revisiones")
    base.update(kw)
    return Listing(**base)


def test_dedupe_cross_platform(cfg):
    a = _l(1)
    b = _l(2, km=151500, precio=3900, descripcion="Yaris 1.33 muy buen estado ITV en vigor y libro revisiones")
    c = _l(3, km=100000)
    out = dedupe([a, b, c], cfg)
    assert len(out) == 2
    assert any(o.duplicados for o in out)


def test_fraud(cfg):
    assert fraud_reasons(_l(1, descripcion="Solo envío, estoy fuera"), 4000, cfg)
    assert fraud_reasons(_l(1, precio=2000), 4000, cfg)          # -50 % vs mediana
    assert fraud_reasons(_l(1, num_fotos=0), 4000, cfg)
    assert not fraud_reasons(_l(1), 4000, cfg)
