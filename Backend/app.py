from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, date

from db import get_db_connection, DB_ENGINE

app = Flask(__name__)
CORS(app)


@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"message": "pong"}), 200


def ejecutar(cur, sql_mysql, sql_sqlite, params):
    if DB_ENGINE == "mysql":
        cur.execute(sql_mysql, params)
    else:
        cur.execute(sql_sqlite, params)


# =========================
# POST /api/contracts
# =========================
@app.route("/api/contracts", methods=["POST"])
def crear_contrato():
    from ai import extraer_datos_contrato

    data = request.get_json() or {}
    texto_contrato = data.get("texto_contrato")

    if not texto_contrato:
        return jsonify({"error": "Falta texto_contrato"}), 400

    # defaults
    res = {"ok": False, "model": None, "raw": None, "data": {}}
    extraidos = {
        "inmobiliaria": None,
        "inquilino": None,
        "propietario": None,
        "fecha_inicio": None,
        "fecha_fin": None,
    }

    # 1) IA
    try:
        res = extraer_datos_contrato(texto_contrato) or res
        extraidos = res.get("data") or extraidos
    except Exception as e:
        print("❌ Error IA (excepción):", repr(e))

    # 2) Validación
    if (not res.get("ok")) or all(
        extraidos.get(k) is None
        for k in ["inmobiliaria", "inquilino", "propietario", "fecha_inicio", "fecha_fin"]
    ):
        return jsonify({
            "error": "La IA no pudo extraer datos del contrato. Revisar texto o API Key.",
            "ia_ok": res.get("ok"),
            "ia_modelo": res.get("model"),
        }), 422

    # 3) Insert
    conn = get_db_connection()
    cur = conn.cursor()

    sql_mysql = """
        INSERT INTO contratos (
            inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin
        ) VALUES (%s, %s, %s, %s, %s)
    """
    sql_sqlite = """
        INSERT INTO contratos (
            inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin
        ) VALUES (?, ?, ?, ?, ?)
    """
    params = (
        extraidos.get("inmobiliaria"),
        extraidos.get("inquilino"),
        extraidos.get("propietario"),
        extraidos.get("fecha_inicio"),
        extraidos.get("fecha_fin"),
    )

    ejecutar(cur, sql_mysql, sql_sqlite, params)

    try:
        conn.commit()
    except Exception:
        pass

    contrato_id = cur.lastrowid
    cur.close()
    conn.close()

    return jsonify({
        "id": contrato_id,
        "extraido": extraidos,
        "ia_ok": True,
        "ia_modelo": res.get("model"),
    }), 201


# =========================
# GET /api/contracts
# (listado simple + dias_restantes/por_vencer)
# =========================
@app.route("/api/contracts", methods=["GET"])
def listar_contratos():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, inmobiliaria, inquilino, propietario,
               fecha_inicio, fecha_fin, decision_renovacion
        FROM contratos
        ORDER BY fecha_fin ASC
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    hoy = date.today()
    contratos = []

    for r in rows:
        fin_raw = r["fecha_fin"]
        fin = None

        if fin_raw:
            if isinstance(fin_raw, date):
                fin = fin_raw
            else:
                try:
                    fin = datetime.strptime(str(fin_raw), "%Y-%m-%d").date()
                except ValueError:
                    fin = None

        dias_restantes = (fin - hoy).days if fin else None
        por_vencer = dias_restantes is not None and 0 <= dias_restantes <= 60

        contratos.append({
            "id": r["id"],
            "inmobiliaria": r["inmobiliaria"],
            "inquilino": r["inquilino"],
            "propietario": r["propietario"],
            "fecha_inicio": str(r["fecha_inicio"]) if r["fecha_inicio"] else None,
            "fecha_fin": str(r["fecha_fin"]) if r["fecha_fin"] else None,
            "dias_restantes": dias_restantes,
            "por_vencer": por_vencer,
            "decision_renovacion": r["decision_renovacion"],
        })

    return jsonify(contratos), 200


# =========================
# PATCH /api/contracts/<id>/renewal
# =========================
@app.route("/api/contracts/<int:contrato_id>/renewal", methods=["PATCH"])
def actualizar_renovacion(contrato_id):
    data = request.get_json() or {}
    decision = data.get("decision")

    if decision not in ["RENUEVA", "NO_RENUEVA"]:
        return jsonify({"error": "decision inválida"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    ejecutar(
        cur,
        "UPDATE contratos SET decision_renovacion = %s WHERE id = %s",
        "UPDATE contratos SET decision_renovacion = ? WHERE id = ?",
        (decision, contrato_id)
    )

    try:
        conn.commit()
    except Exception:
        pass

    cur.close()
    conn.close()

    return jsonify({"ok": True}), 200


# =========================
# POST /api/contracts/manual
# =========================
@app.route("/api/contracts/manual", methods=["POST"])
def crear_contrato_manual():
    data = request.get_json() or {}

    conn = get_db_connection()
    cur = conn.cursor()

    sql_mysql = """
        INSERT INTO contratos (
            inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin, dias_aviso
        ) VALUES (%s, %s, %s, %s, %s, %s)
    """
    sql_sqlite = """
        INSERT INTO contratos (
            inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin, dias_aviso
        ) VALUES (?, ?, ?, ?, ?, ?)
    """
    params = (
        data.get("inmobiliaria"),
        data.get("inquilino"),
        data.get("propietario"),
        data.get("fecha_inicio"),
        data.get("fecha_fin"),
        data.get("dias_aviso", 60),
    )

    ejecutar(cur, sql_mysql, sql_sqlite, params)

    try:
        conn.commit()
    except Exception:
        pass

    contrato_id = cur.lastrowid
    cur.close()
    conn.close()

    return jsonify({"id": contrato_id}), 201


# =========================
# Helpers para "estado"
# =========================
def _parse_iso_date(d: str | None):
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        return None


def _estado_contrato(fecha_fin_iso: str | None, umbral_dias: int = 60):
    hoy = date.today()
    fin = _parse_iso_date(fecha_fin_iso)

    if not fin:
        return {"dias_restantes": None, "estado": "sin_fecha_fin", "requiere_aviso_60d": False}

    dias = (fin - hoy).days

    if dias < 0:
        return {"dias_restantes": dias, "estado": "vencido", "requiere_aviso_60d": False}
    if dias <= umbral_dias:
        return {"dias_restantes": dias, "estado": "por_vencer", "requiere_aviso_60d": True}
    return {"dias_restantes": dias, "estado": "vigente", "requiere_aviso_60d": False}


# =========================
# GET /api/contracts/list
# (listado enriquecido + filtros)
# =========================
@app.route("/api/contracts/list", methods=["GET"])
def listar_contratos_enriquecidos():
    umbral = request.args.get("umbral", default="60")
    try:
        umbral = int(umbral)
    except ValueError:
        umbral = 60

    only = request.args.get("only")  # por_vencer | vigente | vencido | sin_fecha_fin

    # Opción A: seguir como lo tenías (db.py trae lista de dicts)
    from db import listar_contratos_bd

    contratos = listar_contratos_bd()

    items = []
    for c in contratos:
        calc = _estado_contrato(c.get("fecha_fin"), umbral_dias=umbral)
        item = {**c, **calc}
        if only and item.get("estado") != only:
            continue
        items.append(item)

    return jsonify({"items": items, "umbral_dias": umbral}), 200

@app.route("/api/alerts/contracts", methods=["GET"])
def alertas_contratos_por_vencer():
    # configurable: /api/alerts/contracts?umbral=60
    umbral = request.args.get("umbral", default="60")
    try:
        umbral = int(umbral)
    except ValueError:
        umbral = 60

    from db import listar_contratos_bd  # debe devolver lista de dicts

    contratos = listar_contratos_bd()

    alertas = []
    for c in contratos:
        # si ya se decidió, no avisar
        # solo alertar si sigue pendiente
        if c.get("decision_renovacion") not in (None, "PENDIENTE"):
            continue

        calc = _estado_contrato(c.get("fecha_fin"), umbral_dias=umbral)

        if calc.get("estado") == "por_vencer" and calc.get("requiere_aviso_60d") is True:
            alertas.append({**c, **calc})

    return jsonify({
        "items": alertas,
        "umbral_dias": umbral,
        "total": len(alertas)
    }), 200


if __name__ == "__main__":
    app.run(debug=True)
    app.run(host="127.0.0.1", port=5000, debug=True)