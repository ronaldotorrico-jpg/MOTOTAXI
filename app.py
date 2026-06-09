
import sqlite3
import os
from flask import Flask, request, jsonify, g
from datetime import datetime


BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE_DIR, "motorapido.db")

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

#  BASE DE DATOS SQLite
def get_db():
    """Devuelve la conexión a la base de datos (una por request)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row   # permite acceder por nombre de columna
    return g.db


@app.teardown_appcontext
def cerrar_db(error):
    """Cierra la conexión al terminar cada request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def inicializar_db():
    """Crea las tablas si no existen."""
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT    NOT NULL,
            telefono  TEXT    NOT NULL,
            origen    TEXT    NOT NULL,
            destino   TEXT    NOT NULL,
            fecha     TEXT    NOT NULL,
            hora      TEXT    NOT NULL,
            servicio  TEXT    NOT NULL,
            estado    TEXT    NOT NULL DEFAULT 'pendiente',
            precio    REAL,
            creado    TEXT    NOT NULL
        )
    """)
    db.commit()
    db.close()
    print("  ✅ Base de datos lista:", DB_PATH)

TARIFAS = {
    "Centro":     {"precio": 8,  "tiempo": "5 - 10 min",  "distancia": "0 - 3 km"},
    "Norte":      {"precio": 12, "tiempo": "10 - 15 min", "distancia": "3 - 6 km"},
    "Sur":        {"precio": 18, "tiempo": "15 - 25 min", "distancia": "6 - 10 km"},
    "Este/Oeste": {"precio": 25, "tiempo": "25 - 35 min", "distancia": "10 - 15 km"},
}

SERVICIOS_VALIDOS = ["viaje", "delivery", "mensajeria"]
ESTADOS_VALIDOS   = ["pendiente", "confirmado", "en camino", "completado", "cancelado"]


# ================================================================
#  FUNCIONES AUXILIARES
# ================================================================

def fila_a_dict(fila):
    """Convierte una fila de SQLite (Row) a diccionario."""
    return dict(fila) if fila else None


def validar_campos(datos, campos):
    """Valida que todos los campos requeridos estén presentes y no vacíos."""
    for campo in campos:
        if not datos.get(campo, "").strip():
            return False, campo
    return True, None


def calcular_precio(origen, destino):
    """
    Estima el precio buscando palabras clave de zona en origen/destino.
    Si no encuentra zona, devuelve tarifa base de Centro.
    """
    texto = (origen + " " + destino).lower()
    if "norte" in texto:
        return TARIFAS["Norte"]["precio"]
    elif "sur" in texto:
        return TARIFAS["Sur"]["precio"]
    elif "este" in texto or "oeste" in texto:
        return TARIFAS["Este/Oeste"]["precio"]
    else:
        return TARIFAS["Centro"]["precio"]


# ================================================================
#  RUTA PRINCIPAL
# ================================================================

@app.route("/")
def inicio():
    """Sirve la página principal index.html."""
    return app.send_static_file("index.html")


# ================================================================
#  RUTAS DE RESERVAS
# ================================================================

@app.route("/reservar", methods=["POST"])
def reservar():
    """
    Crea una nueva reserva de moto taxi.

    Recibe (JSON):
        nombre, telefono, origen, destino, fecha, hora, servicio

    Devuelve (JSON):
        { ok, mensaje, id, precio }
    """
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"error": "No se recibieron datos JSON."}), 400

    # -- Validación de campos obligatorios --
    campos_requeridos = ["nombre", "telefono", "origen", "destino",
                         "fecha", "hora", "servicio"]
    ok, campo_faltante = validar_campos(datos, campos_requeridos)
    if not ok:
        return jsonify({"error": f"El campo '{campo_faltante}' es obligatorio."}), 400

    # -- Validar servicio --
    if datos["servicio"] not in SERVICIOS_VALIDOS:
        return jsonify({"error": f"Servicio no válido. Opciones: {SERVICIOS_VALIDOS}"}), 400

    # -- Validar formato de fecha --
    try:
        datetime.strptime(datos["fecha"], "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD."}), 400

    # -- Calcular precio estimado --
    precio = calcular_precio(datos["origen"], datos["destino"])

    # -- Guardar en base de datos --
    db    = get_db()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = db.execute("""
        INSERT INTO reservas (nombre, telefono, origen, destino,
                              fecha, hora, servicio, estado, precio, creado)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, ?)
    """, (
        datos["nombre"].strip(),
        datos["telefono"].strip(),
        datos["origen"].strip(),
        datos["destino"].strip(),
        datos["fecha"].strip(),
        datos["hora"].strip(),
        datos["servicio"].strip(),
        precio,
        ahora,
    ))
    db.commit()
    nueva_id = cursor.lastrowid

    # -- Log en consola --
    print(f"\n  🏍️  Nueva reserva #{nueva_id}")
    print(f"     Cliente : {datos['nombre']}  |  {datos['telefono']}")
    print(f"     Ruta    : {datos['origen']}  →  {datos['destino']}")
    print(f"     Fecha   : {datos['fecha']} a las {datos['hora']}")
    print(f"     Servicio: {datos['servicio']}  |  Precio estimado: Bs. {precio}\n")

    mensaje = (
        f"¡Gracias {datos['nombre']}! "
        f"Tu viaje de {datos['origen']} → {datos['destino']} "
        f"fue reservado para el {datos['fecha']} a las {datos['hora']}. "
        f"Precio estimado: Bs. {precio}. "
        f"Te contactamos al {datos['telefono']}."
    )

    return jsonify({"ok": True, "mensaje": mensaje, "id": nueva_id, "precio": precio})


# ----------------------------------------------------------------

@app.route("/reservas", methods=["GET"])
def ver_reservas():
    """
    Devuelve todas las reservas en JSON.
    Parámetros opcionales de URL:
        ?estado=pendiente    filtra por estado
        ?fecha=2025-06-01    filtra por fecha
    """
    db     = get_db()
    estado = request.args.get("estado", "").strip()
    fecha  = request.args.get("fecha", "").strip()

    consulta = "SELECT * FROM reservas WHERE 1=1"
    params   = []

    if estado:
        consulta += " AND estado = ?"
        params.append(estado)
    if fecha:
        consulta += " AND fecha = ?"
        params.append(fecha)

    consulta += " ORDER BY id DESC"

    filas    = db.execute(consulta, params).fetchall()
    lista    = [fila_a_dict(f) for f in filas]

    return jsonify({"total": len(lista), "reservas": lista})


# ----------------------------------------------------------------

@app.route("/reservas/<int:reserva_id>", methods=["GET"])
def ver_reserva(reserva_id):
    """Devuelve una reserva específica por ID."""
    db   = get_db()
    fila = db.execute("SELECT * FROM reservas WHERE id = ?", (reserva_id,)).fetchone()
    if not fila:
        return jsonify({"error": f"Reserva #{reserva_id} no encontrada."}), 404
    return jsonify(fila_a_dict(fila))


# ----------------------------------------------------------------

@app.route("/reservas/<int:reserva_id>/estado", methods=["PUT"])
def cambiar_estado(reserva_id):
    """
    Actualiza el estado de una reserva.

    Recibe (JSON):  { "estado": "confirmado" }
    Estados válidos: pendiente | confirmado | en camino | completado | cancelado
    """
    datos = request.get_json(silent=True)
    if not datos or "estado" not in datos:
        return jsonify({"error": "Falta el campo 'estado'."}), 400

    nuevo_estado = datos["estado"].strip().lower()
    if nuevo_estado not in ESTADOS_VALIDOS:
        return jsonify({"error": f"Estado no válido. Opciones: {ESTADOS_VALIDOS}"}), 400

    db   = get_db()
    fila = db.execute("SELECT id FROM reservas WHERE id = ?", (reserva_id,)).fetchone()
    if not fila:
        return jsonify({"error": f"Reserva #{reserva_id} no encontrada."}), 404

    db.execute("UPDATE reservas SET estado = ? WHERE id = ?", (nuevo_estado, reserva_id))
    db.commit()

    print(f"  🔄 Reserva #{reserva_id} → estado: {nuevo_estado}")
    return jsonify({"ok": True, "id": reserva_id, "estado": nuevo_estado})


# ----------------------------------------------------------------

@app.route("/reservas/<int:reserva_id>", methods=["DELETE"])
def cancelar_reserva(reserva_id):
    """Elimina (cancela) una reserva por ID."""
    db   = get_db()
    fila = db.execute("SELECT id, nombre FROM reservas WHERE id = ?", (reserva_id,)).fetchone()
    if not fila:
        return jsonify({"error": f"Reserva #{reserva_id} no encontrada."}), 404

    db.execute("DELETE FROM reservas WHERE id = ?", (reserva_id,))
    db.commit()

    print(f"  🗑️  Reserva #{reserva_id} eliminada ({fila['nombre']})")
    return jsonify({"ok": True, "mensaje": f"Reserva #{reserva_id} eliminada correctamente."})


# ================================================================
#  RUTA TARIFAS
# ================================================================

@app.route("/tarifa", methods=["POST"])
def calcular_tarifa():
    """
    Calcula la tarifa según la zona.

    Recibe (JSON):  { "zona": "Norte" }
    Devuelve (JSON): { zona, precio, tiempo, distancia }
    """
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"error": "No se recibieron datos JSON."}), 400

    zona = datos.get("zona", "").strip()
    if zona not in TARIFAS:
        return jsonify({
            "error": "Zona no encontrada.",
            "zonas_disponibles": list(TARIFAS.keys())
        }), 404

    return jsonify({
        "zona":      zona,
        "precio":    TARIFAS[zona]["precio"],
        "tiempo":    TARIFAS[zona]["tiempo"],
        "distancia": TARIFAS[zona]["distancia"],
    })


@app.route("/tarifas", methods=["GET"])
def ver_todas_tarifas():
    """Devuelve todas las tarifas disponibles."""
    return jsonify(TARIFAS)


# ================================================================
#  ESTADÍSTICAS DEL NEGOCIO
# ================================================================

@app.route("/estadisticas", methods=["GET"])
def estadisticas():
    """
    Devuelve un resumen del negocio:
    - Total de reservas
    - Reservas por estado
    - Reservas por servicio
    - Ingresos totales y promedio
    - Reservas de hoy
    """
    db    = get_db()
    hoy   = datetime.now().strftime("%Y-%m-%d")

    total = db.execute("SELECT COUNT(*) FROM reservas").fetchone()[0]

    # Conteo por estado
    por_estado = {}
    for estado in ESTADOS_VALIDOS:
        n = db.execute("SELECT COUNT(*) FROM reservas WHERE estado = ?", (estado,)).fetchone()[0]
        por_estado[estado] = n

    # Conteo por tipo de servicio
    por_servicio = {}
    for serv in SERVICIOS_VALIDOS:
        n = db.execute("SELECT COUNT(*) FROM reservas WHERE servicio = ?", (serv,)).fetchone()[0]
        por_servicio[serv] = n

    # Ingresos (solo reservas completadas)
    fila_ing = db.execute(
        "SELECT SUM(precio), AVG(precio) FROM reservas WHERE estado = 'completado'"
    ).fetchone()
    ingresos_total   = round(fila_ing[0] or 0, 2)
    ingresos_promedio = round(fila_ing[1] or 0, 2)

    # Reservas de hoy
    hoy_total = db.execute(
        "SELECT COUNT(*) FROM reservas WHERE fecha = ?", (hoy,)
    ).fetchone()[0]

    return jsonify({
        "fecha_consulta":    hoy,
        "total_reservas":    total,
        "reservas_hoy":      hoy_total,
        "por_estado":        por_estado,
        "por_servicio":      por_servicio,
        "ingresos_completados": {
            "total":   ingresos_total,
            "promedio": ingresos_promedio,
            "moneda":  "Bs."
        }
    })


# ================================================================
#  EXPORTAR RESERVAS A ARCHIVO .TXT
# ================================================================

@app.route("/exportar", methods=["GET"])
def exportar():
    """
    Exporta todas las reservas a un archivo 'reservas.txt'
    en la misma carpeta del proyecto.
    """
    db    = get_db()
    filas = db.execute("SELECT * FROM reservas ORDER BY id").fetchall()

    ruta_txt = os.path.join(BASE_DIR, "reservas.txt")
    lineas   = []
    lineas.append("=" * 60)
    lineas.append("  MOTOÁPIDO — Reporte de Reservas")
    lineas.append(f"  Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lineas.append(f"  Total: {len(filas)} reservas")
    lineas.append("=" * 60)

    for f in filas:
        lineas.append("")
        lineas.append(f"  Reserva #{f['id']}  |  Estado: {f['estado'].upper()}")
        lineas.append(f"  Cliente : {f['nombre']}  ({f['telefono']})")
        lineas.append(f"  Ruta    : {f['origen']}  →  {f['destino']}")
        lineas.append(f"  Fecha   : {f['fecha']} a las {f['hora']}")
        lineas.append(f"  Servicio: {f['servicio']}  |  Precio: Bs. {f['precio']}")
        lineas.append(f"  Creado  : {f['creado']}")
        lineas.append("  " + "-" * 50)

    with open(ruta_txt, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas))

    print(f"  📄 Exportado a: {ruta_txt}")
    return jsonify({
        "ok":    True,
        "archivo": ruta_txt,
        "total": len(filas),
        "mensaje": f"Se exportaron {len(filas)} reservas a 'reservas.txt'."
    })


