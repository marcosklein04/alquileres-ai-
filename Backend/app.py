import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, date

from db import get_db_connection, DB_ENGINE
from mailer import send_email  # SMTP: usa SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/MAIL_FROM

app = Flask(__name__)
CORS(app)


# =========================================================
# Helper SQL (mysql/sqlite placeholders)
# =========================================================
def ejecutar(cur, sql_mysql, sql_sqlite, params):
    if DB_ENGINE == "mysql":
        cur.execute(sql_mysql, params)
    else:
        cur.execute(sql_sqlite, params)


# =========================================================
# Helpers fecha/estado
# =========================================================
def _parse_iso_date(d):
    """
    d puede ser:
    - date/datetime (MySQL)
    - string 'YYYY-MM-DD' (SQLite o serializado)
    - None
    """
    if not d:
        return None

    if isinstance(d, date):
        return d if not isinstance(d, datetime) else d.date()

    try:
        return datetime.strptime(str(d), "%Y-%m-%d").date()
    except ValueError:
        return None


def _estado_contrato(fecha_fin, umbral_dias=60):
    hoy = date.today()
    fin = _parse_iso_date(fecha_fin)

    if not fin:
        return {"dias_restantes": None, "estado": "sin_fecha_fin", "requiere_aviso_60d": False}

    dias = (fin - hoy).days

    if dias < 0:
        return {"dias_restantes": dias, "estado": "vencido", "requiere_aviso_60d": False}

    if dias <= umbral_dias:
        return {"dias_restantes": dias, "estado": "por_vencer", "requiere_aviso_60d": True}

    return {"dias_restantes": dias, "estado": "vigente", "requiere_aviso_60d": False}


# =========================================================
# Debug: listar rutas
# =========================================================
@app.route("/api/routes", methods=["GET"])
def routes():
    out = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        methods = sorted([m for m in rule.methods if m in ("GET", "POST", "PATCH", "PUT", "DELETE")])
        out.append({"rule": str(rule), "methods": methods})
    out.sort(key=lambda x: x["rule"])
    return jsonify({"total": len(out), "routes": out}), 200


@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"message": "pong"}), 200


# =========================================================
# POST /api/contracts (IA)
# =========================================================
@app.route("/api/contracts", methods=["POST"])
def crear_contrato():
    from ai import extraer_datos_contrato
    try:
        from ai import extraer_datos_contrato
    except Exception as e:
        return jsonify({
            "error": "No se pudo cargar el motor de IA (dependencias faltantes).",
            "detalle": repr(e)
        }), 500

    data = request.get_json() or {}
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

    # si no extrajo nada, no insertamos
    if (not res.get("ok")) or all(extraidos.get(k) is None for k in extraidos.keys()):
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


# =========================================================
# GET /api/contracts (simple)
# =========================================================
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
    out = []

    for r in rows:
        fin = _parse_iso_date(r.get("fecha_fin"))
        dias_restantes = (fin - hoy).days if fin else None
        por_vencer = dias_restantes is not None and 0 <= dias_restantes <= 60

        out.append({
            "id": r.get("id"),
            "inmobiliaria": r.get("inmobiliaria"),
            "inquilino": r.get("inquilino"),
            "propietario": r.get("propietario"),
            "fecha_inicio": str(r.get("fecha_inicio")) if r.get("fecha_inicio") else None,
            "fecha_fin": str(r.get("fecha_fin")) if r.get("fecha_fin") else None,
            "dias_restantes": dias_restantes,
            "por_vencer": por_vencer,
            "decision_renovacion": r.get("decision_renovacion"),
        })

    return jsonify(out), 200


# =========================================================
# PATCH /api/contracts/<id>/renewal
# =========================================================
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
        (decision, contrato_id),
    )

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"ok": True}), 200


# =========================================================
# POST /api/contracts/manual
# =========================================================
@app.route("/api/contracts/manual", methods=["POST"])
def crear_contrato_manual():
    data = request.get_json() or {}

    conn = get_db_connection()
    cur = conn.cursor()

    sql_mysql = """
        INSERT INTO contratos (
            inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin, dias_aviso,
            email_inquilino, email_propietario
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    sql_sqlite = """
        INSERT INTO contratos (
            inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin, dias_aviso,
            email_inquilino, email_propietario
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        data.get("inmobiliaria"),
        data.get("inquilino"),
        data.get("propietario"),
        data.get("fecha_inicio"),
        data.get("fecha_fin"),
        data.get("dias_aviso", 60),
        data.get("email_inquilino"),
        data.get("email_propietario"),
    )

    ejecutar(cur, sql_mysql, sql_sqlite, params)

    conn.commit()
    contrato_id = cur.lastrowid
    cur.close()
    conn.close()

    return jsonify({"id": contrato_id}), 201


# =========================================================
# GET /api/contracts/list (enriquecido + filtro)
# =========================================================
@app.route("/api/contracts/list", methods=["GET"])
def listar_contratos_enriquecidos():
    umbral = request.args.get("umbral", default="60")
    try:
        umbral = int(umbral)
    except ValueError:
        umbral = 60

    only = request.args.get("only")  # por_vencer | vigente | vencido | sin_fecha_fin

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, inmobiliaria, inquilino, propietario,
               fecha_inicio, fecha_fin, dias_aviso, decision_renovacion
        FROM contratos
        ORDER BY fecha_fin ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    items = []
    for r in rows:
        calc = _estado_contrato(r.get("fecha_fin"), umbral_dias=umbral)
        item = {
            "id": r.get("id"),
            "inmobiliaria": r.get("inmobiliaria"),
            "inquilino": r.get("inquilino"),
            "propietario": r.get("propietario"),
            "fecha_inicio": str(r.get("fecha_inicio")) if r.get("fecha_inicio") else None,
            "fecha_fin": str(r.get("fecha_fin")) if r.get("fecha_fin") else None,
            "dias_aviso": r.get("dias_aviso", 60),
            "decision_renovacion": r.get("decision_renovacion"),
            **calc,
        }
        if only and item.get("estado") != only:
            continue
        items.append(item)

    return jsonify({"items": items, "umbral_dias": umbral}), 200


# =========================================================
# POST /api/notifications/run-60d
# Envía mail y marca notificado_60d solo si envía OK
# =========================================================
@app.route("/api/notifications/run-60d", methods=["POST"])
def run_notifications_60d():
    umbral = 60
    hoy = date.today()

    conn = get_db_connection()
    cur = conn.cursor()

    # Nota: agrego estado='ACTIVO' para no notificar cosas dadas de baja
    cur.execute("""
        SELECT id, inquilino, propietario, fecha_fin,
               email_inquilino, email_propietario,
               notificado_60d, decision_renovacion
        FROM contratos
        WHERE estado = 'ACTIVO'
          AND fecha_fin IS NOT NULL
          AND notificado_60d = 0
          AND (email_inquilino IS NOT NULL OR email_propietario IS NOT NULL)
        ORDER BY fecha_fin ASC
    """)
    rows = cur.fetchall()

    notificados = []
    saltados = []

    for r in rows:
        fin = _parse_iso_date(r.get("fecha_fin"))
        if not fin:
            saltados.append({"id": r.get("id"), "motivo": "sin_fecha_fin"})
            continue

        dias = (fin - hoy).days
        if not (0 <= dias <= umbral):
            saltados.append({"id": r.get("id"), "motivo": f"fuera_de_umbral ({dias})"})
            continue

        # si ya decidió, no avisar
        if r.get("decision_renovacion") not in (None, "PENDIENTE"):
            saltados.append({"id": r.get("id"), "motivo": f"decision_renovacion={r.get('decision_renovacion')}"})
            continue

        destinos = []
        if r.get("email_inquilino"):
            destinos.append(r["email_inquilino"])
        if r.get("email_propietario"):
            destinos.append(r["email_propietario"])

        if not destinos:
            saltados.append({"id": r.get("id"), "motivo": "sin_emails"})
            continue

        subject = f"[Alquileres AI] Contrato por vencer en {dias} días (ID {r.get('id')})"
        body = (
            "Hola,\n\n"
            "Aviso automático: un contrato está próximo a vencer.\n\n"
            f"Contrato ID: {r.get('id')}\n"
            f"Inquilino: {r.get('inquilino')}\n"
            f"Propietario: {r.get('propietario')}\n"
            f"Fecha fin: {fin}\n"
            f"Días restantes: {dias}\n\n"
            "Saludos,\n"
            "Sistema Alquileres AI\n"
        )

        try:
            for to in destinos:
                send_email(to=to, subject=subject, body=body)

            ejecutar(
                cur,
                "UPDATE contratos SET notificado_60d = %s, notificado_60d_at = %s WHERE id = %s",
                "UPDATE contratos SET notificado_60d = ?, notificado_60d_at = ? WHERE id = ?",
                (1, datetime.now(), r.get("id")),
            )

            notificados.append({"id": r.get("id"), "dias_restantes": dias, "destinos": destinos})

        except Exception as e:
            saltados.append({"id": r.get("id"), "motivo": f"error_envio: {repr(e)}"})
            continue

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


# =========================================================
# Main
# =========================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)