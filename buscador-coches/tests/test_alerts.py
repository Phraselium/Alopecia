"""Alertas (selección y mensaje, sin red) y registro de desaparición de anuncios."""
from pathlib import Path

from src.models import Listing
from src.notify import load_env, message, select_alerts, send
from src.store import Store


def _f(uid, total, estado="sí"):
    l = Listing(plataforma="p", id_externo=uid, url=f"https://x/{uid}", titulo="Toyota Yaris 1.3", marca="Toyota",
                modelo="Yaris", anio=2012, km=120000, precio=4200, etiqueta_dgt="C", etiqueta_fuente="DGT")
    return {"listing": l, "total": total, "estado": estado, "coste": {"total": 4300}, "avisos": "distancia no verificable"}


def test_select_alerts(cfg):
    filas = [_f("1", 70), _f("2", 40), _f("3", 80, "negociar"), _f("4", 90, "no"), _f("5", 75)]
    sel = select_alerts(filas, new_uids={"p:1", "p:2", "p:3", "p:4"}, already=set(), cfg=cfg)
    assert [f["listing"].uid for f in sel] == ["p:1", "p:3"]          # umbral, presupuesto y solo nuevos
    assert not select_alerts(filas, {"p:1"}, {"p:1"}, cfg)            # no se repite una alerta
    a = _f("6", 90)
    a["listing"].etiqueta_dgt, a["listing"].etiqueta_dudosa = "A", True
    assert not select_alerts([a], {"p:6"}, set(), cfg)                 # dudosa A: no se avisa


def test_message_and_send_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    txt = message(_f("3", 80, "negociar"))
    assert "Etiqueta: C (fichero oficial DGT)" in txt
    assert "negociar" in txt and "4.300 €" in txt and "https://x/3" in txt and "120.000 km" in txt
    env = load_env(tmp_path / ".env")   # no existe
    assert send(txt, env, tmp_path / "alertas.log") is False
    assert "Yaris" in (tmp_path / "alertas.log").read_text(encoding="utf-8")


def test_send_with_token(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=abc\nTELEGRAM_CHAT_ID=42\n", encoding="utf-8")
    calls = {}

    class R:
        status_code = 200
        text = "ok"

    def fake_post(url, json, timeout):
        calls["url"], calls["json"] = url, json
        return R()
    monkeypatch.setattr("src.notify.requests.post", fake_post)
    assert send("hola", load_env(tmp_path / ".env"), tmp_path / "a.log")
    assert calls["url"].endswith("/botabc/sendMessage") and calls["json"]["chat_id"] == "42"


def test_mark_missing(tmp_path: Path):
    st = Store(tmp_path / "db.sqlite")
    ls = [Listing(plataforma="p", id_externo=str(i), url="u", titulo="t") for i in range(3)]
    st.add_new(ls)
    st.add_market([{"uid": f"p:{i}", "plataforma": "p", "marca": "Seat", "modelo": "Ibiza", "titulo": "t",
                    "anio": 2010, "km": 1, "precio": 3000.0} for i in range(3)])
    seen = {"p:0", "p:1"}
    st.mark_missing("p", seen, seen, runs_needed=2)
    assert st.db.execute("SELECT COUNT(*) FROM listings WHERE gone_at IS NOT NULL").fetchone()[0] == 0
    st.mark_missing("p", seen, seen, runs_needed=2)               # segunda ejecución sin ver p:2
    assert st.db.execute("SELECT uid FROM listings WHERE gone_at IS NOT NULL").fetchall() == [("p:2",)]
    assert len(st.sale_times()) == 1
    st.mark_missing("p", seen | {"p:2"}, seen | {"p:2"}, runs_needed=2)   # reaparece
    assert st.db.execute("SELECT COUNT(*) FROM listings WHERE gone_at IS NOT NULL").fetchone()[0] == 0
