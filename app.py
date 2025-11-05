"""
Qualisem Productos — Sistema de registro de productos fitosanitarios (Streamlit + SQLite)
Autor: ChatGPT (GPT-5 Thinking)
Fecha: 2025-11-04

Instrucciones rápidas (README):
1) Crea un repo en GitHub y añade estos archivos:
   - app.py  (este archivo)
   - requirements.txt  (contenido sugerido más abajo)
   - data/ (carpeta vacía para la BD SQLite y exportaciones CSV)
2) Instala dependencias:  pip install -r requirements.txt
3) Ejecuta:              streamlit run app.py

requirements.txt sugerido:
--------------------------
streamlit>=1.37
pandas>=2.2

Notas:
- Se usa SQLite (archivo local) sin dependencias extra.
- El esquema cubre: productos, movimientos (entradas/salidas) y stock.
- Campos clave de producto: nombre, ingrediente_activo, categoria, peligrosidad (rojo/amarillo/azul/verde), **empresa** (proveedor/origen).
- Campos de movimiento: empresa (proveedor/origen) y estado_pago (pagado/debe) por cada entrada/salida.
- Incluye validaciones, filtros, exportación a CSV y control de stock (no permite negativos).
"""

from __future__ import annotations
import os
import sqlite3
from datetime import datetime, date
from typing import Literal, Dict

import pandas as pd
import streamlit as st

# =============== Configuración básica ===============
st.set_page_config(
    page_title="Qualisem Productos | Fitosanitarios",
    page_icon="🌿",
    layout="wide",
)

DB_DIR = os.path.join("data")
DB_PATH = os.path.join(DB_DIR, "fitosanitarios.db")
EXPORT_DIR = DB_DIR  # usar misma carpeta para exportaciones simples

HAZARD_LEVELS: Dict[str, str] = {
    "rojo": "🟥 Rojo (Alto)",
    "amarillo": "🟨 Amarillo (Moderado)",
    "azul": "🟦 Azul (Cuidado)",
    "verde": "🟩 Verde (Bajo)",
}
HAZARD_KEYS = list(HAZARD_LEVELS.keys())

# =============== Inicialización de la BD ===============

def init_storage():
    os.makedirs(DB_DIR, exist_ok=True)


def get_conn():
    init_storage()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ingrediente_activo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            peligrosidad TEXT NOT NULL CHECK (peligrosidad IN ('rojo','amarillo','azul','verde')),
            unidad TEXT NOT NULL DEFAULT 'L',
            empresa TEXT,
            stock REAL NOT NULL DEFAULT 0
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('entrada','salida')),
            cantidad REAL NOT NULL,
            usuario TEXT,
            notas TEXT,
            empresa TEXT,
            estado_pago TEXT CHECK (estado_pago IN ('pagado','debe')),
            FOREIGN KEY(producto_id) REFERENCES productos(id) ON DELETE CASCADE
        );
        """
    )

    conn.commit()
    conn.close()


def migrate_db():
    """Asegura columnas nuevas en instalaciones existentes."""
    conn = get_conn()
    cur = conn.cursor()
    # productos.empresa
    cur.execute("PRAGMA table_info(productos);")
    prod_cols = {row[1] for row in cur.fetchall()}
    if "empresa" not in prod_cols:
        cur.execute("ALTER TABLE productos ADD COLUMN empresa TEXT;")
    # movimientos.empresa / estado_pago
    cur.execute("PRAGMA table_info(movimientos);")
    mov_cols = {row[1] for row in cur.fetchall()}
    if "empresa" not in mov_cols:
        cur.execute("ALTER TABLE movimientos ADD COLUMN empresa TEXT;")
    if "estado_pago" not in mov_cols:
        cur.execute("ALTER TABLE movimientos ADD COLUMN estado_pago TEXT;")
    conn.commit()
    conn.close()


init_db()
migrate_db()

# =============== Funciones DAO ===============

def add_producto(nombre: str, ingrediente_activo: str, categoria: str, peligrosidad: str, unidad: str = "L", empresa: str | None = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO productos (nombre, ingrediente_activo, categoria, peligrosidad, unidad, empresa, stock)
        VALUES (?,?,?,?,?,?,0)
        """,
        (nombre.strip(), ingrediente_activo.strip(), categoria.strip(), peligrosidad, unidad, (empresa.strip() if empresa else None)),
    )
    conn.commit()
    conn.close()


def list_productos_df() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT id, nombre, ingrediente_activo, categoria, peligrosidad, unidad, empresa, stock FROM productos ORDER BY nombre ASC",
        conn,
    )
    conn.close()
    return df


def get_producto(producto_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nombre, ingrediente_activo, categoria, peligrosidad, unidad, empresa, stock FROM productos WHERE id=?",
        (producto_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        keys = ["id", "nombre", "ingrediente_activo", "categoria", "peligrosidad", "unidad", "empresa", "stock"]
        return dict(zip(keys, row))
    return None


def update_producto(producto_id: int, nombre: str, ingrediente_activo: str, categoria: str, peligrosidad: str, unidad: str, empresa: str | None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE productos
        SET nombre=?, ingrediente_activo=?, categoria=?, peligrosidad=?, unidad=?, empresa=?
        WHERE id=?
        """,
        (nombre.strip(), ingrediente_activo.strip(), categoria.strip(), peligrosidad, unidad, (empresa.strip() if empresa else None), producto_id),
    )
    conn.commit()
    conn.close()


def delete_producto(producto_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM productos WHERE id=?", (producto_id,))
    conn.commit()
    conn.close()


def registrar_movimiento(
    producto_id: int,
    tipo: Literal['entrada','salida'],
    cantidad: float,
    usuario: str | None,
    notas: str | None,
    fecha_str: str,
    empresa: str | None,
    estado_pago: Literal['pagado','debe'] | None,
):
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a 0")

    conn = get_conn()
    cur = conn.cursor()

    # Verifica stock para salidas
    cur.execute("SELECT stock FROM productos WHERE id=?", (producto_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError("Producto no encontrado")

    stock_actual = float(row[0])
    nuevo_stock = stock_actual + cantidad if tipo == 'entrada' else stock_actual - cantidad

    if tipo == 'salida' and nuevo_stock < 0:
        conn.close()
        raise ValueError("Stock insuficiente para registrar la salida")

    # Inserta movimiento
    cur.execute(
        """
        INSERT INTO movimientos (producto_id, fecha, tipo, cantidad, usuario, notas, empresa, estado_pago)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (producto_id, fecha_str, tipo, cantidad, usuario, notas, empresa, estado_pago),
    )

    # Actualiza stock
    cur.execute("UPDATE productos SET stock=? WHERE id=?", (nuevo_stock, producto_id))

    conn.commit()
    conn.close()


def movimientos_df(
    f_ini: str | None = None,
    f_fin: str | None = None,
    producto_id: int | None = None,
    tipo: str | None = None,
    estado_pago: str | None = None,
    empresa: str | None = None,
) -> pd.DataFrame:
    conn = get_conn()
    parts = [
        "SELECT m.id, m.fecha, m.tipo, m.cantidad, m.usuario, m.notas, m.empresa, m.estado_pago, ",
        "p.nombre AS producto, p.ingrediente_activo, p.categoria, p.peligrosidad, p.unidad ",
        "FROM movimientos m JOIN productos p ON p.id = m.producto_id ",
        "WHERE 1=1",
    ]
    params = []
    if f_ini:
        parts.append("AND date(m.fecha) >= date(?)")
        params.append(f_ini)
    if f_fin:
        parts.append("AND date(m.fecha) <= date(?)")
        params.append(f_fin)
    if producto_id:
        parts.append("AND m.producto_id = ?")
        params.append(producto_id)
    if tipo in ("entrada", "salida"):
        parts.append("AND m.tipo = ?")
        params.append(tipo)
    if estado_pago in ("pagado", "debe"):
        parts.append("AND m.estado_pago = ?")
        params.append(estado_pago)
    if empresa:
        parts.append("AND m.empresa LIKE ?")
        params.append(f"%{empresa}%")

    parts.append("ORDER BY datetime(m.fecha) DESC, m.id DESC")
    sql = "
".join(parts)

    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


# =============== UI Helpers ===============

def hazard_badge(code: str) -> str:
    label = HAZARD_LEVELS.get(code, code)
    return label


def df_with_badges(df: pd.DataFrame) -> pd.DataFrame:
    if "peligrosidad" in df.columns:
        df = df.copy()
        df["peligrosidad"] = df["peligrosidad"].map(hazard_badge)
    return df


# =============== Sidebar ===============
st.sidebar.title("🌿 Qualisem Productos")
st.sidebar.caption("Registro de fitosanitarios: entradas, salidas e inventario")

with st.sidebar:
    st.markdown("**Leyenda de peligrosidad**")
    for k in HAZARD_KEYS:
        st.markdown(f"- {hazard_badge(k)}")

st.title("📦 Registro de Productos Fitosanitarios")
st.write("Gestiona **entradas/salidas**, catálogo de **productos** y **stock** actual.")

# Tabs principales
TAB_CATALOGO, TAB_MOV, TAB_INVENTARIO, TAB_HIST = st.tabs([
    "📚 Catálogo de productos",
    "➕➖ Entradas / Salidas",
    "📊 Inventario",
    "🕓 Historial",
])

# =============== Tab: Catálogo de productos ===============
with TAB_CATALOGO:
    st.subheader("Agregar producto")
    with st.form("form_producto", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Nombre comercial *", placeholder="Ej: Clorpirifos 48 EC")
            ingrediente = st.text_input("Ingrediente activo *", placeholder="Ej: Clorpirifos")
            categoria = st.text_input("Categoría *", placeholder="Insecticida / Fungicida / Herbicida …")
        with col2:
            peligrosidad = st.selectbox("Peligrosidad *", options=HAZARD_KEYS, format_func=lambda x: HAZARD_LEVELS[x])
            unidad = st.selectbox("Unidad", ["L", "mL", "kg", "g", "u"], index=0)
        empresa_prod = st.text_input("Empresa (proveedor/origen del producto)", placeholder="Ej: AgroPerú SAC")
        submitted = st.form_submit_button("Guardar producto", type="primary")

    if submitted:
        if not (nombre and ingrediente and categoria):
            st.error("Completa los campos obligatorios (*)")
        else:
            add_producto(nombre, ingrediente, categoria, peligrosidad, unidad, empresa_prod or None)
            st.success(f"Producto **{nombre}** registrado")

    st.divider()
    st.subheader("Catálogo")
    df_prod = list_productos_df()
    if df_prod.empty:
        st.info("No hay productos. Agrega el primero en el formulario de arriba.")
    else:
        q = st.text_input("Buscar por nombre / ingrediente / categoría / empresa", key="q_catalogo")
        if q:
            mask = (
                df_prod["nombre"].str.contains(q, case=False, na=False)
                | df_prod["ingrediente_activo"].str.contains(q, case=False, na=False)
                | df_prod["categoria"].str.contains(q, case=False, na=False)
                | df_prod["empresa"].str.contains(q, case=False, na=False)
            )
            df_show = df_prod[mask]
        else:
            df_show = df_prod

        st.dataframe(
            df_with_badges(df_show),
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("Editar / Eliminar producto"):
            prod_opt = {f"{r.nombre} — {r.ingrediente_activo} (id {r.id})": int(r.id) for r in df_prod.itertuples()}
            if prod_opt:
                pid = st.selectbox("Selecciona el producto", options=list(prod_opt.values()), format_func=lambda i: list(prod_opt.keys())[list(prod_opt.values()).index(i)])
                p = get_producto(pid)
                if p:
                    c1, c2 = st.columns(2)
                    with c1:
                        new_nombre = st.text_input("Nombre", value=p["nombre"])
                        new_ing = st.text_input("Ingrediente activo", value=p["ingrediente_activo"])
                        new_cat = st.text_input("Categoría", value=p["categoria"])
                        new_emp = st.text_input("Empresa", value=p.get("empresa") or "")
                    with c2:
                        new_pel = st.selectbox("Peligrosidad", HAZARD_KEYS, index=HAZARD_KEYS.index(p["peligrosidad"]), format_func=lambda x: HAZARD_LEVELS[x])
                        new_uni = st.selectbox("Unidad", ["L", "mL", "kg", "g", "u"], index=["L","mL","kg","g","u"].index(p["unidad"]))

                    c3, c4 = st.columns([1,1])
                    if c3.button("Actualizar", type="primary"):
                        update_producto(pid, new_nombre, new_ing, new_cat, new_pel, new_uni, new_emp or None)
                        st.success("Producto actualizado")
                    if c4.button("Eliminar", type="secondary"):
                        delete_producto(pid)
                        st.warning("Producto eliminado")

# =============== Tab: Entradas / Salidas ===============
with TAB_MOV:
    st.subheader("Registrar movimiento")

    df_prod = list_productos_df()
    if df_prod.empty:
        st.info("Primero registra productos en el catálogo")
    else:
        # Selector de producto
        prod_label = {int(r.id): f"{r.nombre} — {r.ingrediente_activo} (Stock: {r.stock} {r.unidad})" for r in df_prod.itertuples()}
        producto_id = st.selectbox("Producto", options=list(prod_label.keys()), format_func=lambda k: prod_label[k])

        c1, c2, c3 = st.columns(3)
        with c1:
            tipo = st.radio("Tipo", ["entrada", "salida"], horizontal=True)
        with c2:
            cantidad = st.number_input("Cantidad", min_value=0.0, step=0.1, value=0.0, help="Usa la misma unidad definida en el producto")
        with c3:
            fecha = st.date_input("Fecha", value=date.today())

        c4, c5 = st.columns(2)
        with c4:
            empresa_mov = st.text_input("Empresa (proveedor/origen)", placeholder="Ej: AgroPerú SAC")
        with c5:
            estado_pago = st.selectbox("Estado de pago", options=["pagado", "debe"], index=1)

        usuario = st.text_input("Usuario/Responsable (opcional)")
        notas = st.text_area("Notas (lote, proveedor, destino, etc.)", height=80)

        if st.button("Registrar movimiento", type="primary"):
            try:
                fecha_str = datetime.combine(fecha, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
                registrar_movimiento(
                    int(producto_id),
                    tipo,
                    float(cantidad),
                    usuario.strip() or None,
                    notas.strip() or None,
                    fecha_str,
                    empresa_mov.strip() or None,
                    estado_pago,
                )
                st.success(f"Movimiento de **{tipo}** registrado")
            except Exception as e:
                st.error(f"No se pudo registrar: {e}")

    st.divider()
    st.subheader("Atajos")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Descargar catálogo CSV"):
            df = list_productos_df()
            if not df.empty:
                path = os.path.join(EXPORT_DIR, f"catalogo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
                df.to_csv(path, index=False)
                st.success(f"Exportado: {path}")
            else:
                st.info("Catálogo vacío")
    with c2:
        if st.button("Descargar historial CSV"):
            df = movimientos_df()
            if not df.empty:
                path = os.path.join(EXPORT_DIR, f"historial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
                df.to_csv(path, index=False)
                st.success(f"Exportado: {path}")
            else:
                st.info("Historial vacío")

# =============== Tab: Inventario ===============
with TAB_INVENTARIO:
    st.subheader("Inventario actual")
    df_prod = list_productos_df()
    if df_prod.empty:
        st.info("Sin productos.")
    else:
        # Filtros
        categorias_unicas = sorted([c for c in df_prod["categoria"].dropna().unique()])
        colf1, colf2, colf3 = st.columns([1,1,1])
        with colf1:
            f_pelig = st.multiselect("Peligrosidad", options=HAZARD_KEYS, format_func=lambda x: HAZARD_LEVELS[x])
        with colf2:
            f_cat_multi = st.multiselect("Categorías", options=categorias_unicas, help="Selecciona una o varias categorías para ver su stock total")
        with colf3:
            f_text = st.text_input("Buscar texto (nombre/IA/empresa)")

        df_show = df_prod.copy()
        if f_pelig:
            df_show = df_show[df_show["peligrosidad"].isin(f_pelig)]
        if f_cat_multi:
            df_show = df_show[df_show["categoria"].isin(f_cat_multi)]
        if f_text:
            mask = (
                df_show["nombre"].str.contains(f_text, case=False, na=False)
                | df_show["ingrediente_activo"].str.contains(f_text, case=False, na=False)
                | df_show["empresa"].str.contains(f_text, case=False, na=False)
            )
            df_show = df_show[mask]

        # Indicadores simples
        total_items = len(df_show)
        total_stock = df_show["stock"].sum() if not df_show.empty else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Productos (filtrados)", total_items)
        c2.metric("Suma de stock", f"{total_stock:.2f}")
        c3.metric("Categorías únicas", df_show["categoria"].nunique())

        # Resumen por categoría
        st.markdown("### 📂 Resumen por categoría")
        if df_show.empty:
            st.info("Sin datos para resumir.")
        else:
            df_sum = (
                df_show.groupby("categoria", dropna=False)["stock"].sum().reset_index().sort_values("stock", ascending=False)
            )
            st.dataframe(df_sum, use_container_width=True, hide_index=True)
            try:
                st.bar_chart(data=df_sum.set_index("categoria")["stock"], height=240)
            except Exception:
                pass

        st.markdown("### 📋 Detalle de productos")
        st.dataframe(
            df_with_badges(df_show),
            use_container_width=True,
            hide_index=True,
        )

# =============== Tab: Historial ===============

with TAB_HIST:
    st.subheader("Historial de movimientos")

    # Filtros
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        f_ini = st.date_input("Desde", value=None, format="YYYY-MM-DD")
    with c2:
        f_fin = st.date_input("Hasta", value=None, format="YYYY-MM-DD")
    with c3:
        dfp = list_productos_df()
        prod_map = {0: "Todos"}
        if not dfp.empty:
            prod_map.update({int(r.id): f"{r.nombre}" for r in dfp.itertuples()})
        sel_pid = st.selectbox("Producto", options=list(prod_map.keys()), format_func=lambda k: prod_map[k])
    with c4:
        tipo = st.selectbox("Tipo", options=["Todos", "entrada", "salida"], index=0)

    c5, c6 = st.columns(2)
    with c5:
        f_estado_pago = st.selectbox("Estado de pago", options=["Todos", "pagado", "debe"], index=0)
    with c6:
        f_empresa = st.text_input("Empresa contiene")

    f_ini_str = f_ini.strftime("%Y-%m-%d") if isinstance(f_ini, date) else None
    f_fin_str = f_fin.strftime("%Y-%m-%d") if isinstance(f_fin, date) else None
    tipo_query = None if tipo == "Todos" else tipo
    pid_query = None if sel_pid == 0 else int(sel_pid)
    estado_pago_query = None if f_estado_pago == "Todos" else f_estado_pago

    df_hist = movimientos_df(
        f_ini=f_ini_str,
        f_fin=f_fin_str,
        producto_id=pid_query,
        tipo=tipo_query,
        estado_pago=estado_pago_query,
        empresa=f_empresa or None,
    )

    if df_hist.empty:
        st.info("Sin movimientos para los filtros actuales.")
    else:
        st.dataframe(df_with_badges(df_hist), use_container_width=True, hide_index=True)

        # Resumen rápido
        entradas = df_hist[df_hist["tipo"] == "entrada"]["cantidad"].sum()
        salidas = df_hist[df_hist["tipo"] == "salida"]["cantidad"].sum()
        pagado_sum = df_hist[df_hist["estado_pago"] == "pagado"]["cantidad"].sum() if "estado_pago" in df_hist.columns else 0
        debe_sum = df_hist[df_hist["estado_pago"] == "debe"]["cantidad"].sum() if "estado_pago" in df_hist.columns else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Entradas (sum)", f"{entradas:.2f}")
        c2.metric("Salidas (sum)", f"{salidas:.2f}")
        c3.metric("Pagado (sum)", f"{pagado_sum:.2f}")
        c4.metric("Debe (sum)", f"{debe_sum:.2f}")

st.caption("© 2025 Qualisem Productos — Registro simple en Streamlit con SQLite. 🐍")
