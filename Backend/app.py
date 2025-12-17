from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, date
from db import get_db_connection

app = Flask(__name__)
CORS(app)


@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"message": "pong"}), 200


@app.route("/api/contracts", methods=["POST"])
def crear_contrato():
    from ai import extraer_datos_contrato

    data = request.get_json() or {}
    texto_contrato = data.get("texto_contrato")

    if not texto_contrato:
        return jsonify({"error": "Falta texto_contrato"}), 400

    extraidos = extraer_datos_contrato(texto_contrato)

    inmobiliaria = extraidos.get("inmobiliaria")
    inquilino = extraidos.get("inquilino")
    propietario = extraidos.get("propietario")
    fecha_inicio = extraidos.get("fecha_inicio")  # ideal: "YYYY-MM-DD"
    fecha_fin = extraidos.get("fecha_fin")        # ideal: "YYYY-MM-DD"

    conn = get_db_connection()
    cur = conn.cursor()

    # MySQL: placeholders %s
    cur.execute("""
        INSERT INTO contratos (
            inmobiliaria, inquilino, propietario,
            fecha_inicio, fecha_fin
        ) VALUES (%s, %s, %s, %s, %s)
    """, (inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin))

    # Con autocommit=True no hace falta, pero no molesta.
    try:
        conn.commit()
    except Exception:
        pass

    contrato_id = cur.lastrowid
    cur.close()
    conn.close()

    return jsonify({"id": contrato_id, "extraido": extraidos}), 201


@app.route("/api/contracts", methods=["GET"])
def listar_contratos():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, inmobiliaria, inquilino, propietario,
               fecha_inicio, fecha_fin,
               decision_renovacion
        FROM contratos
        ORDER BY fecha_fin ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    hoy = datetime.today().date()
    contratos = []

    for r in rows:
        dias_restantes = None
        por_vencer = False

        fin_raw = r.get("fecha_fin")

        if fin_raw:
            # MySQL puede devolver date o str dependiendo del driver/config.
            if isinstance(fin_raw, (date,)):
                fin = fin_raw
            else:
                # fallback si viene como string
                try:
                    fin = datetime.strptime(str(fin_raw), "%Y-%m-%d").date()
                except ValueError:
                    fin = None

            if fin:
                dias_restantes = (fin - hoy).days
                por_vencer = 0 <= dias_restantes <= 60

        contratos.append({
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

    return jsonify(contratos), 200


@app.route("/api/contracts/<int:contrato_id>/renewal", methods=["PATCH"])
def actualizar_renovacion(contrato_id):
    data = request.get_json() or {}
    decision = data.get("decision")

    if decision not in ["RENUEVA", "NO_RENUEVA"]:
        return jsonify({"error": "decision inválida"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    # Opción 1 (recomendada): no seteás actualizado_en, MySQL lo actualiza solo por ON UPDATE
    cur.execute("""
        UPDATE contratos
        SET decision_renovacion = %s
        WHERE id = %s
    """, (decision, contrato_id))

    # Opción 2 (si querés forzar): actualizado_en = NOW()
    # cur.execute("""
    #     UPDATE contratos
    #     SET decision_renovacion = %s, actualizado_en = NOW()
    #     WHERE id = %s
    # """, (decision, contrato_id))

    try:
        conn.commit()
    except Exception:
        pass

    cur.close()
    conn.close()

    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    app.run(debug=True)