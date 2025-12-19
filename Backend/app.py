from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, date

from db import get_db_connection, DB_ENGINE, listar_contratos_bd

app = Flask(__name__)
CORS(app)


def ejecutar(cur, sql_mysql, sql_sqlite, params):
    if DB_ENGINE == "mysql":
        cur.execute(sql_mysql, params)
    else:
        cur.execute(sql_sqlite, params)


# =========================
# DEBUG: listar rutas
# =========================
@app.route("/api/routes", methods=["GET"])
def routes():
    rules = []
    for r in sorted(app.url_map.iter_rules(), key=lambda x: str(x)):
        rules.append({"rule": str(r), "methods": sorted([m for m in r.methods if m not in ("HEAD", "OPTIONS")])})
    return jsonify({"routes": rules, "total": len(rules)}), 200


@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"message": "pong"}), 200


# =========================
# POST /api/contracts
# =========================
@app.route("/api/contracts", methods=["POST"])
def crear_contrato():
    from ai import extraer_datos_contrato

    data = request.get_json(silent=True) or {}
    texto_contrato = data.get("texto_contrato")

    if not texto_contrato:
        return jsonify({"error": "Falta texto_contrato"}), 400

    res = {"ok": False, "model": None, "raw": None, "data": {}}
    extraidos = {
        "inmobiliaria": None,
        "inquilino": None,
        "propietario": None,
        "fecha_inicio": None,
        "fecha_fin": None,
    }

    try:
        res = extraer_datos_contrato(texto_contrato) or res
        extraidos = res.get("data") or extraidos
    except Exception as e:
        print("❌ Error IA:", repr(e))

    if (not res.get("ok")) or all(
        extraidos.get(k) is None
        for k in ["inmobiliaria", "inquilino", "propietario", "fecha_inicio", "fecha_fin"]
    ):
        return jsonify({
            "error": "La IA no pudo extraer datos del contrato. Revisar texto o API Key.",
            "ia_ok": res.get("ok"),
            "ia_modelo": res.get("model"),
        }), 422

    conn = get_db_connection()
    cur = conn.cursor()

    sql_mysql = """
        INSERT INTO contratos (inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin)
        VALUES (%s, %s, %s, %s, %s)
    """
    sql_sqlite = """
        INSERT INTO contratos (inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin)
        VALUES (?, ?, ?, ?, ?)
    """
    params = (
        extraidos.get("inmobiliaria"),
        extraidos.get("inquilino"),
        extraidos.get("propietario"),
        extraidos.get("fecha_inicio"),
        extraidos.get("fecha_fin"),
    )

    ejecutar(cur, sql_mysql, sql_sqlite, params)
    conn.commit()

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
        fin = r["fecha_fin"] if isinstance(r["fecha_fin"], date) else None
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
    data = request.get_json(silent=True) or {}
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
    conn.commit()

    cur.close()
    conn.close()

    return jsonify({"ok": True}), 200


# =========================
# Helpers estado contrato
# =========================
def _parse_iso_date(d):
    if not d:
        return None
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").date()
    except ValueError:
        return None


def _estado_contrato(fecha_fin_iso, umbral_dias=60):
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
# =========================
@app.route("/api/contracts/list", methods=["GET"])
def listar_contratos_enriquecidos():
    umbral = request.args.get("umbral", default="60")
    try:
        umbral = int(umbral)
    except ValueError:
        umbral = 60

    only = request.args.get("only")  # por_vencer | vigente | vencido | sin_fecha_fin

    contratos = listar_contratos_bd()  # lista de dicts

    items = []
    for c in contratos:
        calc = _estado_contrato(c.get("fecha_fin"), umbral_dias=umbral)
        item = {**c, **calc}
        if only and item.get("estado") != only:
            continue
        items.append(item)

    return jsonify({"items": items, "umbral_dias": umbral, "total": len(items)}), 200


# =========================
# POST /api/notifications/run-60d
# =========================
@app.route("/api/notifications/run-60d", methods=["POST"])
def run_notifications_60d():
    umbral = 60
    hoy = date.today()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, inquilino, propietario, fecha_fin, email_inquilino, email_propietario, notificado_60d
        FROM contratos
        WHERE fecha_fin IS NOT NULL
          AND notificado_60d = 0
          AND (email_inquilino IS NOT NULL OR email_propietario IS NOT NULL)
        ORDER BY fecha_fin ASC
    """)
    rows = cur.fetchall()

    notificados = []
    saltados = []

    for r in rows:
        fin = r["fecha_fin"]
        dias = (fin - hoy).days if fin else None

        if dias is None:
            saltados.append({"id": r["id"], "motivo": "sin_fecha_fin"})
            continue

        if not (0 <= dias <= umbral):
            saltados.append({"id": r["id"], "motivo": f"fuera_de_umbral ({dias})"})
            continue

        # TODO: acá luego llamamos al envío real de email.
        # Por ahora marcamos como notificado:
        ejecutar(
            cur,
            "UPDATE contratos SET notificado_60d = %s, notificado_60d_at = %s WHERE id = %s",
            "UPDATE contratos SET notificado_60d = ?, notificado_60d_at = ? WHERE id = ?",
            (1, datetime.now(), r["id"])
        )

        notificados.append({
            "id": r["id"],
            "dias_restantes": dias,
            "email_inquilino": r["email_inquilino"],
            "email_propietario": r["email_propietario"],
        })

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "ok": True,
        "umbral_dias": umbral,
        "total_notificados": len(notificados),
        "notificados": notificados,
        "saltados": saltados,
    }), 200


if __name__ == "__main__":
    # Un solo run, un solo puerto. Sin reloader para que no te rompa al pausar.
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)